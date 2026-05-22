"""Settings router (Stream 3).

Two surfaces:

  router         — /api/v2/settings/public    GET   any authenticated user
                   Returns only safe URL-style settings (no secrets).
                   Also hosts the Test Database (sandbox SQLite) endpoints.

  admin_router   — /api/admin/settings        GET / PUT / DELETE   owners only
                   Full read/write across the merged config surface.
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from core.audit import log_event
from core.config import UPLOAD_DIR
from core.db import app_settings as app_settings_coll
from core.deps import ROLE_OWNER, get_current_user, require_role
from services import config_service

logger = logging.getLogger("docchat.routers.settings")

router = APIRouter(prefix="/v2/settings", tags=["settings"])
admin_router = APIRouter(prefix="/admin/settings", tags=["admin"])

# Test DB (sandbox SQLite) storage — single active slot per deployment.
TEST_DB_DIR = UPLOAD_DIR / "test"
TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
TEST_DB_MAX_BYTES = 100 * 1024 * 1024   # 100 MB hard cap
TEST_DB_PATH_KEY = "db_agent_test_db_path"
TEST_DB_META_KEY = "db_agent_test_db_meta"


@router.get("/public")
async def get_public_settings(_: dict = Depends(get_current_user)):
    """Non-secret config — used by the frontend to discover base URLs etc."""
    return await config_service.get_public_subset()


@admin_router.get("")
async def list_settings(_: dict = Depends(require_role(ROLE_OWNER))):
    """Full merged view of every known setting (env > DB > default)."""
    data = await config_service.get_all_for_admin()
    # Mark which keys are sourced from env vs DB for the UI
    sources: dict[str, str] = {}
    db_keys = set()
    async for doc in app_settings_coll.find({}, {"_id": 0, "key": 1}):
        db_keys.add(doc["key"])
    for k in data:
        if os.environ.get(k.upper()):
            sources[k] = "env"
        elif k in db_keys:
            sources[k] = "db"
        else:
            sources[k] = "default"
    return {"settings": data, "sources": sources}


class SettingUpdate(BaseModel):
    value: Any


@admin_router.put("/{key}")
async def upsert_setting(
    key: str,
    body: SettingUpdate,
    _: dict = Depends(require_role(ROLE_OWNER)),
):
    if not key or len(key) > 100:
        raise HTTPException(status_code=400, detail="Invalid key")
    await config_service.set_setting(key, body.value)
    val = await config_service.get_setting(key)
    return {"key": key, "value": val, "ok": True}


@admin_router.delete("/{key}")
async def delete_setting(
    key: str,
    _: dict = Depends(require_role(ROLE_OWNER)),
):
    await config_service.delete_setting(key)
    return {"key": key, "ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Test Database (sandbox SQLite for the DB Agent)
#
# The production PostgreSQL connection is left untouched. When a test DB is
# active, the DB Agent's executor + schema service detect the path and route
# queries to SQLite instead. Removing the file silently reverts to live mode.
# ─────────────────────────────────────────────────────────────────────────────
def _import_os_safe():
    import os as _os
    return _os


async def _read_test_db_status() -> dict:
    """Return current test DB metadata or {"active": False}."""
    path = await config_service.get_setting(TEST_DB_PATH_KEY, "")
    meta = await config_service.get_setting(TEST_DB_META_KEY, None)
    if not path or not Path(path).exists():
        return {"active": False, "filename": None, "size": 0, "uploaded_at": None, "path": None}
    meta = meta or {}
    return {
        "active": True,
        "filename": meta.get("filename") or Path(path).name,
        "size": meta.get("size") or Path(path).stat().st_size,
        "uploaded_at": meta.get("uploaded_at"),
        "path": path,
    }


@router.get("/test-db")
async def get_test_db_status(user: dict = Depends(require_role(ROLE_OWNER))):
    """Owner-only: return active test DB metadata (or active=False)."""
    return await _read_test_db_status()


@router.post("/test-db")
async def upload_test_db(
    file: UploadFile = File(...),
    user: dict = Depends(require_role(ROLE_OWNER)),
):
    """Owner-only: upload a `.db` SQLite file as the DB Agent sandbox source.

    Replaces any existing test DB. The production Postgres connection config
    is NOT touched — removing the file silently reverts to live mode.
    """
    name = (file.filename or "").strip()
    if not name.lower().endswith(".db"):
        raise HTTPException(status_code=415, detail="Only .db (SQLite) files are accepted.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(raw) > TEST_DB_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {TEST_DB_MAX_BYTES // (1024 * 1024)} MB cap.")

    # Magic-bytes sanity check — SQLite v3 files begin with "SQLite format 3\0"
    if not raw.startswith(b"SQLite format 3\x00"):
        raise HTTPException(
            status_code=400,
            detail="File is not a valid SQLite database (magic bytes missing).",
        )

    # Remove any previously-active test DB on disk (incl. SQLite -shm/-wal sidecars)
    prev = await config_service.get_setting(TEST_DB_PATH_KEY, "")
    if prev:
        for suffix in ("", "-shm", "-wal"):
            try:
                Path(prev + suffix).unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Could not remove previous test DB sidecar %s: %s", suffix, e)

    # Save under a deterministic single-slot name with a uuid suffix so we can
    # always purge cleanly without worrying about cached file handles.
    disk_name = f"active-{uuid.uuid4().hex[:8]}.db"
    disk_path = TEST_DB_DIR / disk_name
    disk_path.write_bytes(raw)

    uploaded_at = datetime.now(timezone.utc).isoformat()
    meta = {"filename": name, "size": len(raw), "uploaded_at": uploaded_at}
    await config_service.set_setting(TEST_DB_PATH_KEY, str(disk_path))
    await config_service.set_setting(TEST_DB_META_KEY, meta)
    # Schema cache holds the previous DB's tables — flush so the LLM sees the new ones.
    try:
        from services.db_agent import schema_service as _schema
        _schema.invalidate()
    except Exception:
        pass

    await log_event(
        "settings.test_db.upload",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="settings",
        resource_id="test_db",
        metadata={"filename": name, "size": len(raw)},
    )
    return {
        "active": True,
        "filename": name,
        "size": len(raw),
        "uploaded_at": uploaded_at,
        "path": str(disk_path),
    }


@router.delete("/test-db")
async def remove_test_db(user: dict = Depends(require_role(ROLE_OWNER))):
    """Owner-only: clear the active test DB and revert the DB Agent to live mode."""
    prev = await config_service.get_setting(TEST_DB_PATH_KEY, "")
    if prev:
        for suffix in ("", "-shm", "-wal"):
            try:
                Path(prev + suffix).unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Could not delete test DB sidecar %s: %s", suffix, e)
    await config_service.delete_setting(TEST_DB_PATH_KEY)
    await config_service.delete_setting(TEST_DB_META_KEY)
    try:
        from services.db_agent import schema_service as _schema
        _schema.invalidate()
    except Exception:
        pass

    await log_event(
        "settings.test_db.remove",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="settings",
        resource_id="test_db",
    )
    return {"active": False}
