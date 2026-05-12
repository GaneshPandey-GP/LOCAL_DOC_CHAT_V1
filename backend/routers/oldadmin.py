"""Admin analytics, audit log, users, providers."""
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
    share_links,
    users,
)
from core.deps import ROLE_EDITOR, ROLE_OWNER, require_role
from core.security import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/analytics")
async def analytics(days: int = 7, _: dict = Depends(require_role(ROLE_OWNER))):
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat()

    # Totals
    total_docs = await documents.count_documents({})
    total_users = await users.count_documents({})
    total_sessions = await messages.distinct("session_id")
    total_share_links = await share_links.count_documents({})
    total_messages = await messages.count_documents({"created_at": {"$gte": since}})

    # Latency
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

    # Feedback ratio
    up = await feedback.count_documents({"rating": 1})
    down = await feedback.count_documents({"rating": -1})

    # Daily query counts
    daily: dict[str, int] = {}
    async for ev in analytics_events.find(
        {"event_type": "chat.query", "created_at": {"$gte": since}},
        {"_id": 0, "created_at": 1},
    ):
        day = ev["created_at"][:10]
        daily[day] = daily.get(day, 0) + 1
    series = [{"day": k, "count": v} for k, v in sorted(daily.items())]

    # Confidence distribution
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


class UserUpdate(BaseModel):
    role: Optional[str] = None


class UserCreateBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1, max_length=120)
    role: str = ROLE_EDITOR  # owners create editors by default


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
    """Owner-only: create a new editor (or owner) account."""
    if body.role not in (ROLE_OWNER, ROLE_EDITOR):
        raise HTTPException(status_code=400, detail="Invalid role. Allowed: owner, editor")
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
    if body.role and body.role not in (ROLE_OWNER, ROLE_EDITOR):
        raise HTTPException(status_code=400, detail="Invalid role. Allowed: owner, editor")
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
    """Owner-only: delete an editor account. Cannot delete self or last owner."""
    if user_id == actor["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    target = await users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("role") == ROLE_OWNER:
        owner_count = await users.count_documents({"role": ROLE_OWNER})
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last owner")
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


# ---------------------------------------------------------------------------
# Provider management (owner-only, runtime-switchable)
# ---------------------------------------------------------------------------
class ProviderUpdate(BaseModel):
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None


_ALLOWED_LLM_PROVIDERS = {"emergent", "openrouter"}
_ALLOWED_EMBEDDING_PROVIDERS = {"local", "openai"}


@router.get("/providers")
async def get_providers(_: dict = Depends(require_role(ROLE_OWNER))):
    """Return current effective provider configuration."""
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
    """Mutate provider config at runtime AND persist to /app/backend/.env."""
    from core import config as cfg

    updates: dict = {}
    if body.llm_provider is not None:
        if body.llm_provider.lower() not in _ALLOWED_LLM_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid llm_provider. Allowed: {sorted(_ALLOWED_LLM_PROVIDERS)}",
            )
        cfg.LLM_PROVIDER = body.llm_provider.lower()
        updates["LLM_PROVIDER"] = cfg.LLM_PROVIDER
    if body.llm_model is not None and body.llm_model.strip():
        cfg.LLM_MODEL = body.llm_model.strip()
        updates["LLM_MODEL"] = cfg.LLM_MODEL
    if body.embedding_provider is not None:
        if body.embedding_provider.lower() not in _ALLOWED_EMBEDDING_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid embedding_provider. Allowed: {sorted(_ALLOWED_EMBEDDING_PROVIDERS)}",
            )
        cfg.EMBEDDING_PROVIDER = body.embedding_provider.lower()
        updates["EMBEDDING_PROVIDER"] = cfg.EMBEDDING_PROVIDER
    if body.embedding_model is not None and body.embedding_model.strip():
        cfg.EMBEDDING_MODEL = body.embedding_model.strip()
        updates["EMBEDDING_MODEL"] = cfg.EMBEDDING_MODEL

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Persist to .env so settings survive a process restart.
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
    """Idempotent .env writer — adds or replaces keys without touching others."""
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
        # Non-fatal: runtime values are still updated in memory
        pass
    # Reflect in process env so any code reading os.environ later sees it
    for k, v in updates.items():
        os.environ[k] = str(v)
