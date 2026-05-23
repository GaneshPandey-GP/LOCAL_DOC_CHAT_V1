"""Hybrid (dense + sparse) retrieval against Qdrant.

When `ENABLE_QDRANT_HYBRID` is on, runs two prefetches (dense via cosine, sparse
via dot product) and lets Qdrant's native `Query.fusion=RRF` merge them.

Falls back to dense-only when sparse vectors are disabled or unavailable.
Returns a list of hit dicts with a stable shape:
   {chunk_id, text, score, doc_id, filename, page, chunk_index, kb_id}
"""
from __future__ import annotations

import logging
from typing import Optional

from core.config import is_enabled
from services import config_service

from .client import get_client
from .collections import get_collection_name
from .ingestion import _embed_dense, _embed_sparse

logger = logging.getLogger("docchat.qdrant.hybrid_search")


def _build_filter(owner_id: str, doc_ids: Optional[list], kb_ids: Optional[list]):
    from qdrant_client.http import models as rest
    must: list = [rest.FieldCondition(key="owner_id", match=rest.MatchValue(value=owner_id))]
    if doc_ids:
        must.append(rest.FieldCondition(key="doc_id", match=rest.MatchAny(any=doc_ids)))
    if kb_ids:
        must.append(rest.FieldCondition(key="kb_id", match=rest.MatchAny(any=kb_ids)))
    return rest.Filter(must=must)


def _hit_to_dict(point) -> dict:
    p = point.payload or {}
    return {
        "chunk_id": str(point.id),
        "text": p.get("text", ""),
        "score": float(getattr(point, "score", 0.0)),
        "doc_id": p.get("doc_id"),
        "filename": p.get("filename"),
        "page": p.get("page"),
        "chunk_index": p.get("chunk_index"),
        "kb_id": p.get("kb_id"),
        "tags": p.get("tags", []),
    }


async def vector_only_search(
    query: str,
    owner_id: str,
    doc_ids: Optional[list] = None,
    kb_ids: Optional[list] = None,
    top_k: int = 5,
    threshold: float = 0.0,
) -> list[dict]:
    client = await get_client()
    name = get_collection_name(owner_id)
    qvec = (await _embed_dense([query]))[0]
    res = await client.query_points(
        collection_name=name,
        query=qvec,
        using="dense",
        query_filter=_build_filter(owner_id, doc_ids, kb_ids),
        limit=top_k,
        score_threshold=threshold or None,
        with_payload=True,
    )
    return [_hit_to_dict(p) for p in res.points]


async def keyword_search(
    query: str,
    owner_id: str,
    doc_ids: Optional[list] = None,
    kb_ids: Optional[list] = None,
    top_k: int = 5,
) -> list[dict]:
    if not is_enabled("ENABLE_SPARSE_VECTORS"):
        return await vector_only_search(query, owner_id, doc_ids, kb_ids, top_k)
    from qdrant_client.http import models as rest

    client = await get_client()
    name = get_collection_name(owner_id)
    sparse = await _embed_sparse([query])
    if not sparse:
        return await vector_only_search(query, owner_id, doc_ids, kb_ids, top_k)
    sv = sparse[0]
    res = await client.query_points(
        collection_name=name,
        query=rest.SparseVector(indices=list(sv.indices), values=list(sv.values)),
        using="sparse",
        query_filter=_build_filter(owner_id, doc_ids, kb_ids),
        limit=top_k,
        with_payload=True,
    )
    return [_hit_to_dict(p) for p in res.points]


async def search(
    query: str,
    owner_id: str,
    doc_ids: Optional[list] = None,
    kb_ids: Optional[list] = None,
    top_k: int = 5,
    dense_weight: Optional[float] = None,
    sparse_weight: Optional[float] = None,
    similarity_threshold: float = 0.0,
    filters: Optional[dict] = None,  # reserved for future payload filters
) -> list[dict]:
    if not is_enabled("ENABLE_QDRANT_HYBRID") or not is_enabled("ENABLE_SPARSE_VECTORS"):
        return await vector_only_search(query, owner_id, doc_ids, kb_ids, top_k, similarity_threshold)

    from qdrant_client.http import models as rest
    client = await get_client()
    name = get_collection_name(owner_id)

    dvec = (await _embed_dense([query]))[0]
    sparse = await _embed_sparse([query])
    if not sparse:
        return await vector_only_search(query, owner_id, doc_ids, kb_ids, top_k, similarity_threshold)
    sv = sparse[0]

    flt = _build_filter(owner_id, doc_ids, kb_ids)
    prefetch_k = max(top_k * 4, 20)
    res = await client.query_points(
        collection_name=name,
        prefetch=[
            rest.Prefetch(query=dvec, using="dense", filter=flt, limit=prefetch_k),
            rest.Prefetch(
                query=rest.SparseVector(indices=list(sv.indices), values=list(sv.values)),
                using="sparse", filter=flt, limit=prefetch_k,
            ),
        ],
        query=rest.FusionQuery(fusion=rest.Fusion.RRF),
        limit=top_k,
        with_payload=True,
    )
    hits = [_hit_to_dict(p) for p in res.points]
    if similarity_threshold and similarity_threshold > 0:
        hits = [h for h in hits if h["score"] >= similarity_threshold]
    return hits
