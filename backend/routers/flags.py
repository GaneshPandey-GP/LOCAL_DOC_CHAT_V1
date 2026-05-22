"""Feature-flags endpoints.

Two routers exported from this module:

  router       — prefix /v2   (read-only, any authenticated user)
                 GET  /api/v2/flags      → current flag values   [Settings.jsx]
                 GET  /api/v2/providers  → LLM/embedding info    [Settings.jsx]

  admin_router — prefix /admin/flags  (owner-only CRUD)
                 GET    /api/admin/flags/          → list flags + overrides
                 PATCH  /api/admin/flags/{name}    → toggle single flag
                 POST   /api/admin/flags/reset     → revert to env defaults
"""
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.config import (
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    FEATURE_FLAGS,
    LLM_MODEL,
    LLM_PROVIDER,
)
from core.deps import ROLE_OWNER, get_current_user, require_role

# ── Read-only router (backward compat) ────────────────────────────────────────
router = APIRouter(prefix="/v2", tags=["flags"])


@router.get("/flags")
async def get_flags(_: dict = Depends(get_current_user)):
    return FEATURE_FLAGS


@router.get("/providers")
async def get_providers(_: dict = Depends(get_current_user)):
    return {
        "llm": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
        "embedding": {"provider": EMBEDDING_PROVIDER, "model": EMBEDDING_MODEL},
    }


# ── Admin CRUD router (owner-only) ────────────────────────────────────────────
admin_router = APIRouter(prefix="/admin/flags", tags=["admin"])

# Capture the original (env-resolved) defaults at module import time, BEFORE any
# runtime PATCH mutates FEATURE_FLAGS. This is the source-of-truth for reset().
_ORIGINAL_FLAGS: Dict[str, bool] = dict(FEATURE_FLAGS)

# Runtime overrides — process-lifetime only; reset on server restart
_runtime_overrides: Dict[str, bool] = {}


class FlagUpdate(BaseModel):
    value: bool


@admin_router.get("/")
async def list_flags(_: dict = Depends(require_role(ROLE_OWNER))):
    """Return all feature flags with their current effective values."""
    merged = {k: _runtime_overrides.get(k, v) for k, v in FEATURE_FLAGS.items()}
    return {
        "flags": merged,
        "overrides": _runtime_overrides,
        "note": "Overrides are runtime-only and reset on server restart unless persisted to .env",
    }


@admin_router.patch("/{flag_name}")
async def update_flag(
    flag_name: str,
    body: FlagUpdate,
    _: dict = Depends(require_role(ROLE_OWNER)),
):
    """Toggle a single feature flag at runtime."""
    if flag_name not in FEATURE_FLAGS:
        raise HTTPException(status_code=404, detail=f"Flag '{flag_name}' not found")
    _runtime_overrides[flag_name] = body.value
    # Patch the live dict so is_enabled() reflects the change immediately
    FEATURE_FLAGS[flag_name] = body.value
    return {"flag": flag_name, "value": body.value, "status": "updated"}


@admin_router.post("/reset")
async def reset_flags(_: dict = Depends(require_role(ROLE_OWNER))):
    """Reset all runtime overrides back to the original env-resolved defaults."""
    _runtime_overrides.clear()
    for k, v in _ORIGINAL_FLAGS.items():
        FEATURE_FLAGS[k] = v
    return {"status": "reset", "flags": dict(FEATURE_FLAGS)}
