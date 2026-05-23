"""Qdrant async client singleton.

Reads `qdrant_host` and `qdrant_port` from `config_service` (env > DB > default).
A cached `AsyncQdrantClient` is rebuilt only when the host/port pair changes.
All callers must use `get_client()` to avoid opening fresh TCP connections per
request. A liveness check is exposed via `health_check()` so endpoints can
degrade gracefully to 503 when Qdrant is unreachable.
"""
from __future__ import annotations

import logging
from typing import Optional

from services import config_service

logger = logging.getLogger("docchat.qdrant.client")

try:
    from qdrant_client import AsyncQdrantClient
    _QDRANT_AVAILABLE = True
except Exception:  # pragma: no cover — package optional at runtime
    AsyncQdrantClient = None  # type: ignore
    _QDRANT_AVAILABLE = False

_client: Optional["AsyncQdrantClient"] = None
_client_addr: Optional[str] = None


async def get_client() -> "AsyncQdrantClient":
    global _client, _client_addr
    if not _QDRANT_AVAILABLE:
        raise RuntimeError("qdrant-client is not installed")
    host = await config_service.get_setting("qdrant_host", "qdrant")
    port = int(await config_service.get_setting("qdrant_port", 6333))
    addr = f"{host}:{port}"
    if _client is None or _client_addr != addr:
        if _client is not None:
            try:
                await _client.close()
            except Exception:
                pass
        _client = AsyncQdrantClient(host=host, port=port, prefer_grpc=False, timeout=10)
        _client_addr = addr
        logger.info("Qdrant client connected → %s", addr)
    return _client


async def health_check() -> bool:
    """Ping Qdrant. Returns False on any failure (used by /health endpoints)."""
    if not _QDRANT_AVAILABLE:
        return False
    try:
        c = await get_client()
        # `get_collections` is the cheapest reachable call across versions
        await c.get_collections()
        return True
    except Exception as e:
        logger.warning("Qdrant health check failed: %s", e)
        return False
