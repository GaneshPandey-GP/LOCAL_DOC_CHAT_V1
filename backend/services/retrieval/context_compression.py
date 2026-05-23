"""LLM-based context compression: drop irrelevant chunks, trim to token budget."""
from __future__ import annotations

import logging

logger = logging.getLogger("docchat.retrieval.context_compression")


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


async def compress(query: str, chunks: list[dict], max_tokens: int = 3000) -> list[dict]:
    """Greedy compression — keep top-relevant chunks until we hit `max_tokens`."""
    if not chunks:
        return []
    # Cheap heuristic: rank by score, then add until budget exhausted.
    ranked = sorted(chunks, key=lambda c: c.get("score", 0.0), reverse=True)
    out: list[dict] = []
    used = 0
    for c in ranked:
        cost = _approx_tokens(c.get("text", ""))
        if used + cost > max_tokens:
            continue
        out.append(c)
        used += cost
    return out
