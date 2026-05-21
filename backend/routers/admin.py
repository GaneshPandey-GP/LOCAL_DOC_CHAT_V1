"""Admin analytics, audit log, users, providers, and model configs."""
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field

from core.audit import log_event
from core.db import (
    analytics_events,
    audit_log,
    documents,
    feedback,
    messages,
    model_configs,
    share_links,
    users,
)
from core.deps import ROLE_EDITOR, ROLE_OWNER, require_role
from core.security import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])


# ──────────────────────────────────────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/analytics")
async def analytics(days: int = 7, _: dict = Depends(require_role(ROLE_OWNER))):
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat()

    total_docs = await documents.count_documents({})
    total_users = await users.count_documents({})
    total_sessions = await messages.distinct("session_id")
    total_share_links = await share_links.count_documents({})
    total_messages = await messages.count_documents({"created_at": {"$gte": since}})

    latencies = []
    async for m in messages.find(
        {"role": "assistant", "latency_ms": {"$exists": True}, "created_at": {"$gte": since}},
        {"_id": 0, "latency_ms": 1},
    ):
        latencies.append(m["latency_ms"])
    latencies.sort()

    def pct(p):
        if not latencies:
            return 0
        idx = min(len(latencies) - 1, int(len(latencies) * p))
        return latencies[idx]

    up = await feedback.count_documents({"rating": 1})
    down = await feedback.count_documents({"rating": -1})

    daily: dict[str, int] = {}
    async for ev in analytics_events.find(
        {"event_type": "chat.query", "created_at": {"$gte": since}},
        {"_id": 0, "created_at": 1},
    ):
        day = ev["created_at"][:10]
        daily[day] = daily.get(day, 0) + 1
    series = [{"day": k, "count": v} for k, v in sorted(daily.items())]

    conf_dist = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    async for m in messages.find(
        {"role": "assistant", "confidence": {"$exists": True}, "created_at": {"$gte": since}},
        {"_id": 0, "confidence": 1},
    ):
        c = m.get("confidence", "LOW")
        conf_dist[c] = conf_dist.get(c, 0) + 1

    return {
        "totals": {
            "documents": total_docs,
            "users": total_users,
            "sessions": len(total_sessions),
            "share_links": total_share_links,
            "messages": total_messages,
        },
        "latency_ms": {
            "p50": pct(0.5),
            "p90": pct(0.9),
            "p99": pct(0.99),
            "samples": len(latencies),
        },
        "feedback": {"up": up, "down": down, "ratio": round(up / (up + down), 2) if (up + down) else 0},
        "queries_daily": series,
        "confidence_distribution": conf_dist,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Audit log
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/audit-log")
async def get_audit_log(
    limit: int = Query(100, le=500),
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    _: dict = Depends(require_role(ROLE_OWNER)),
):
    query: dict = {}
    if action:
        query["action"] = action
    if actor_id:
        query["actor_id"] = actor_id
    cursor = audit_log.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(limit)


# ──────────────────────────────────────────────────────────────────────────────
# Users
# ──────────────────────────────────────────────────────────────────────────────
class UserUpdate(BaseModel):
    role: Optional[str] = None


class UserCreateBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1, max_length=120)
    role: str = ROLE_EDITOR


@router.get("/users")
async def list_users(_: dict = Depends(require_role(ROLE_OWNER))):
    cursor = users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1)
    return await cursor.to_list(500)


@router.post("/users")
async def create_user(
    body: UserCreateBody,
    request: Request,
    actor: dict = Depends(require_role(ROLE_OWNER)),
):
    if body.role not in (ROLE_OWNER, ROLE_EDITOR):
        raise HTTPException(status_code=400, detail="Invalid role. Allowed: Admin, editor")
    existing = await users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id,
        "email": body.email.lower(),
        "name": body.name,
        "role": body.role,
        "password_hash": hash_password(body.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await users.insert_one(doc)
    await log_event(
        "user.create",
        actor_id=actor["id"],
        actor_role=actor["role"],
        resource_type="user",
        resource_id=user_id,
        ip=request.client.host if request.client else None,
        metadata={"email": body.email.lower(), "role": body.role},
    )
    return {k: v for k, v in doc.items() if k not in ("password_hash", "_id")}


@router.patch("/users/{user_id}")
async def update_user(user_id: str, body: UserUpdate, _: dict = Depends(require_role(ROLE_OWNER))):
    if body.role and body.role not in (ROLE_OWNER, ROLE_EDITOR,'admin'):
        raise HTTPException(status_code=400, detail="Invalid role. Allowed: admin, editor")
    update: dict = {}
    if body.role:
        update["role"] = body.role
    if update:
        await users.update_one({"id": user_id}, {"$set": update})
    return {"ok": True}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    actor: dict = Depends(require_role(ROLE_OWNER)),
):
    if user_id == actor["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    target = await users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("role") == ROLE_OWNER:
        owner_count = await users.count_documents({"role": ROLE_OWNER})
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last admin")
    await users.delete_one({"id": user_id})
    await log_event(
        "user.delete",
        actor_id=actor["id"],
        actor_role=actor["role"],
        resource_type="user",
        resource_id=user_id,
        ip=request.client.host if request.client else None,
        metadata={"email": target.get("email")},
    )
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# Legacy provider config (env-based, kept for backward compat)
# ──────────────────────────────────────────────────────────────────────────────
class ProviderUpdate(BaseModel):
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None


_ALLOWED_LLM_PROVIDERS = {"emergent", "openrouter", "openai", "anthropic", "custom"}
_ALLOWED_EMBEDDING_PROVIDERS = {"local", "openai"}


@router.get("/providers")
async def get_providers(_: dict = Depends(require_role(ROLE_OWNER))):
    from core import config as cfg
    return {
        "llm": {
            "provider": cfg.LLM_PROVIDER,
            "model": cfg.LLM_MODEL,
            "allowed_providers": sorted(_ALLOWED_LLM_PROVIDERS),
        },
        "embedding": {
            "provider": cfg.EMBEDDING_PROVIDER,
            "model": cfg.EMBEDDING_MODEL,
            "allowed_providers": sorted(_ALLOWED_EMBEDDING_PROVIDERS),
        },
    }


@router.patch("/providers")
async def update_providers(
    body: ProviderUpdate,
    request: Request,
    actor: dict = Depends(require_role(ROLE_OWNER)),
):
    from core import config as cfg
    updates: dict = {}
    if body.llm_provider is not None:
        if body.llm_provider.lower() not in _ALLOWED_LLM_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Invalid llm_provider.")
        cfg.LLM_PROVIDER = body.llm_provider.lower()
        updates["LLM_PROVIDER"] = cfg.LLM_PROVIDER
    if body.llm_model is not None and body.llm_model.strip():
        cfg.LLM_MODEL = body.llm_model.strip()
        updates["LLM_MODEL"] = cfg.LLM_MODEL
    if body.embedding_provider is not None:
        if body.embedding_provider.lower() not in _ALLOWED_EMBEDDING_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Invalid embedding_provider.")
        cfg.EMBEDDING_PROVIDER = body.embedding_provider.lower()
        updates["EMBEDDING_PROVIDER"] = cfg.EMBEDDING_PROVIDER
    if body.embedding_model is not None and body.embedding_model.strip():
        cfg.EMBEDDING_MODEL = body.embedding_model.strip()
        updates["EMBEDDING_MODEL"] = cfg.EMBEDDING_MODEL
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    _persist_env_updates(updates)
    await log_event(
        "providers.update",
        actor_id=actor["id"],
        actor_role=actor["role"],
        resource_type="config",
        resource_id="providers",
        ip=request.client.host if request.client else None,
        metadata=updates,
    )
    return {
        "ok": True,
        "llm": {"provider": cfg.LLM_PROVIDER, "model": cfg.LLM_MODEL},
        "embedding": {"provider": cfg.EMBEDDING_PROVIDER, "model": cfg.EMBEDDING_MODEL},
        "note": "Saved. Some changes (e.g. embedding provider) only fully apply to new ingestions.",
    }


def _persist_env_updates(updates: dict) -> None:
    env_path = Path(os.environ.get("BACKEND_ENV_PATH", "/app/backend/.env"))
    try:
        existing_lines = env_path.read_text().splitlines() if env_path.exists() else []
    except Exception:
        existing_lines = []
    keys_to_set = dict(updates)
    out_lines = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in keys_to_set:
            out_lines.append(f"{key}={keys_to_set.pop(key)}")
        else:
            out_lines.append(line)
    for k, v in keys_to_set.items():
        out_lines.append(f"{k}={v}")
    try:
        env_path.write_text("\n".join(out_lines) + "\n")
    except Exception:
        pass
    for k, v in updates.items():
        os.environ[k] = str(v)


# ──────────────────────────────────────────────────────────────────────────────
# Model Configs — stored in MongoDB, fully managed from the frontend
# ──────────────────────────────────────────────────────────────────────────────

MODEL_TYPES = {"llm", "embedding"}
PROVIDER_OPTIONS = {
    "llm": ["emergent", "openrouter", "openai", "anthropic", "custom"],
    "embedding": ["local", "openai", "custom"],
}


class ModelConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    model_type: str          # "llm" | "embedding"
    provider: str            # e.g. "openrouter", "openai"
    model_id: str = Field(min_length=1, max_length=200)  # e.g. "gpt-4o-mini"
    api_key: Optional[str] = None          # stored encrypted-at-rest in future; plaintext for now
    api_base_url: Optional[str] = None     # custom base URL override
    is_active: bool = False                # whether this is the currently selected model
    notes: Optional[str] = None


class ModelConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    model_id: Optional[str] = None
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


def _sanitize_model(doc: dict) -> dict:
    """Return a safe model dict (mask API key)."""
    d = {k: v for k, v in doc.items() if k not in ("_id",)}
    if d.get("api_key"):
        key = d["api_key"]
        d["api_key_preview"] = key[:6] + "…" + key[-4:] if len(key) > 10 else "••••••"
        d["has_api_key"] = True
    else:
        d["api_key_preview"] = None
        d["has_api_key"] = False
    d.pop("api_key", None)  # never send raw key to frontend
    return d


@router.get("/models")
async def list_model_configs(_: dict = Depends(require_role(ROLE_OWNER))):
    """List all stored model configurations (keys masked)."""
    cursor = model_configs.find({}, {"_id": 0}).sort("created_at", -1)
    docs = await cursor.to_list(200)
    return [_sanitize_model(d) for d in docs]


@router.post("/models")
async def create_model_config(
    body: ModelConfigCreate,
    request: Request,
    actor: dict = Depends(require_role(ROLE_OWNER)),
):
    """Add a new model configuration."""
    if body.model_type not in MODEL_TYPES:
        raise HTTPException(status_code=400, detail=f"model_type must be one of {sorted(MODEL_TYPES)}")

    model_id_db = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # If setting this as active, deactivate others of same type first
    if body.is_active:
        await model_configs.update_many(
            {"model_type": body.model_type},
            {"$set": {"is_active": False}},
        )

    doc = {
        "id": model_id_db,
        "name": body.name.strip(),
        "model_type": body.model_type,
        "provider": body.provider.strip().lower(),
        "model_id": body.model_id.strip(),
        "api_key": body.api_key.strip() if body.api_key else None,
        "api_base_url": body.api_base_url.strip() if body.api_base_url else None,
        "is_active": body.is_active,
        "notes": body.notes,
        "created_by": actor["id"],
        "created_at": now,
        "updated_at": now,
    }
    await model_configs.insert_one(doc)

    # If active, apply to runtime config immediately
    if body.is_active:
        _apply_model_to_runtime(doc)

    await log_event(
        "model_config.create",
        actor_id=actor["id"],
        actor_role=actor["role"],
        resource_type="model_config",
        resource_id=model_id_db,
        ip=request.client.host if request.client else None,
        metadata={"name": body.name, "model_type": body.model_type, "provider": body.provider},
    )
    return _sanitize_model(doc)


@router.patch("/models/{model_config_id}")
async def update_model_config(
    model_config_id: str,
    body: ModelConfigUpdate,
    request: Request,
    actor: dict = Depends(require_role(ROLE_OWNER)),
):
    """Update a model configuration. To set as active, pass is_active=true."""
    existing = await model_configs.find_one({"id": model_config_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Model config not found")

    updates: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.provider is not None and body.provider.strip():
        updates["provider"] = body.provider.strip().lower()
    if body.model_id is not None and body.model_id.strip():
        updates["model_id"] = body.model_id.strip()
    if body.api_key is not None:
        updates["api_key"] = body.api_key.strip() if body.api_key.strip() else None
    if body.api_base_url is not None:
        updates["api_base_url"] = body.api_base_url.strip() if body.api_base_url.strip() else None
    if body.notes is not None:
        updates["notes"] = body.notes
    if body.is_active is not None:
        if body.is_active:
            # Deactivate siblings
            await model_configs.update_many(
                {"model_type": existing["model_type"], "id": {"$ne": model_config_id}},
                {"$set": {"is_active": False}},
            )
        updates["is_active"] = body.is_active

    await model_configs.update_one({"id": model_config_id}, {"$set": updates})
    updated = await model_configs.find_one({"id": model_config_id}, {"_id": 0})

    # Apply to runtime if active
    if updated.get("is_active"):
        _apply_model_to_runtime(updated)

    await log_event(
        "model_config.update",
        actor_id=actor["id"],
        actor_role=actor["role"],
        resource_type="model_config",
        resource_id=model_config_id,
        ip=request.client.host if request.client else None,
        metadata=list(updates.keys()),
    )
    return _sanitize_model(updated)


@router.delete("/models/{model_config_id}")
async def delete_model_config(
    model_config_id: str,
    request: Request,
    actor: dict = Depends(require_role(ROLE_OWNER)),
):
    """Delete a model configuration."""
    existing = await model_configs.find_one({"id": model_config_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Model config not found")
    if existing.get("is_active"):
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the active model. Set another model as active first.",
        )
    await model_configs.delete_one({"id": model_config_id})
    await log_event(
        "model_config.delete",
        actor_id=actor["id"],
        actor_role=actor["role"],
        resource_type="model_config",
        resource_id=model_config_id,
        ip=request.client.host if request.client else None,
        metadata={"name": existing.get("name")},
    )
    return {"ok": True}


@router.post("/models/{model_config_id}/activate")
async def activate_model_config(
    model_config_id: str,
    request: Request,
    actor: dict = Depends(require_role(ROLE_OWNER)),
):
    """Set a model as the active one for its type."""
    existing = await model_configs.find_one({"id": model_config_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Model config not found")

    await model_configs.update_many(
        {"model_type": existing["model_type"]},
        {"$set": {"is_active": False}},
    )
    await model_configs.update_one(
        {"id": model_config_id},
        {"$set": {"is_active": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    updated = await model_configs.find_one({"id": model_config_id}, {"_id": 0})
    _apply_model_to_runtime(updated)

    await log_event(
        "model_config.activate",
        actor_id=actor["id"],
        actor_role=actor["role"],
        resource_type="model_config",
        resource_id=model_config_id,
        ip=request.client.host if request.client else None,
        metadata={"name": existing.get("name"), "model_type": existing.get("model_type")},
    )
    return _sanitize_model(updated)


def _apply_model_to_runtime(doc: dict) -> None:
    """Push an active model config into the live config module + env."""
    from core import config as cfg
    from services import llm as llm_svc

    model_type = doc.get("model_type")
    provider = doc.get("provider", "")
    model_id = doc.get("model_id", "")
    api_key = doc.get("api_key") or ""
    api_base_url = doc.get("api_base_url") or ""

    if model_type == "llm":
        cfg.LLM_PROVIDER = provider
        cfg.LLM_MODEL = model_id
        if api_key:
            if provider in ("emergent",):
                cfg.EMERGENT_LLM_KEY = api_key
                os.environ["EMERGENT_LLM_KEY"] = api_key
            elif provider in ("openrouter",):
                cfg.OPENROUTER_API_KEY = api_key
                os.environ["OPENROUTER_API_KEY"] = api_key
            elif provider in ("openai",):
                cfg.OPENAI_API_KEY = api_key
                os.environ["OPENAI_API_KEY"] = api_key
            elif provider in ("anthropic",):
                cfg.ANTHROPIC_API_KEY = api_key
                os.environ["ANTHROPIC_API_KEY"] = api_key
            else:
                # custom — store under OPENAI_API_KEY for openai-compat endpoints
                os.environ["CUSTOM_API_KEY"] = api_key
        if api_base_url:
            cfg.OPENROUTER_BASE_URL = api_base_url
            os.environ["CUSTOM_BASE_URL"] = api_base_url
        # Reset the cached LLM client so next call picks up new creds
        llm_svc._client = None
        os.environ["LLM_PROVIDER"] = provider
        os.environ["LLM_MODEL"] = model_id

    elif model_type == "embedding":
        cfg.EMBEDDING_PROVIDER = provider
        cfg.EMBEDDING_MODEL = model_id
        if api_key and provider == "openai":
            cfg.OPENAI_API_KEY = api_key
            os.environ["OPENAI_API_KEY"] = api_key
        os.environ["EMBEDDING_PROVIDER"] = provider
        os.environ["EMBEDDING_MODEL"] = model_id
