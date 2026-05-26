"""Knowledge Base management router (Module 2).

Mounted at /api/v2/kb. All routes use the canonical core.deps RBAC dependencies.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.audit import log_event
from core.config import is_enabled
from core.db import crawl_history, crawl_jobs, documents, knowledge_bases, sync_schedules
from core.deps import ROLE_ADMIN, ROLE_EDITOR, get_current_user, require_role
from services.qdrant.collections import ensure_collection
from services.qdrant.ingestion import delete_kb_chunks
from services.retrieval.search_strategies import get_strategy

router = APIRouter(prefix="/v2/kb", tags=["knowledge-base"])


# ── Models ───────────────────────────────────────────────────────────────────
class KBCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=256)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    type: str = Field(default="document")  # document | web | hybrid
    web_root_url: Optional[str] = None
    sitemap_url: Optional[str] = None
    selector: Optional[str] = None
    exclude_selectors: List[str] = Field(default_factory=list)
    search_mode: str = "hybrid"  # vector | hybrid | similarity | bm25 | ensemble
    similarity_threshold: float = 0.5
    top_k: int = 5
    chunk_size: int = 1000
    chunk_overlap: int = 200
    dense_weight: float = 0.7
    sparse_weight: float = 0.3
    enable_reranking: bool = False
    enable_query_rewriting: bool = False


class KBUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    embedding_model: Optional[str] = None
    type: Optional[str] = None
    web_root_url: Optional[str] = None
    sitemap_url: Optional[str] = None
    selector: Optional[str] = None
    exclude_selectors: Optional[List[str]] = None
    search_mode: Optional[str] = None
    similarity_threshold: Optional[float] = None
    top_k: Optional[int] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    dense_weight: Optional[float] = None
    sparse_weight: Optional[float] = None
    enable_reranking: Optional[bool] = None
    enable_query_rewriting: Optional[bool] = None


class CrawlConfig(BaseModel):
    type: str = "recursive"  # recursive | sitemap | single
    url: Optional[str] = None
    depth: int = 3
    max_pages: int = 200
    respect_robots: bool = True
    rate_limit_rps: float = 2.0
    selector: Optional[str] = None
    use_playwright: bool = False


class ScheduleCreate(BaseModel):
    cron_expr: str
    enabled: bool = True
    crawl_config: CrawlConfig


class SearchQuery(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    mode: Optional[str] = None
    top_k: Optional[int] = None
    similarity_threshold: Optional[float] = None


# ── Helpers ──────────────────────────────────────────────────────────────────
def _is_admin(user: dict) -> bool:
    return user.get("role") in (ROLE_ADMIN, "owner")


async def _get_owned_kb(kb_id: str, user: dict, require_owner: bool = False) -> dict:
    kb = await knowledge_bases.find_one({"id": kb_id}, {"_id": 0})
    if not kb:
        raise HTTPException(404, "Knowledge base not found")
    if not _is_admin(user) and kb["owner_id"] != user["id"]:
        if require_owner:
            raise HTTPException(403, "Forbidden")
        # editors may read KBs owned by anyone (used for shared workflows)
    return kb


# ── Endpoints ────────────────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_kb(body: KBCreate, request: Request, user: dict = Depends(require_role(ROLE_EDITOR))):
    kb_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": kb_id,
        "owner_id": user["id"],
        "created_at": now,
        "chunk_count": 0,
        "document_count": 0,
        **body.model_dump(),
    }
    await knowledge_bases.insert_one(doc)
    try:
        await ensure_collection(user["id"])
    except Exception:
        pass
    await log_event("kb.created", actor_id=user["id"], actor_role=user["role"], resource_type="kb", resource_id=kb_id,
                    ip=request.client.host if request.client else None, metadata={"name": body.name, "type": body.type})
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_kbs(user: dict = Depends(get_current_user)):
    q: dict = {} if _is_admin(user) else {"owner_id": user["id"]}
    cursor = knowledge_bases.find(q, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(500)


@router.get("/schedules/all")
async def list_all_schedules(_: dict = Depends(require_role(ROLE_ADMIN))):
    return await sync_schedules.find({}, {"_id": 0}).to_list(500)


@router.get("/{kb_id}")
async def get_kb(kb_id: str, user: dict = Depends(get_current_user)):
    return await _get_owned_kb(kb_id, user)


@router.patch("/{kb_id}")
async def update_kb(kb_id: str, body: KBUpdate, user: dict = Depends(require_role(ROLE_EDITOR))):
    kb = await _get_owned_kb(kb_id, user, require_owner=True)
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if not upd:
        return kb
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    await knowledge_bases.update_one({"id": kb_id}, {"$set": upd})
    out = await knowledge_bases.find_one({"id": kb_id}, {"_id": 0})
    return out


@router.delete("/{kb_id}")
async def delete_kb(kb_id: str, request: Request, user: dict = Depends(require_role(ROLE_EDITOR))):
    kb = await _get_owned_kb(kb_id, user, require_owner=True)
    await knowledge_bases.delete_one({"id": kb_id})
    await crawl_jobs.delete_many({"kb_id": kb_id})
    await crawl_history.delete_many({"kb_id": kb_id})
    await sync_schedules.delete_many({"kb_id": kb_id})
    await documents.delete_many({"kb_id": kb_id})
    try:
        await delete_kb_chunks(kb_id, kb["owner_id"])
    except Exception:
        pass
    await log_event("kb.deleted", actor_id=user["id"], actor_role=user["role"], resource_type="kb", resource_id=kb_id,
                    ip=request.client.host if request.client else None)
    return {"ok": True}


@router.post("/{kb_id}/crawl")
async def start_crawl(
    kb_id: str,
    body: CrawlConfig,
    background_tasks: BackgroundTasks,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    if not is_enabled("ENABLE_WEB_CRAWLER"):
        raise HTTPException(400, "Web crawler is disabled (ENABLE_WEB_CRAWLER=false)")
    # Preflight: crawled pages are written to Qdrant. If Qdrant is unreachable
    # we fail fast with a clear message instead of letting the background task
    # die mid-pipeline.
    from services.qdrant.client import health_check as _qhealth
    if not await _qhealth():
        raise HTTPException(
            503,
            "Vector store (Qdrant) is unreachable. Start the Qdrant container "
            "(docker compose -f docker-compose.qdrant.yml up -d qdrant) and "
            "set QDRANT_HOST in backend .env before launching a crawl.",
        )
    kb = await _get_owned_kb(kb_id, user, require_owner=True)

    # Reject if a job is already running for this KB
    running = await crawl_jobs.find_one({"kb_id": kb_id, "status": {"$in": ["queued", "running"]}}, {"_id": 0, "id": 1})
    if running:
        raise HTTPException(409, "A crawl job is already running for this KB")

    # URL reachability preflight (HEAD with short timeout). Fail-fast with 422.
    probe_url = body.url or kb.get("web_root_url") or kb.get("sitemap_url")
    if probe_url:
        import httpx as _httpx
        try:
            async with _httpx.AsyncClient(follow_redirects=True, timeout=10.0) as _c:
                _r = await _c.head(probe_url)
                if _r.status_code >= 400:
                    # Some servers don't support HEAD — retry with GET
                    _r = await _c.get(probe_url)
                if _r.status_code >= 400:
                    raise HTTPException(422, f"URL unreachable: {probe_url} responded {_r.status_code}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(422, f"URL unreachable: {probe_url} ({type(e).__name__}: {str(e)[:160]})")

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    job_doc = {
        "id": job_id, "kb_id": kb_id, "owner_id": kb["owner_id"],
        "status": "queued", "config": body.model_dump(),
        "pages_found": 0, "pages_crawled": 0, "pages_failed": 0, "pages_skipped": 0,
        "failed_urls": [],
        "queued_at": now,
    }
    await crawl_jobs.insert_one(job_doc)
    # Defer the heavy import to keep router startup cheap. BackgroundTasks
    # expects a callable + args — NOT a pre-awaited coroutine.
    from services.web_crawler.pipeline import run_crawl_job
    background_tasks.add_task(run_crawl_job, job_id)
    await log_event("kb.crawl.started", actor_id=user["id"], actor_role=user["role"],
                    resource_type="kb", resource_id=kb_id,
                    ip=request.client.host if request.client else None,
                    metadata={"job_id": job_id, "type": body.type})
    job_doc.pop("_id", None)
    return job_doc


@router.post("/{kb_id}/crawl/cancel")
async def cancel_crawl(
    kb_id: str,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    """Signal the active job to stop after the page currently in flight."""
    await _get_owned_kb(kb_id, user, require_owner=True)
    job = await crawl_jobs.find_one(
        {"kb_id": kb_id, "status": {"$in": ["queued", "running"]}}, {"_id": 0}, sort=[("queued_at", -1)],
    )
    if not job:
        raise HTTPException(404, "No active crawl to cancel")
    await crawl_jobs.update_one(
        {"id": job["id"]},
        {"$set": {"status": "cancelled", "ended_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "job_id": job["id"]}


@router.post("/{kb_id}/crawl/preview")
async def preview_crawl(
    kb_id: str,
    body: CrawlConfig,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    """Fetch a single URL and return the extracted markdown preview without ingesting.

    Useful for end-users dialling in `selector` / `exclude_selectors` before
    committing to a full crawl.
    """
    kb = await _get_owned_kb(kb_id, user)
    url = body.url or kb.get("web_root_url")
    if not url:
        raise HTTPException(422, "No URL provided and KB has no web_root_url")
    from services.web_crawler.crawler import WebCrawler
    crawler = WebCrawler(user_agent="DocChat-Crawler/1.0")
    try:
        page = await crawler.fetch_single(url, body.selector or kb.get("selector"), kb.get("exclude_selectors") or [])
    except Exception as e:
        raise HTTPException(422, f"Preview failed: {str(e)[:200]}")
    if not page:
        raise HTTPException(422, f"URL did not return usable HTML content: {url}")
    return {
        "url": page.url,
        "title": page.title,
        "content_preview": page.content[:500],
        "word_count": len(page.content.split()),
        "status_code": page.status_code,
    }


@router.get("/{kb_id}/crawl/status")
async def crawl_status(kb_id: str, user: dict = Depends(get_current_user)):
    await _get_owned_kb(kb_id, user)
    job = await crawl_jobs.find_one({"kb_id": kb_id}, {"_id": 0}, sort=[("queued_at", -1)])
    return job or {"status": "none"}


@router.get("/{kb_id}/crawl/history")
async def crawl_history_list(kb_id: str, limit: int = Query(50, le=200), user: dict = Depends(get_current_user)):
    await _get_owned_kb(kb_id, user)
    cursor = crawl_jobs.find({"kb_id": kb_id}, {"_id": 0}).sort("queued_at", -1).limit(limit)
    return await cursor.to_list(limit)


@router.post("/{kb_id}/crawl/retry")
async def retry_crawl(
    kb_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    await _get_owned_kb(kb_id, user, require_owner=True)
    last = await crawl_jobs.find_one({"kb_id": kb_id, "status": "failed"}, {"_id": 0}, sort=[("queued_at", -1)])
    if not last:
        raise HTTPException(404, "No failed crawl job to retry")
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await crawl_jobs.insert_one({
        **{k: v for k, v in last.items() if k not in ("_id", "id", "queued_at", "started_at", "ended_at", "status", "error")},
        "id": job_id, "status": "queued", "queued_at": now,
        "pages_found": 0, "pages_crawled": 0, "pages_failed": 0, "pages_skipped": 0,
    })
    from services.web_crawler.pipeline import run_crawl_job
    background_tasks.add_task(run_crawl_job, job_id)
    return {"job_id": job_id, "status": "queued"}


@router.post("/{kb_id}/schedule")
async def upsert_schedule(kb_id: str, body: ScheduleCreate, user: dict = Depends(require_role(ROLE_EDITOR))):
    await _get_owned_kb(kb_id, user, require_owner=True)
    now = datetime.now(timezone.utc).isoformat()
    await sync_schedules.update_one(
        {"kb_id": kb_id},
        {"$set": {"kb_id": kb_id, "cron_expr": body.cron_expr, "enabled": body.enabled,
                  "crawl_config": body.crawl_config.model_dump(), "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return {"ok": True}


@router.delete("/{kb_id}/schedule")
async def delete_schedule(kb_id: str, user: dict = Depends(require_role(ROLE_EDITOR))):
    await _get_owned_kb(kb_id, user, require_owner=True)
    await sync_schedules.delete_one({"kb_id": kb_id})
    return {"ok": True}


@router.get("/{kb_id}/analytics")
async def kb_analytics(kb_id: str, user: dict = Depends(get_current_user)):
    kb = await _get_owned_kb(kb_id, user)
    job_count = await crawl_jobs.count_documents({"kb_id": kb_id})
    doc_count = await documents.count_documents({"kb_id": kb_id})
    page_count = await crawl_history.count_documents({"kb_id": kb_id})
    recent = await crawl_jobs.find({"kb_id": kb_id}, {"_id": 0, "queued_at": 1, "status": 1,
                                                        "pages_crawled": 1, "pages_skipped": 1,
                                                        "pages_failed": 1}).sort("queued_at", -1).limit(20).to_list(20)
    return {
        "kb_id": kb_id, "name": kb.get("name"),
        "job_count": job_count, "document_count": doc_count, "page_count": page_count,
        "chunk_count": kb.get("chunk_count", 0),
        "recent_jobs": recent,
    }


@router.post("/{kb_id}/search")
async def search_kb(kb_id: str, body: SearchQuery, user: dict = Depends(get_current_user)):
    kb = await _get_owned_kb(kb_id, user)
    strategy = get_strategy(body.mode or kb.get("search_mode", "hybrid"))
    config = {**kb, **({"similarity_threshold": body.similarity_threshold} if body.similarity_threshold is not None else {})}
    raw_hits = await strategy(
        body.query,
        kb["owner_id"],
        doc_ids=None,
        kb_ids=[kb_id],
        top_k=body.top_k or kb.get("top_k", 5),
        config=config,
    )
    # Enrich each hit with stable source attribution fields for the UI.
    kb_name = kb.get("name") or "unknown"
    enriched = []
    for h in raw_hits or []:
        enriched.append({
            **h,
            "filename": h.get("filename") or "unknown",
            "page": h.get("page") if h.get("page") is not None else "unknown",
            "chunk_index": h.get("chunk_index") if h.get("chunk_index") is not None else "unknown",
            "score": float(h.get("score") or 0.0),
            "kb_id": kb_id,
            "kb_name": kb_name,
        })
    return enriched
