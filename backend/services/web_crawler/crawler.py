"""Async web crawler.

Uses httpx + BeautifulSoup + markdownify. BFS across one domain, respects
robots.txt by default, supports CSS selector targeting and an exclude list,
returns a list of `CrawledPage` records with stable SHA-256 content hashes.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

logger = logging.getLogger("docchat.web_crawler.crawler")

try:
    from bs4 import BeautifulSoup  # type: ignore
    from markdownify import markdownify as md  # type: ignore
    _AVAILABLE = True
except Exception:
    _AVAILABLE = False


@dataclass
class CrawledPage:
    url: str
    title: str
    content: str
    content_hash: str
    status_code: int
    depth: int
    parent_url: Optional[str]
    crawled_at: str


def _strip_noise(soup) -> None:
    for tag in soup(["script", "style", "nav", "footer", "aside", "noscript"]):
        tag.decompose()


def _clean_markdown(html: str, selector: Optional[str], exclude_selectors: list[str]) -> str:
    soup = BeautifulSoup(html, "lxml") if _have_lxml() else BeautifulSoup(html, "html.parser")
    _strip_noise(soup)
    for sel in exclude_selectors or []:
        for el in soup.select(sel):
            el.decompose()
    root = soup.select_one(selector) if selector else (soup.body or soup)
    if root is None:
        return ""
    text = md(str(root), heading_style="ATX")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _have_lxml() -> bool:
    try:
        import lxml  # noqa: F401
        return True
    except Exception:
        return False


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_html(resp: httpx.Response) -> bool:
    return "html" in (resp.headers.get("content-type") or "").lower()


def _same_origin(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return pa.netloc == pb.netloc and pa.scheme in ("http", "https")


class WebCrawler:
    def __init__(self, user_agent: str = "DocChat-Crawler/1.0"):
        if not _AVAILABLE:
            raise RuntimeError("beautifulsoup4 + markdownify must be installed for the web crawler")
        self.user_agent = user_agent

    async def _fetch(self, client: httpx.AsyncClient, url: str, selector: Optional[str], exclude_selectors: list[str]) -> Optional[tuple[str, str, int]]:
        try:
            resp = await client.get(url, timeout=20.0, follow_redirects=True)
        except Exception as e:
            logger.debug("fetch fail %s: %s", url, e)
            return None
        if resp.status_code != 200 or not _is_html(resp):
            return None
        text = _clean_markdown(resp.text, selector, exclude_selectors)
        if len(text) < 50:
            return None
        soup = BeautifulSoup(resp.text, "lxml") if _have_lxml() else BeautifulSoup(resp.text, "html.parser")
        title = (soup.title.string.strip() if soup.title and soup.title.string else url)
        return text, title, resp.status_code

    def _robots_ok(self, robots: Optional[urllib.robotparser.RobotFileParser], url: str) -> bool:
        if robots is None:
            return True
        try:
            return robots.can_fetch(self.user_agent, url)
        except Exception:
            return True

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
        exclude_selectors = exclude_selectors or []
        seen: set[str] = set()
        out: list[CrawledPage] = []
        queue: list[tuple[str, int, Optional[str]]] = [(root_url, 0, None)]

        # Robots
        robots = None
        if respect_robots:
            try:
                p = urlparse(root_url)
                robots = urllib.robotparser.RobotFileParser()
                robots.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
                robots.read()
            except Exception:
                robots = None

        delay = 1.0 / max(0.1, rate_limit_rps)
        async with httpx.AsyncClient(headers={"User-Agent": self.user_agent}) as client:
            while queue and len(out) < max_pages:
                url, depth, parent = queue.pop(0)
                url, _ = urldefrag(url)
                if url in seen:
                    continue
                seen.add(url)
                if not _same_origin(root_url, url):
                    continue
                if not self._robots_ok(robots, url):
                    continue

                t0 = time.monotonic()
                result = await self._fetch(client, url, selector, exclude_selectors)
                if result is None:
                    continue
                text, title, status = result
                out.append(CrawledPage(
                    url=url, title=title, content=text, content_hash=_hash(text),
                    status_code=status, depth=depth, parent_url=parent,
                    crawled_at=datetime.now(timezone.utc).isoformat(),
                ))

                # Discover links if we still have depth budget
                if depth < max_depth:
                    try:
                        resp = await client.get(url, timeout=20.0)
                        soup = BeautifulSoup(resp.text, "lxml") if _have_lxml() else BeautifulSoup(resp.text, "html.parser")
                        for a in soup.find_all("a", href=True):
                            href = urljoin(url, a["href"])
                            href, _ = urldefrag(href)
                            if href not in seen and _same_origin(root_url, href):
                                queue.append((href, depth + 1, url))
                    except Exception:
                        pass

                # Rate limit
                elapsed = time.monotonic() - t0
                if elapsed < delay:
                    await asyncio.sleep(delay - elapsed)
        return out

    async def fetch_sitemap_urls(self, sitemap_url: str) -> list[str]:
        urls: list[str] = []
        try:
            async with httpx.AsyncClient(headers={"User-Agent": self.user_agent}) as c:
                resp = await c.get(sitemap_url, timeout=20.0)
            if resp.status_code != 200:
                return urls
            soup = BeautifulSoup(resp.text, "xml")
            for loc in soup.find_all("loc"):
                url = (loc.text or "").strip()
                if url.endswith(".xml"):
                    urls.extend(await self.fetch_sitemap_urls(url))
                else:
                    urls.append(url)
        except Exception as e:
            logger.warning("sitemap fetch failed for %s: %s", sitemap_url, e)
        return urls

    async def fetch_single(self, url: str, selector: Optional[str] = None, exclude_selectors: Optional[list[str]] = None) -> Optional[CrawledPage]:
        async with httpx.AsyncClient(headers={"User-Agent": self.user_agent}) as client:
            res = await self._fetch(client, url, selector, exclude_selectors or [])
        if res is None:
            return None
        text, title, status = res
        return CrawledPage(
            url=url, title=title, content=text, content_hash=_hash(text),
            status_code=status, depth=0, parent_url=None,
            crawled_at=datetime.now(timezone.utc).isoformat(),
        )
