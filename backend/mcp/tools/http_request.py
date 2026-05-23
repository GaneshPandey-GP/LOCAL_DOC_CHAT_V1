"""Built-in generic HTTP request tool.

Input: {"method": "GET|POST|PUT|DELETE", "url": "...", "headers": {...}, "body": ...}
Output: {"status": int, "body": str|dict}
"""
from __future__ import annotations

import httpx


async def run(tool_input: dict) -> dict:
    method = (tool_input or {}).get("method", "GET").upper()
    url = (tool_input or {}).get("url")
    headers = (tool_input or {}).get("headers") or {}
    body = (tool_input or {}).get("body")
    if not url:
        return {"error": "url required"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        if method in ("GET", "DELETE"):
            r = await client.request(method, url, headers=headers)
        else:
            r = await client.request(method, url, headers=headers, json=body if isinstance(body, (dict, list)) else None,
                                     content=body if isinstance(body, (str, bytes)) else None)
    out = {"status": r.status_code}
    try:
        out["body"] = r.json()
    except Exception:
        out["body"] = (r.text or "")[:10000]
    return out
