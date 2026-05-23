"""JS-rendered Playwright crawler (off by default).

Mirrors `WebCrawler` interface so the pipeline can swap implementations based
on the `use_playwright` config flag. Falls back to `WebCrawler` if Playwright
is unavailable in the runtime image.
"""
from __future__ import annotations

import logging
from typing import Optional

from .crawler import CrawledPage, WebCrawler

logger = logging.getLogger("docchat.web_crawler.playwright")

try:
    from playwright.async_api import async_playwright  # type: ignore
    _PLAYWRIGHT_AVAILABLE = True
except Exception:
    _PLAYWRIGHT_AVAILABLE = False


class PlaywrightCrawler:
    def __init__(self, user_agent: str = "DocChat-Crawler/1.0"):
        self.user_agent = user_agent
        if not _PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright unavailable — PlaywrightCrawler will delegate to httpx WebCrawler.")
        self._fallback = WebCrawler(user_agent=user_agent)

    async def crawl_url(
        self,
        root_url: str,
        max_depth: int = 3,
        max_pages: int = 200,
        selector: Optional[str] = None,
        exclude_selectors: Optional[list[str]] = None,
        respect_robots: bool = True,
        rate_limit_rps: float = 2.0,
    ) -> list[CrawledPage]:
        if not _PLAYWRIGHT_AVAILABLE:
            return await self._fallback.crawl_url(
                root_url, max_depth, max_pages, selector, exclude_selectors, respect_robots, rate_limit_rps
            )
        # Minimal Playwright variant: single-page render → reuses BS+markdownify
        from .crawler import _clean_markdown, _hash, _have_lxml
        from bs4 import BeautifulSoup
        from datetime import datetime, timezone
        out: list[CrawledPage] = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=self.user_agent)
            try:
                await page.goto(root_url, wait_until="networkidle", timeout=30_000)
                html = await page.content()
                text = _clean_markdown(html, selector, exclude_selectors or [])
                if text:
                    soup = BeautifulSoup(html, "lxml") if _have_lxml() else BeautifulSoup(html, "html.parser")
                    title = soup.title.string.strip() if soup.title and soup.title.string else root_url
                    out.append(CrawledPage(
                        url=root_url, title=title, content=text, content_hash=_hash(text),
                        status_code=200, depth=0, parent_url=None,
                        crawled_at=datetime.now(timezone.utc).isoformat(),
                    ))
            finally:
                await browser.close()
        return out

    async def fetch_sitemap_urls(self, sitemap_url: str) -> list[str]:
        return await self._fallback.fetch_sitemap_urls(sitemap_url)

    async def fetch_single(self, url: str, selector: Optional[str] = None, exclude_selectors: Optional[list[str]] = None):
        return await self._fallback.fetch_single(url, selector, exclude_selectors)
