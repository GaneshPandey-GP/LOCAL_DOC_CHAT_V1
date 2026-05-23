"""Per-tenant Qdrant collection lifecycle.

Each owner_id gets a namespaced collection like `docchat_<owner_id>`. Collections
expose a dense vector field (cosine) and an optional sparse field (dot product)
when sparse vectors are enabled. Payload indexing is enabled for the keys we
filter on most often (doc_id, owner_id, kb_id, chunk_index).
"""
from __future__ import annotations

import logging
from typing import Optional

from core.config import is_enabled
from services import config_service

from .client import get_client

logger = logging.getLogger("docchat.qdrant.collections")

# Most local embedding models we ship default to 384-d (MiniLM-L6, bge-small).
# OpenAI text-embedding-3-small is 1536-d. We resolve via env / settings so the
# operator can switch without code changes.
DEFAULT_DENSE_SIZE = 384


def _dense_size_for(model_name: str) -> int:
    name = (model_name or "").lower()
    if "text-embedding-3-large" in name:
        return 3072
    if "text-embedding-3-small" in name or "text-embedding-ada" in name:
        return 1536
    if "bge-large" in name:
        return 1024
    if "bge-base" in name or "mpnet-base" in name:
        return 768
    return DEFAULT_DENSE_SIZE


def get_collection_name(owner_id: str) -> str:
    """Namespaced collection per owner for cheap tenant isolation."""
    prefix = "docchat"
    # synchronous accessor — read from env only; we don't want to await here
    import os
    prefix = os.environ.get("QDRANT_COLLECTION_PREFIX", prefix)
    safe = (owner_id or "shared").replace("-", "").replace("_", "")[:40]
    return f"{prefix}_{safe}"


async def list_collections() -> list[str]:
    c = await get_client()
    res = await c.get_collections()
    return [col.name for col in res.collections]


async def ensure_collection(owner_id: str, dense_size: Optional[int] = None) -> str:
    """Idempotent — creates the collection if missing, returns its name."""
    from qdrant_client.http import models as rest

    name = get_collection_name(owner_id)
    c = await get_client()
    cols = {col.name for col in (await c.get_collections()).collections}
    if name in cols:
        return name

    model = await config_service.get_setting("dense_model", "BAAI/bge-small-en-v1.5")
    size = dense_size or _dense_size_for(str(model))

    sparse_enabled = is_enabled("ENABLE_SPARSE_VECTORS")
    vectors_config = {
        "dense": rest.VectorParams(size=size, distance=rest.Distance.COSINE),
    }
    sparse_vectors_config = None
    if sparse_enabled:
        sparse_vectors_config = {
            "sparse": rest.SparseVectorParams(
                index=rest.SparseIndexParams(on_disk=False),
            ),
        }

    await c.create_collection(
        collection_name=name,
        vectors_config=vectors_config,
        sparse_vectors_config=sparse_vectors_config,
    )
    # Payload indexes — speed up filtered searches
    for field, schema in (
        ("doc_id", rest.PayloadSchemaType.KEYWORD),
        ("owner_id", rest.PayloadSchemaType.KEYWORD),
        ("kb_id", rest.PayloadSchemaType.KEYWORD),
        ("chunk_index", rest.PayloadSchemaType.INTEGER),
    ):
        try:
            await c.create_payload_index(collection_name=name, field_name=field, field_schema=schema)
        except Exception as e:
            logger.debug("payload index create skipped for %s.%s: %s", name, field, e)
    logger.info("Qdrant collection ready: %s (dense=%d, sparse=%s)", name, size, sparse_enabled)
    return name


async def delete_collection(owner_id: str) -> None:
    c = await get_client()
    try:
        await c.delete_collection(get_collection_name(owner_id))
    except Exception as e:
        logger.warning("delete_collection failed for %s: %s", owner_id, e)
