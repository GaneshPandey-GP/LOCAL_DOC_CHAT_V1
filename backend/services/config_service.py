"""Centralized configuration resolver (Stream 3).

Priority chain for every key:
   1. process env (.env loaded at startup)         — wins always
   2. MongoDB `app_settings` collection            — runtime overrides
   3. Safe hardcoded default passed to get_setting — fallback

The resolver keeps a small in-process cache. Call invalidate_cache() after
mutating the DB to force a re-read on the next get().

Sensitive keys (postgres_password, *_api_key, *_secret, *_token) are NEVER
returned to non-admin callers via the public endpoint.
"""
import logging
import os
from typing import Any, Optional

from core.db import app_settings

logger = logging.getLogger("docchat.config_service")

# In-process cache: { key: value }.  Cleared on every write.
_cache: dict[str, Any] = {}
_cache_loaded: bool = False

# Keys that must NEVER be exposed to non-admin callers
SENSITIVE_KEY_TOKENS = (
    "password", "secret", "token", "api_key", "private", "credential",
)

# Default values for known configurable keys.  Defaults are applied only
# when neither .env nor DB has a value.
DEFAULT_SETTINGS: dict[str, Any] = {
    # URLs (Stream 3 surface area)
    "backend_base_url": "",
    "frontend_base_url": "",
    "api_base_url": "",
    # AI settings
    "llm_provider": "emergent",
    "llm_model": "gpt-4o-mini",
    "embedding_provider": "local",
    "embedding_model": "all-MiniLM-L6-v2",
    # Limits
    "upload_max_mb": 50,
    "query_row_cap": 1000,
    "streaming_chunk_size": 256,
    # DB Agent — Postgres connection (Stream 6)
    "db_agent_enabled": False,
    "db_agent_postgres_host": "",
    "db_agent_postgres_port": 5432,
    "db_agent_postgres_db": "",
    "db_agent_postgres_user": "",
    "db_agent_postgres_password": "",
    "db_agent_query_timeout_sec": 30,
    "db_agent_row_cap": 5000,
    "db_agent_allowed_schemas": "public",
    # DB Agent LLM override (falls back to active LLM config if blank)
    "db_agent_llm_provider": "",
    "db_agent_llm_model": "",
    "db_agent_llm_api_key": "",
    "db_agent_llm_base_url": "",
    # ── Enterprise AI Platform (Mar 2026) ─────────────────────────────────
    "qdrant_host": "/app/backend/uploads/qdrant_local",
    "qdrant_port": 6333,
    "qdrant_collection_prefix": "docchat",
    "dense_model": "BAAI/bge-small-en-v1.5",
    "sparse_model": "prithivida/Splade_PP_en_v1",
    "hybrid_dense_weight": 0.7,
    "hybrid_sparse_weight": 0.3,
    "similarity_threshold": 0.5,
    "retrieval_top_k": 5,
    "reranker_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "reranker_top_n": 5,
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "crawl_rate_limit_rps": 2,
    "crawl_max_depth": 3,
    "crawl_max_pages": 200,
    "crawl_user_agent": "DocChat-Crawler/1.0",
}


def _is_sensitive(key: str) -> bool:
    k = key.lower()
    return any(tok in k for tok in SENSITIVE_KEY_TOKENS)


def _env_key(setting_key: str) -> str:
    """Map a settings key to its env-var name (uppercase)."""
    return setting_key.upper()


async def _load_cache() -> None:
    """Populate the in-process cache from the DB once."""
    global _cache_loaded
    _cache.clear()
    try:
        async for doc in app_settings.find({}, {"_id": 0, "key": 1, "value": 1}):
            _cache[doc["key"]] = doc.get("value")
    except Exception as e:
        logger.warning("config_service: failed to load app_settings cache: %s", e)
    _cache_loaded = True


def invalidate_cache() -> None:
    """Force the next get_setting() to re-read the DB."""
    global _cache_loaded
    _cache_loaded = False
    _cache.clear()


async def get_setting(key: str, default: Optional[Any] = None) -> Any:
    """Resolve a setting following the .env > DB > default chain."""
    # 1) Env wins
    env_val = os.environ.get(_env_key(key))
    if env_val is not None and env_val != "":
        return _coerce(env_val, default if default is not None else DEFAULT_SETTINGS.get(key))

    # 2) DB (cached)
    if not _cache_loaded:
        await _load_cache()
    if key in _cache and _cache[key] is not None and _cache[key] != "":
        return _cache[key]

    # 3) Hardcoded default (param or built-in)
    if default is not None:
        return default
    return DEFAULT_SETTINGS.get(key)


def _coerce(raw: Any, hint: Any) -> Any:
    """Coerce a string env value into the type implied by the default."""
    if hint is None or isinstance(hint, str):
        return raw
    if isinstance(hint, bool):
        return str(raw).lower() in ("1", "true", "yes", "on")
    if isinstance(hint, int):
        try:
            return int(raw)
        except (ValueError, TypeError):
            return hint
    if isinstance(hint, float):
        try:
            return float(raw)
        except (ValueError, TypeError):
            return hint
    return raw


async def get_all_for_admin() -> dict[str, Any]:
    """Return the full merged config (with sensitive values UNMASKED) for owners."""
    if not _cache_loaded:
        await _load_cache()
    out: dict[str, Any] = {}
    for key, default in DEFAULT_SETTINGS.items():
        out[key] = await get_setting(key, default)
    # Include any extra keys present only in DB
    for k, v in _cache.items():
        if k not in out:
            out[k] = v
    return out


async def get_public_subset() -> dict[str, Any]:
    """Return only NON-sensitive, URL-style settings — safe for any authenticated user."""
    public_keys = (
        "backend_base_url", "frontend_base_url", "api_base_url",
        "upload_max_mb", "streaming_chunk_size",
    )
    out: dict[str, Any] = {}
    for k in public_keys:
        v = await get_setting(k, DEFAULT_SETTINGS.get(k))
        if not _is_sensitive(k):
            out[k] = v
    return out


async def set_setting(key: str, value: Any) -> None:
    """Upsert a single setting into the DB and invalidate cache."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    await app_settings.update_one(
        {"key": key},
        {"$set": {"key": key, "value": value, "updated_at": now}},
        upsert=True,
    )
    invalidate_cache()


async def delete_setting(key: str) -> None:
    """Remove a setting override so it falls back to env/default."""
    await app_settings.delete_one({"key": key})
    invalidate_cache()
