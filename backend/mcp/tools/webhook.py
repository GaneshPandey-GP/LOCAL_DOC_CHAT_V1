"""Built-in webhook tool — POSTs context payload to a configured webhook URL.

Looks up the webhook record in the `webhooks` collection by `webhook_id`.
Input: {"webhook_id": "...", "payload": {...}}
Output: {"status": int, "body": str|dict}
"""
from __future__ import annotations

import httpx

from core.db import webhooks


async def run(tool_input: dict) -> dict:
    wid = (tool_input or {}).get("webhook_id")
    payload = (tool_input or {}).get("payload") or {}
    if not wid:
        return {"error": "webhook_id required"}
    wh = await webhooks.find_one({"id": wid}, {"_id": 0})
    if not wh:
        return {"error": "webhook not found"}
    if wh.get("enabled") is False:
        return {"error": "webhook disabled"}
    url = wh.get("url")
    headers = wh.get("headers") or {}
    secret = wh.get("secret")
    if secret:
        headers["X-DocChat-Webhook-Secret"] = secret
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, json=payload, headers=headers)
    try:
        body = r.json()
    except Exception:
        body = (r.text or "")[:4000]
    return {"status": r.status_code, "body": body}
