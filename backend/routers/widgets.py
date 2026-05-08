"""Embed widget management — CRUD + analytics (owner/editor auth required)."""
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.audit import log_event
from core.config import is_enabled
from core.db import documents, embed_widgets, widget_events, widget_sessions
from core.deps import ROLE_EDITOR, require_role

router = APIRouter(prefix="/v2/widgets", tags=["widgets"])


def _check_flag():
    if not is_enabled("ENABLE_EMBED_WIDGET"):
        raise HTTPException(status_code=404, detail="Feature not enabled")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class WidgetConfig(BaseModel):
    # Appearance
    title: str = "Ask our Knowledge Base"
    subtitle: str = "Ask me anything about our docs..."
    brand_color: str = "#2563EB"
    logo_url: Optional[str] = None
    position: str = "bottom-right"  # bottom-right | bottom-left
    launcher_style: str = "icon"  # icon | icon-label
    dark_mode: bool = False
    # Behaviour
    welcome_message: str = "Hi! How can I help you today?"
    fallback_message: str = "I don't have enough information in the provided documents to answer that."
    max_questions_per_session: int = 0  # 0 = unlimited
    show_citations: bool = True
    show_confidence: bool = True
    allow_copy: bool = True
    email_collection: str = "off"  # off | optional | required


class CreateWidgetBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    document_ids: List[str] = Field(min_length=1)
    config: WidgetConfig = Field(default_factory=WidgetConfig)
    allowed_domains: List[str] = []
    rate_limit_hour: int = Field(default=20, ge=0)
    rate_limit_day: int = Field(default=500, ge=0)


class UpdateWidgetBody(BaseModel):
    name: Optional[str] = None
    document_ids: Optional[List[str]] = None
    config: Optional[WidgetConfig] = None
    allowed_domains: Optional[List[str]] = None
    rate_limit_hour: Optional[int] = None
    rate_limit_day: Optional[int] = None
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _public_widget(w: dict) -> dict:
    return {
        "id": w["id"],
        "widget_id": w["widget_id"],
        "name": w["name"],
        "config": w.get("config", {}),
        "allowed_domains": w.get("allowed_domains", []),
        "document_ids": w.get("document_ids", []),
        "rate_limit_hour": w.get("rate_limit_hour", 20),
        "rate_limit_day": w.get("rate_limit_day", 500),
        "is_active": w.get("is_active", True),
        "created_at": w["created_at"],
        "updated_at": w["updated_at"],
    }


async def _verify_doc_access(user: dict, doc_ids: List[str]) -> None:
    """Raise 403 if user doesn't have access to all doc_ids."""
    doc_query: Dict[str, Any] = {"id": {"$in": doc_ids}}
    if user["role"] != "owner":
        doc_query["owner_id"] = user["id"]
    found = await documents.find(doc_query, {"_id": 0, "id": 1}).to_list(500)
    found_ids = {d["id"] for d in found}
    missing = set(doc_ids) - found_ids
    if missing:
        raise HTTPException(status_code=403, detail=f"No access to documents: {sorted(missing)}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("")
async def create_widget(
    body: CreateWidgetBody,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    _check_flag()
    await _verify_doc_access(user, body.document_ids)

    widget_id = "wgt_" + uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).isoformat()
    w = {
        "id": str(uuid.uuid4()),
        "widget_id": widget_id,
        "owner_id": user["id"],
        "name": body.name,
        "config": body.config.dict(),
        "allowed_domains": body.allowed_domains,
        "document_ids": body.document_ids,
        "rate_limit_hour": body.rate_limit_hour,
        "rate_limit_day": body.rate_limit_day,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    await embed_widgets.insert_one(w)
    await log_event(
        "widget.create",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="widget",
        resource_id=widget_id,
        ip=request.client.host if request.client else None,
        metadata={"name": body.name, "doc_count": len(body.document_ids)},
    )
    return _public_widget(w)


@router.get("")
async def list_widgets(user: dict = Depends(require_role(ROLE_EDITOR))):
    _check_flag()
    query: Dict[str, Any] = {} if user["role"] == "owner" else {"owner_id": user["id"]}
    ws = await embed_widgets.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [_public_widget(w) for w in ws]


@router.get("/{widget_id}")
async def get_widget(widget_id: str, user: dict = Depends(require_role(ROLE_EDITOR))):
    _check_flag()
    query: Dict[str, Any] = {"widget_id": widget_id}
    if user["role"] != "owner":
        query["owner_id"] = user["id"]
    w = await embed_widgets.find_one(query, {"_id": 0})
    if not w:
        raise HTTPException(status_code=404, detail="Widget not found")
    return _public_widget(w)


@router.patch("/{widget_id}")
async def update_widget(
    widget_id: str,
    body: UpdateWidgetBody,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    _check_flag()
    query: Dict[str, Any] = {"widget_id": widget_id}
    if user["role"] != "owner":
        query["owner_id"] = user["id"]
    w = await embed_widgets.find_one(query, {"_id": 0})
    if not w:
        raise HTTPException(status_code=404, detail="Widget not found")

    updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if body.name is not None:
        updates["name"] = body.name
    if body.config is not None:
        updates["config"] = body.config.dict()
    if body.allowed_domains is not None:
        updates["allowed_domains"] = body.allowed_domains
    if body.document_ids is not None:
        await _verify_doc_access(user, body.document_ids)
        updates["document_ids"] = body.document_ids
    if body.rate_limit_hour is not None:
        updates["rate_limit_hour"] = body.rate_limit_hour
    if body.rate_limit_day is not None:
        updates["rate_limit_day"] = body.rate_limit_day
    if body.is_active is not None:
        updates["is_active"] = body.is_active

    await embed_widgets.update_one({"widget_id": widget_id}, {"$set": updates})
    updated = await embed_widgets.find_one({"widget_id": widget_id}, {"_id": 0})
    await log_event(
        "widget.update",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="widget",
        resource_id=widget_id,
        ip=request.client.host if request.client else None,
    )
    return _public_widget(updated)


@router.delete("/{widget_id}")
async def delete_widget(
    widget_id: str,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    _check_flag()
    query: Dict[str, Any] = {"widget_id": widget_id}
    if user["role"] != "owner":
        query["owner_id"] = user["id"]
    w = await embed_widgets.find_one(query, {"_id": 0})
    if not w:
        raise HTTPException(status_code=404, detail="Widget not found")

    await embed_widgets.update_one(
        {"widget_id": widget_id},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await log_event(
        "widget.delete",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="widget",
        resource_id=widget_id,
        ip=request.client.host if request.client else None,
    )
    return {"ok": True}


@router.get("/{widget_id}/analytics")
async def widget_analytics(widget_id: str, user: dict = Depends(require_role(ROLE_EDITOR))):
    _check_flag()
    query: Dict[str, Any] = {"widget_id": widget_id}
    if user["role"] != "owner":
        query["owner_id"] = user["id"]
    w = await embed_widgets.find_one(query, {"_id": 0})
    if not w:
        raise HTTPException(status_code=404, detail="Widget not found")

    total_sessions = await widget_sessions.count_documents({"widget_id": widget_id})
    total_queries = await widget_events.count_documents({"widget_id": widget_id, "event_type": "query_sent"})
    rate_limit_hits = await widget_events.count_documents({"widget_id": widget_id, "event_type": "rate_limited"})
    domain_blocks = await widget_events.count_documents({"widget_id": widget_id, "event_type": "domain_blocked"})

    # Top questions (anonymized)
    events = (
        await widget_events.find(
            {"widget_id": widget_id, "event_type": "query_sent"},
            {"_id": 0, "payload": 1},
        )
        .sort("created_at", -1)
        .to_list(200)
    )
    q_counter: Counter = Counter()
    for e in events:
        q = (e.get("payload") or {}).get("query", "")
        if q:
            q_counter[q[:200]] += 1
    top_questions = [{"query": q, "count": c} for q, c in q_counter.most_common(10)]

    # Unique visitors
    visitors = await widget_sessions.distinct("visitor_id", {"widget_id": widget_id})

    # Domain breakdown
    opened_events = (
        await widget_events.find(
            {"widget_id": widget_id, "event_type": "opened"},
            {"_id": 0, "payload": 1},
        )
        .to_list(1000)
    )
    domain_counter: Counter = Counter()
    for e in opened_events:
        d = (e.get("payload") or {}).get("domain", "unknown")
        domain_counter[d] += 1
    domain_breakdown = [{"domain": d, "count": c} for d, c in domain_counter.most_common(10)]

    avg_qps = round(total_queries / total_sessions, 2) if total_sessions else 0

    return {
        "widget_id": widget_id,
        "total_sessions": total_sessions,
        "unique_visitors": len(visitors),
        "total_queries": total_queries,
        "avg_queries_per_session": avg_qps,
        "rate_limit_hits": rate_limit_hits,
        "domain_blocks": domain_blocks,
        "top_questions": top_questions,
        "domain_breakdown": domain_breakdown,
    }
