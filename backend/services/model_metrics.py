"""Per-call LLM metrics — used by the Model Analytics dashboard.

Public surface kept tiny so the existing `chat_complete` wrapper can call
`record_call` from anywhere without re-importing chains of dependencies.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from core.db import model_metrics

logger = logging.getLogger("docchat.model_metrics")


async def record_call(
    *,
    model_id: str,
    provider: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = 0,
    cost_usd: float = 0.0,
    success: bool = True,
    error: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> None:
    try:
        await model_metrics.insert_one({
            "id": str(uuid.uuid4()),
            "model_id": model_id,
            "provider": provider,
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
            "total_tokens": int((prompt_tokens or 0) + (completion_tokens or 0)),
            "latency_ms": int(latency_ms or 0),
            "cost_usd": float(cost_usd or 0.0),
            "success": bool(success),
            "error": (error or "")[:300] or None,
            "owner_id": owner_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning("record_call failed: %s", e)


async def get_summary(days: int = 7, owner_id: Optional[str] = None) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    match: dict = {"created_at": {"$gte": cutoff}}
    if owner_id:
        match["owner_id"] = owner_id
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "calls": {"$sum": 1},
            "tokens": {"$sum": "$total_tokens"},
            "cost": {"$sum": "$cost_usd"},
            "errors": {"$sum": {"$cond": [{"$eq": ["$success", False]}, 1, 0]}},
            "avg_latency": {"$avg": "$latency_ms"},
        }},
    ]
    res = await model_metrics.aggregate(pipeline).to_list(1)
    if not res:
        return {"calls": 0, "tokens": 0, "cost": 0.0, "errors": 0, "avg_latency": 0, "error_rate": 0.0}
    r = res[0]
    calls = r.get("calls", 0)
    errors = r.get("errors", 0)
    return {
        "calls": calls,
        "tokens": r.get("tokens", 0),
        "cost": round(float(r.get("cost", 0.0)), 4),
        "errors": errors,
        "avg_latency": int(r.get("avg_latency") or 0),
        "error_rate": round(100.0 * errors / calls, 2) if calls else 0.0,
    }


async def by_model(days: int = 7, owner_id: Optional[str] = None) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    match: dict = {"created_at": {"$gte": cutoff}}
    if owner_id:
        match["owner_id"] = owner_id
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"model_id": "$model_id", "provider": "$provider"},
            "calls": {"$sum": 1},
            "tokens": {"$sum": "$total_tokens"},
            "cost": {"$sum": "$cost_usd"},
            "errors": {"$sum": {"$cond": [{"$eq": ["$success", False]}, 1, 0]}},
            "avg_latency": {"$avg": "$latency_ms"},
        }},
        {"$sort": {"calls": -1}},
    ]
    out = []
    async for r in model_metrics.aggregate(pipeline):
        calls = r.get("calls", 0)
        errors = r.get("errors", 0)
        out.append({
            "model_id": r["_id"]["model_id"],
            "provider": r["_id"]["provider"],
            "calls": calls,
            "tokens": r.get("tokens", 0),
            "cost": round(float(r.get("cost", 0.0)), 4),
            "errors": errors,
            "avg_latency": int(r.get("avg_latency") or 0),
            "success_rate": round(100.0 * (calls - errors) / calls, 2) if calls else 0.0,
        })
    return out


async def latency_percentiles(days: int = 7) -> list[dict]:
    """Approximate p50 / p90 / p99 per model using $bucket + $percentile (Mongo 7+) with a fallback."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out: list[dict] = []
    try:
        pipeline = [
            {"$match": {"created_at": {"$gte": cutoff}}},
            {"$group": {
                "_id": "$model_id",
                "p50": {"$percentile": {"input": "$latency_ms", "p": [0.5], "method": "approximate"}},
                "p90": {"$percentile": {"input": "$latency_ms", "p": [0.9], "method": "approximate"}},
                "p99": {"$percentile": {"input": "$latency_ms", "p": [0.99], "method": "approximate"}},
            }},
        ]
        async for r in model_metrics.aggregate(pipeline):
            out.append({
                "model_id": r["_id"],
                "p50": int((r.get("p50") or [0])[0]),
                "p90": int((r.get("p90") or [0])[0]),
                "p99": int((r.get("p99") or [0])[0]),
            })
        if out:
            return out
    except Exception:
        pass
    # Fallback — manual percentiles
    cursor = model_metrics.aggregate([
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$model_id", "latencies": {"$push": "$latency_ms"}}},
    ])
    async for r in cursor:
        arr = sorted(r.get("latencies") or [])
        if not arr:
            continue

        def pct(p):
            idx = max(0, min(len(arr) - 1, int(p * len(arr))))
            return arr[idx]
        out.append({"model_id": r["_id"], "p50": pct(0.5), "p90": pct(0.9), "p99": pct(0.99)})
    return out


async def daily_cost(days: int = 30) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    pipeline = [
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {
            "_id": {"day": {"$substr": ["$created_at", 0, 10]}, "model": "$model_id"},
            "cost": {"$sum": "$cost_usd"}, "calls": {"$sum": 1},
        }},
        {"$sort": {"_id.day": 1}},
    ]
    out: list[dict] = []
    async for r in model_metrics.aggregate(pipeline):
        out.append({
            "day": r["_id"]["day"],
            "model_id": r["_id"]["model"],
            "cost": round(float(r.get("cost", 0.0)), 4),
            "calls": r.get("calls", 0),
        })
    return out
