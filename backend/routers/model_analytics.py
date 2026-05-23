"""Model analytics router (Module 9) — admin-only aggregated LLM call metrics."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from core.deps import ROLE_ADMIN, require_role
from services import model_metrics

router = APIRouter(prefix="/v2/model-analytics", tags=["model-analytics"])


@router.get("/summary")
async def summary(days: int = Query(7, ge=1, le=365), _: dict = Depends(require_role(ROLE_ADMIN))):
    return await model_metrics.get_summary(days=days)


@router.get("/by-model")
async def per_model(days: int = Query(7, ge=1, le=365), _: dict = Depends(require_role(ROLE_ADMIN))):
    return await model_metrics.by_model(days=days)


@router.get("/latency")
async def latency(days: int = Query(7, ge=1, le=365), _: dict = Depends(require_role(ROLE_ADMIN))):
    return await model_metrics.latency_percentiles(days=days)


@router.get("/cost")
async def cost(days: int = Query(30, ge=1, le=365), _: dict = Depends(require_role(ROLE_ADMIN))):
    return await model_metrics.daily_cost(days=days)
