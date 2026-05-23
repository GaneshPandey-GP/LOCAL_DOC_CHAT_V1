"""Named search strategies — invoked by KB configs via `get_strategy(mode)`.

Each strategy is `async (query, owner_id, doc_ids, kb_ids, top_k, config) -> list[dict]`.
"""
from __future__ import annotations

from typing import Callable, Optional

from services.qdrant import hybrid_search as hs


async def vector_search(query, owner_id, doc_ids=None, kb_ids=None, top_k=5, config=None):
    cfg = config or {}
    return await hs.vector_only_search(
        query, owner_id, doc_ids, kb_ids, top_k, threshold=float(cfg.get("similarity_threshold", 0.0) or 0.0)
    )


async def hybrid_strategy(query, owner_id, doc_ids=None, kb_ids=None, top_k=5, config=None):
    cfg = config or {}
    return await hs.search(
        query, owner_id, doc_ids=doc_ids, kb_ids=kb_ids,
        top_k=top_k,
        dense_weight=cfg.get("dense_weight"),
        sparse_weight=cfg.get("sparse_weight"),
        similarity_threshold=float(cfg.get("similarity_threshold", 0.0) or 0.0),
    )


async def bm25_search(query, owner_id, doc_ids=None, kb_ids=None, top_k=5, config=None):
    return await hs.keyword_search(query, owner_id, doc_ids, kb_ids, top_k)


async def similarity_search(query, owner_id, doc_ids=None, kb_ids=None, top_k=5, config=None):
    cfg = config or {}
    threshold = float(cfg.get("similarity_threshold", 0.7) or 0.7)
    return await hs.vector_only_search(query, owner_id, doc_ids, kb_ids, top_k, threshold=threshold)


async def ensemble_search(query, owner_id, doc_ids=None, kb_ids=None, top_k=5, config=None):
    # RRF-style fusion across the three pure strategies
    dense = await vector_search(query, owner_id, doc_ids, kb_ids, top_k * 2, config)
    sparse = await bm25_search(query, owner_id, doc_ids, kb_ids, top_k * 2, config)
    seen: dict[str, dict] = {}
    for rank_list in (dense, sparse):
        for r, h in enumerate(rank_list):
            cid = h["chunk_id"]
            score = 1.0 / (60 + r)
            if cid in seen:
                seen[cid]["fused_score"] = seen[cid].get("fused_score", 0.0) + score
            else:
                h["fused_score"] = score
                seen[cid] = h
    return sorted(seen.values(), key=lambda h: h["fused_score"], reverse=True)[:top_k]


async def multi_kb_search(query, owner_id, doc_ids=None, kb_ids=None, top_k=5, config=None):
    return await hybrid_strategy(query, owner_id, doc_ids=doc_ids, kb_ids=kb_ids, top_k=top_k, config=config)


_STRATEGIES: dict[str, Callable] = {
    "vector": vector_search,
    "hybrid": hybrid_strategy,
    "bm25": bm25_search,
    "similarity": similarity_search,
    "ensemble": ensemble_search,
    "multi_kb": multi_kb_search,
}


def get_strategy(mode: Optional[str]) -> Callable:
    return _STRATEGIES.get((mode or "hybrid").lower(), hybrid_strategy)
