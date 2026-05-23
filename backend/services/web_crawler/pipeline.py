"""Background-task pipeline that drives a single crawl job through to Qdrant.

Phases:
  1. mark job running
  2. choose crawler (Playwright if enabled & requested, else httpx)
  3. enumerate URLs (recursive | sitemap | single)
  4. for each page:
       • if content_hash unchanged in crawl_history → skip
       • else chunk → embed → upsert via services.qdrant.ingestion.add_chunks
       • upsert a `documents` row with category=Web, tags=[web-crawl]
       • record content_hash in crawl_history
  5. on success: mark job completed, bump KB last_crawled_at + chunk_count
  6. on failure: mark job failed with stringified exception
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from core.config import is_enabled
from core.db import crawl_history, crawl_jobs, documents, knowledge_bases
from services import config_service
from services.qdrant.ingestion import add_chunks
from services.chunking import chunk_text  # reuse existing chunker

from .crawler import WebCrawler, CrawledPage

logger = logging.getLogger("docchat.web_crawler.pipeline")


def _doc_id_for(kb_id: str, url: str) -> str:
    return f"web:{kb_id}:{uuid.uuid5(uuid.NAMESPACE_URL, url)}"


async def _pick_crawler(use_playwright: bool):
    if use_playwright and is_enabled("ENABLE_PLAYWRIGHT_CRAWLER"):
        try:
            from .playwright_crawler import PlaywrightCrawler
            return PlaywrightCrawler(user_agent=str(await config_service.get_setting("crawl_user_agent", "DocChat-Crawler/1.0")))
        except Exception as e:
            logger.warning("Playwright unavailable, falling back to httpx: %s", e)
    return WebCrawler(user_agent=str(await config_service.get_setting("crawl_user_agent", "DocChat-Crawler/1.0")))


async def _ingest_page(kb: dict, page: CrawledPage) -> tuple[int, bool]:
    """Returns (chunks_added, skipped_unchanged)."""
    prev = await crawl_history.find_one(
        {"kb_id": kb["id"], "url": page.url}, {"_id": 0, "content_hash": 1}
    )
    if prev and prev.get("content_hash") == page.content_hash:
        return 0, True

    chunk_size = int(await config_service.get_setting("chunk_size", 1000))
    overlap = int(await config_service.get_setting("chunk_overlap", 200))
    chunks_raw = chunk_text(page.content, chunk_tokens=chunk_size, overlap=overlap)
    chunks = [{"text": t, "chunk_index": i, "file_type": "web"} for i, t in enumerate(chunks_raw)]

    doc_id = _doc_id_for(kb["id"], page.url)
    written = await add_chunks(
        doc_id=doc_id,
        owner_id=kb["owner_id"],
        filename=page.title or page.url,
        chunks=chunks,
        kb_id=kb["id"],
    )

    now = datetime.now(timezone.utc).isoformat()
    await documents.update_one(
        {"id": doc_id},
        {"$set": {
            "id": doc_id, "owner_id": kb["owner_id"], "kb_id": kb["id"],
            "filename": page.title or page.url, "size": len(page.content),
            "mime_type": "text/markdown", "file_type": "web",
            "category": "Web", "tags": ["web-crawl"],
            "status": "ready", "progress": 100,
            "chunk_count": written, "page_count": 1,
            "source_url": page.url,
            "indexed_at": now,
        }, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    await crawl_history.update_one(
        {"kb_id": kb["id"], "url": page.url},
        {"$set": {"kb_id": kb["id"], "url": page.url, "content_hash": page.content_hash, "last_crawled_at": now}},
        upsert=True,
    )
    return written, False


async def run_crawl_job(job_id: str) -> None:
    job = await crawl_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        logger.warning("Crawl job %s not found", job_id)
        return
    kb = await knowledge_bases.find_one({"id": job["kb_id"]}, {"_id": 0})
    if not kb:
        await crawl_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "failed", "error": "KB not found", "ended_at": datetime.now(timezone.utc).isoformat()}},
        )
        return

    started = datetime.now(timezone.utc).isoformat()
    await crawl_jobs.update_one(
        {"id": job_id},
        {"$set": {"status": "running", "started_at": started, "pages_found": 0, "pages_crawled": 0, "pages_failed": 0, "pages_skipped": 0}},
    )

    cfg = job.get("config", {})
    try:
        crawler = await _pick_crawler(bool(cfg.get("use_playwright")))
        ctype = cfg.get("type", "recursive")
        url = cfg.get("url") or kb.get("web_root_url") or ""
        pages: list[CrawledPage] = []
        if ctype == "single":
            p = await crawler.fetch_single(url, kb.get("selector"), kb.get("exclude_selectors") or [])
            pages = [p] if p else []
        elif ctype == "sitemap":
            urls = await crawler.fetch_sitemap_urls(kb.get("sitemap_url") or url)
            max_pages = int(cfg.get("max_pages", 200))
            for u in urls[:max_pages]:
                p = await crawler.fetch_single(u, kb.get("selector"), kb.get("exclude_selectors") or [])
                if p:
                    pages.append(p)
        else:
            pages = await crawler.crawl_url(
                root_url=url,
                max_depth=int(cfg.get("depth", 3)),
                max_pages=int(cfg.get("max_pages", 200)),
                selector=cfg.get("selector") or kb.get("selector"),
                exclude_selectors=kb.get("exclude_selectors") or [],
                respect_robots=bool(cfg.get("respect_robots", True)),
                rate_limit_rps=float(cfg.get("rate_limit_rps", 2.0)),
            )

        await crawl_jobs.update_one({"id": job_id}, {"$set": {"pages_found": len(pages)}})

        total_chunks = 0
        crawled = 0
        skipped = 0
        failed = 0
        for p in pages:
            try:
                added, was_skipped = await _ingest_page(kb, p)
                if was_skipped:
                    skipped += 1
                else:
                    crawled += 1
                    total_chunks += added
            except Exception as e:
                logger.warning("ingest fail for %s: %s", p.url, e)
                failed += 1
            await crawl_jobs.update_one(
                {"id": job_id},
                {"$set": {"pages_crawled": crawled, "pages_skipped": skipped, "pages_failed": failed}},
            )

        ended = datetime.now(timezone.utc).isoformat()
        await crawl_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "completed", "ended_at": ended, "chunks_added": total_chunks}},
        )
        await knowledge_bases.update_one(
            {"id": kb["id"]},
            {"$set": {"last_crawled_at": ended}, "$inc": {"chunk_count": total_chunks}},
        )
    except Exception as e:
        logger.exception("crawl job failed: %s", e)
        await crawl_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "failed", "error": str(e)[:500], "ended_at": datetime.now(timezone.utc).isoformat()}},
        )
