"""Settings router (Stream 3).

Two surfaces:

  router         — /api/v2/settings/public    GET   any authenticated user
                   Returns only safe URL-style settings (no secrets).

  admin_router   — /api/admin/settings        GET / PUT / DELETE   owners only
                   Full read/write across the merged config surface.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.deps import ROLE_OWNER, get_current_user, require_role
from core.db import app_settings as app_settings_coll
from services import config_service

router = APIRouter(prefix="/v2/settings", tags=["settings"])
admin_router = APIRouter(prefix="/admin/settings", tags=["admin"])


@router.get("/public")
async def get_public_settings(_: dict = Depends(get_current_user)):
    """Non-secret config — used by the frontend to discover base URLs etc."""
    return await config_service.get_public_subset()


@admin_router.get("")
async def list_settings(_: dict = Depends(require_role(ROLE_OWNER))):
    """Full merged view of every known setting (env > DB > default)."""
    data = await config_service.get_all_for_admin()
    # Mark which keys are sourced from env vs DB for the UI
    import os
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
