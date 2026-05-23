"""High-level Qdrant retrieval pipeline: rewrite → search → dedup → rerank."""
from __future__ import annotations

import logging
from typing import Optional

from core.config import is_enabled

from .hybrid_search import search as hybrid_search, vector_only_search

logger = logging.getLogger("docchat.qdrant.retrieval")


async def retrieve(
    query: str,
    owner_id: str,
    doc_ids: Optional[list] = None,
    kb_ids: Optional[list] = None,
    top_k: int = 5,
    config: Optional[dict] = None,
) -> list[dict]:
    """Orchestrate the full retrieval pipeline. `config` is the KB / call config."""
    cfg = config or {}

    queries: list[str] = [query]
    if is_enabled("ENABLE_QUERY_REWRITER") and cfg.get("enable_query_rewriting") is not False:
        from services.retrieval.query_rewriter import rewrite_query
        queries = await rewrite_query(query)

    # Aggregate hits across rewritten queries (dedup by chunk_id, keep best score)
    seen: dict[str, dict] = {}
    threshold = float(cfg.get("similarity_threshold", 0.0) or 0.0)
    dense_w = cfg.get("dense_weight")
    sparse_w = cfg.get("sparse_weight")
    for q in queries:
        hits = await hybrid_search(
            q, owner_id, doc_ids=doc_ids, kb_ids=kb_ids,
            top_k=top_k, dense_weight=dense_w, sparse_weight=sparse_w,
            similarity_threshold=threshold,
        )
        for h in hits:
            existing = seen.get(h["chunk_id"])
            if existing is None or h["score"] > existing["score"]:
                seen[h["chunk_id"]] = h
    merged = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[: top_k * 2]

    # Optional cross-encoder reranking
    if is_enabled("ENABLE_RERANKER") and cfg.get("enable_reranking", True):
        from services.retrieval.reranker import rerank as _rerank
        merged = await _rerank(query, merged, top_n=top_k)
    else:
        merged = merged[:top_k]

    # Tag with confidence buckets (HIGH / MEDIUM / LOW) for the UI
    for h in merged:
        s = h.get("score", 0.0)
        h["confidence"] = "HIGH" if s >= 0.7 else ("MEDIUM" if s >= 0.4 else "LOW")
    return merged


async def multi_kb_search(
    query: str,
    owner_id: str,
    kb_ids: list,
    top_k: int = 5,
) -> list[dict]:
    """Search across multiple KBs in a single fused call."""
    return await retrieve(query, owner_id=owner_id, kb_ids=kb_ids, top_k=top_k)


async def rerank(query: str, hits: list[dict], top_n: int = 5) -> list[dict]:
    """Public passthrough so callers can rerank externally-built hit lists."""
    from services.retrieval.reranker import rerank as _rerank
    return await _rerank(query, hits, top_n=top_n)
