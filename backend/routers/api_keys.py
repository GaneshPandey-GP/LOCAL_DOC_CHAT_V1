"""API Keys router (Module 8).

External systems authenticate by sending `X-API-Key: dck_…` instead of a JWT.
The `get_current_user` dependency in core.deps already handles the lookup;
this router just covers issuance / listing / revocation.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.audit import log_event
from core.config import is_enabled
from core.db import api_keys
from core.deps import ROLE_EDITOR, require_role

router = APIRouter(prefix="/v2/api-keys", tags=["api-keys"])


class APIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default="", max_length=200)
    expires_days: Optional[int] = None  # null = never


def _hash(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _mask(plain: str) -> str:
    return plain[:8] + "…" + plain[-4:] if len(plain) > 14 else plain


@router.post("", status_code=201)
async def create_api_key(body: APIKeyCreate, user: dict = Depends(require_role(ROLE_EDITOR))):
    if not is_enabled("ENABLE_API_KEYS"):
        raise HTTPException(400, "API keys are disabled")
    raw = "dck_" + secrets.token_urlsafe(36)
    key_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": key_id,
        "owner_id": user["id"],
        "name": body.name,
        "description": body.description or "",
        "key_hash": _hash(raw),
        "key_preview": _mask(raw),
        "created_at": now,
        "expires_days": body.expires_days,
        "call_count": 0,
        "revoked": False,
    }
    await api_keys.insert_one(doc)
    await log_event("api_key.created", actor_id=user["id"], actor_role=user["role"],
                    resource_type="api_key", resource_id=key_id, metadata={"name": body.name})
    doc.pop("_id", None)
    return {**doc, "key": raw, "warning": "This is the only time the full key will be shown. Save it now."}


@router.get("")
async def list_api_keys(user: dict = Depends(require_role(ROLE_EDITOR))):
    cursor = api_keys.find({"owner_id": user["id"]}, {"_id": 0, "key_hash": 0}).sort("created_at", -1)
    return await cursor.to_list(200)


@router.delete("/{key_id}")
async def revoke_api_key(key_id: str, user: dict = Depends(require_role(ROLE_EDITOR))):
    rec = await api_keys.find_one({"id": key_id}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "API key not found")
    if rec["owner_id"] != user["id"] and user["role"] not in ("admin", "owner"):
        raise HTTPException(403, "Forbidden")
    await api_keys.update_one(
        {"id": key_id},
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat()}},
    )
    await log_event("api_key.revoked", actor_id=user["id"], actor_role=user["role"],
                    resource_type="api_key", resource_id=key_id)
    return {"ok": True}
