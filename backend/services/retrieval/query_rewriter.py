"""LLM-driven query rewriter — returns N alternative phrasings for retrieval."""
from __future__ import annotations

import json
import logging
import re

from core.config import is_enabled

logger = logging.getLogger("docchat.retrieval.query_rewriter")

PROMPT = (
    "Rewrite the following user search query into 3 alternative phrasings that "
    "would improve recall on a hybrid (dense + sparse) retrieval system. "
    "Return ONLY a JSON array of 3 strings, no commentary.\n\nQuery: {q}"
)


async def rewrite_query(query: str) -> list[str]:
    if not is_enabled("ENABLE_QUERY_REWRITER"):
        return [query]
    try:
        from services.llm import chat_complete
        raw = await chat_complete([
            {"role": "system", "content": "You are a search query rewriter."},
            {"role": "user", "content": PROMPT.format(q=query)},
        ])
        m = re.search(r"\[.*\]", raw or "", re.DOTALL)
        if not m:
            return [query]
        variants = json.loads(m.group(0))
        if isinstance(variants, list):
            return [query] + [str(v) for v in variants[:3] if v]
    except Exception as e:
        logger.warning("query rewriter failed: %s", e)
    return [query]
