"""Cross-encoder reranker.

Lazy-loads `sentence-transformers.CrossEncoder` when the flag is on. If the
package isn't installed we skip silently and return the original order, so
the rest of the platform still functions.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from core.config import is_enabled
from services import config_service

logger = logging.getLogger("docchat.retrieval.reranker")

_model: Optional[object] = None
_model_name: Optional[str] = None


def _load(model_name: str):
    global _model, _model_name
    if _model is not None and _model_name == model_name:
        return _model
    try:
        from sentence_transformers import CrossEncoder  # type: ignore
        _model = CrossEncoder(model_name)
        _model_name = model_name
        return _model
    except Exception as e:
        logger.warning("CrossEncoder unavailable (%s); reranker disabled", e)
        _model = None
        return None


def _score_sync(model, query: str, texts: list[str]) -> list[float]:
    pairs = [(query, t) for t in texts]
    return [float(s) for s in model.predict(pairs)]


def _confidence_bucket(score: float) -> str:
    if score > 5.0:
        return "HIGH"
    if score > 1.0:
        return "MEDIUM"
    return "LOW"


async def rerank(query: str, hits: list[dict], top_n: int = 5) -> list[dict]:
    if not is_enabled("ENABLE_RERANKER") or not hits:
        return hits[:top_n]
    model_name = await config_service.get_setting("reranker_model", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    model = _load(str(model_name))
    if model is None:
        return hits[:top_n]
    try:
        scores = await asyncio.to_thread(_score_sync, model, query, [h["text"] for h in hits])
        for h, s in zip(hits, scores):
            h["rerank_score"] = s
            h["rerank_confidence"] = _confidence_bucket(s)
        return sorted(hits, key=lambda h: h.get("rerank_score", 0.0), reverse=True)[:top_n]
    except Exception as e:
        logger.warning("rerank failed: %s", e)
        return hits[:top_n]
