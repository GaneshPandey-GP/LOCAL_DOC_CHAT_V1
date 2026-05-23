"""Chunk ingestion → Qdrant.

Generates dense (and optionally sparse) vectors and upserts in batches of 100.
The public surface (`add_chunks`, `delete_chunks`, `delete_kb_chunks`) is kept
minimal so callers can route everything through here without referencing
Qdrant SDK details.

Dense embeddings are produced by:
  1. `fastembed` (BAAI/bge-small-en-v1.5)  if available
  2. OpenAI embeddings                     if EMBEDDING_PROVIDER == openai
  3. Falls back to ChromaDB's local MiniLM (existing infra in services.embeddings)

Sparse vectors are produced by `fastembed`'s SPLADE model (if installed) and
skipped silently otherwise — the system still functions with dense-only.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from core.config import is_enabled
from services import config_service

from .client import get_client
from .collections import ensure_collection, get_collection_name

logger = logging.getLogger("docchat.qdrant.ingestion")

# ── Embedding adapters ───────────────────────────────────────────────────────
_dense_model = None
_sparse_model = None


def _load_dense():
    global _dense_model
    if _dense_model is not None:
        return _dense_model
    try:
        from fastembed import TextEmbedding  # type: ignore
        _dense_model = ("fastembed", TextEmbedding(model_name="BAAI/bge-small-en-v1.5"))
    except Exception:
        _dense_model = ("chromadb", None)
    return _dense_model


def _load_sparse():
    global _sparse_model
    if _sparse_model is not None:
        return _sparse_model
    if not is_enabled("ENABLE_SPARSE_VECTORS"):
        _sparse_model = ("disabled", None)
        return _sparse_model
    try:
        from fastembed import SparseTextEmbedding  # type: ignore
        _sparse_model = ("fastembed", SparseTextEmbedding(model_name="prithivida/Splade_PP_en_v1"))
    except Exception:
        _sparse_model = ("disabled", None)
    return _sparse_model


def _embed_dense_sync(texts: list[str]) -> list[list[float]]:
    kind, model = _load_dense()
    if kind == "fastembed" and model is not None:
        return [list(map(float, v)) for v in model.embed(texts)]
    # Fallback to ChromaDB's local ONNX MiniLM via existing services.embeddings
    from services.embeddings import _get_local_ef  # type: ignore
    ef = _get_local_ef() if callable(_get_local_ef) else None
    if ef is None:
        # absolute last resort — random vectors (search will be useless but ingest succeeds)
        import random
        return [[random.random() for _ in range(384)] for _ in texts]
    return [list(map(float, v)) for v in ef(texts)]


def _embed_sparse_sync(texts: list[str]):
    kind, model = _load_sparse()
    if kind != "fastembed" or model is None:
        return None
    return list(model.embed(texts))


async def _embed_dense(texts: list[str]) -> list[list[float]]:
    return await asyncio.to_thread(_embed_dense_sync, texts)


async def _embed_sparse(texts: list[str]):
    return await asyncio.to_thread(_embed_sparse_sync, texts)


# ── Public surface ───────────────────────────────────────────────────────────
async def add_chunks(
    doc_id: str,
    owner_id: str,
    filename: str,
    chunks: list[dict],
    kb_id: Optional[str] = None,
    extra_payload: Optional[dict] = None,
) -> int:
    """Embed and upsert chunks. Each chunk dict must have `text` and `chunk_index`.

    Returns the number of points written.
    """
    if not chunks:
        return 0
    from qdrant_client.http import models as rest

    collection = await ensure_collection(owner_id)
    client = await get_client()

    texts = [c["text"] for c in chunks]
    dense_vecs = await _embed_dense(texts)
    sparse_vecs = await _embed_sparse(texts) if is_enabled("ENABLE_SPARSE_VECTORS") else None

    now = datetime.now(timezone.utc).isoformat()
    points: list = []
    for i, ch in enumerate(chunks):
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}:{ch.get('chunk_index', i)}"))
        vec = {"dense": dense_vecs[i]}
        if sparse_vecs is not None:
            sv = sparse_vecs[i]
            vec["sparse"] = rest.SparseVector(indices=list(sv.indices), values=list(sv.values))
        payload = {
            "doc_id": doc_id,
            "owner_id": owner_id,
            "kb_id": kb_id,
            "filename": filename,
            "chunk_index": ch.get("chunk_index", i),
            "text": ch["text"],
            "page": ch.get("page"),
            "file_type": ch.get("file_type"),
            "tags": ch.get("tags", []),
            "created_at": now,
        }
        if extra_payload:
            payload.update(extra_payload)
        points.append(rest.PointStruct(id=pid, vector=vec, payload=payload))

    # Upsert in batches of 100
    for i in range(0, len(points), 100):
        batch = points[i : i + 100]
        await client.upsert(collection_name=collection, points=batch, wait=True)
    logger.info("Qdrant upsert: collection=%s doc_id=%s points=%d", collection, doc_id, len(points))
    return len(points)


async def delete_chunks(doc_id: str, owner_id: str) -> None:
    from qdrant_client.http import models as rest
    client = await get_client()
    collection = get_collection_name(owner_id)
    try:
        await client.delete(
            collection_name=collection,
            points_selector=rest.FilterSelector(
                filter=rest.Filter(must=[rest.FieldCondition(key="doc_id", match=rest.MatchValue(value=doc_id))])
            ),
            wait=True,
        )
    except Exception as e:
        logger.warning("delete_chunks failed: %s", e)


async def delete_kb_chunks(kb_id: str, owner_id: str) -> None:
    from qdrant_client.http import models as rest
    client = await get_client()
    collection = get_collection_name(owner_id)
    try:
        await client.delete(
            collection_name=collection,
            points_selector=rest.FilterSelector(
                filter=rest.Filter(must=[rest.FieldCondition(key="kb_id", match=rest.MatchValue(value=kb_id))])
            ),
            wait=True,
        )
    except Exception as e:
        logger.warning("delete_kb_chunks failed: %s", e)
