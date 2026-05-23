"""Built-in web search tool — DuckDuckGo Instant Answer API.

Input:  {"query": "..."}
Output: {"abstract": "...", "results": [{"text": "...", "url": "..."}], "source": "duckduckgo"}
"""
from __future__ import annotations

import httpx


async def run(tool_input: dict) -> dict:
    q = (tool_input or {}).get("query", "").strip()
    if not q:
        return {"abstract": "", "results": [], "source": "duckduckgo"}
    url = "https://api.duckduckgo.com/"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params={"q": q, "format": "json", "no_html": 1, "skip_disambig": 1})
    data = resp.json() if resp.status_code == 200 else {}
    results = []
    for topic in (data.get("RelatedTopics") or [])[:5]:
        if isinstance(topic, dict) and topic.get("Text"):
            results.append({"text": topic["Text"], "url": topic.get("FirstURL", "")})
    return {
        "abstract": data.get("AbstractText", "") or data.get("Definition", ""),
        "results": results,
        "source": "duckduckgo",
    }
