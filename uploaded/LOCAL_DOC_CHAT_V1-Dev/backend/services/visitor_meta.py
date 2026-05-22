"""Lightweight visitor metadata helpers for share-link sessions.

Captures IP, user-agent details, and a soft device fingerprint for
share-link guest sessions WITHOUT introducing new dependencies. Geo
lookup is best-effort (free public ipapi.co) and is fire-and-forget so
it never blocks the chat request.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Optional, Tuple

import httpx

from core.db import sessions as sessions_coll

logger = logging.getLogger("docchat")

# In-memory cache to avoid spamming the geo API for repeated IPs
_GEO_CACHE: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# IP helpers
# ---------------------------------------------------------------------------
def extract_client_ip(request) -> Optional[str]:
    """Best-effort client IP — honour X-Forwarded-For first hop."""
    if request is None:
        return None
    headers = getattr(request, "headers", {}) or {}
    xff = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For")
    if xff:
        # First entry in XFF chain is the real client
        ip = xff.split(",")[0].strip()
        if ip:
            return ip
    real_ip = headers.get("x-real-ip") or headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None) if client else None


def mask_ip(ip: Optional[str]) -> Optional[str]:
    """Mask the last octet/segment for safe display.
    203.0.113.42 -> 203.0.113.xxx
    2001:db8:abcd:0012:: -> 2001:db8:abcd:xxxx::
    """
    if not ip:
        return None
    if "." in ip and ":" not in ip:  # IPv4
        parts = ip.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3]) + ".xxx"
    if ":" in ip:  # IPv6 — mask the last visible segment
        parts = ip.split(":")
        if parts:
            # Find the index of the last non-empty segment
            for i in range(len(parts) - 1, -1, -1):
                if parts[i]:
                    parts[i] = "xxxx"
                    break
            return ":".join(parts)
    return ip


# ---------------------------------------------------------------------------
# User-Agent parser (regex-only, no external dep)
# ---------------------------------------------------------------------------
_BROWSER_RES = [
    ("Edge", re.compile(r"Edg(?:e|A|iOS)?/([\d.]+)")),
    ("Opera", re.compile(r"OPR/([\d.]+)|Opera/([\d.]+)")),
    ("Chrome", re.compile(r"Chrome/([\d.]+)")),
    ("Firefox", re.compile(r"Firefox/([\d.]+)")),
    ("Safari", re.compile(r"Version/([\d.]+).*Safari")),
    ("IE", re.compile(r"MSIE ([\d.]+)|Trident.*rv:([\d.]+)")),
]

_OS_RES = [
    ("iOS", re.compile(r"iP(?:hone|ad|od).*OS ([\d_]+)")),
    ("Android", re.compile(r"Android ([\d.]+)")),
    ("Windows", re.compile(r"Windows NT ([\d.]+)")),
    ("macOS", re.compile(r"Mac OS X ([\d_.]+)")),
    ("Linux", re.compile(r"Linux")),
    ("ChromeOS", re.compile(r"CrOS")),
]


def parse_user_agent(ua: Optional[str]) -> dict:
    """Return {browser, browser_version, os, os_version, device_type}."""
    out = {
        "browser": None,
        "browser_version": None,
        "os": None,
        "os_version": None,
        "device_type": "desktop",
    }
    if not ua:
        return out

    # Browser
    for name, regex in _BROWSER_RES:
        m = regex.search(ua)
        if m:
            out["browser"] = name
            ver = next((g for g in m.groups() if g), None)
            if ver:
                out["browser_version"] = ver.split(".")[0]
            break

    # OS
    for name, regex in _OS_RES:
        m = regex.search(ua)
        if m:
            out["os"] = name
            if m.groups():
                ver = next((g for g in m.groups() if g), None)
                if ver:
                    out["os_version"] = ver.replace("_", ".").split(".")[0]
            break

    # Device type
    ua_l = ua.lower()
    if "ipad" in ua_l or ("tablet" in ua_l and "android" in ua_l):
        out["device_type"] = "tablet"
    elif "mobile" in ua_l or "iphone" in ua_l or "android" in ua_l:
        out["device_type"] = "mobile"
    return out


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------
def device_fingerprint(ua: Optional[str], lang: Optional[str], enc: Optional[str]) -> str:
    """Stable short hash over UA + Accept-Language + Accept-Encoding."""
    blob = f"{ua or ''}|{lang or ''}|{enc or ''}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Combined extractor
# ---------------------------------------------------------------------------
def extract_visitor_meta(request) -> dict:
    """Extract everything we can derive synchronously from a request."""
    headers = getattr(request, "headers", {}) or {}
    ua = headers.get("user-agent") or headers.get("User-Agent")
    lang = headers.get("accept-language") or headers.get("Accept-Language")
    enc = headers.get("accept-encoding") or headers.get("Accept-Encoding")
    ip = extract_client_ip(request)
    parsed = parse_user_agent(ua)
    return {
        "ip": ip,
        "ip_masked": mask_ip(ip),
        "user_agent": ua,
        "accept_language": lang,
        "accept_encoding": enc,
        "fingerprint": device_fingerprint(ua, lang, enc),
        **parsed,
    }


# ---------------------------------------------------------------------------
# Geo enrichment (fire-and-forget; never blocks chat)
# ---------------------------------------------------------------------------
def _is_private_ip(ip: str) -> bool:
    """Skip RFC1918 / loopback to save API calls."""
    if not ip:
        return True
    if ip in ("127.0.0.1", "::1", "localhost"):
        return True
    if ip.startswith(("10.", "192.168.", "172.16.", "172.17.", "172.18.",
                     "172.19.", "172.20.", "172.21.", "172.22.", "172.23.",
                     "172.24.", "172.25.", "172.26.", "172.27.", "172.28.",
                     "172.29.", "172.30.", "172.31.", "169.254.", "fc00:", "fe80:")):
        return True
    return False


async def _fetch_geo(ip: str) -> Tuple[Optional[str], Optional[str]]:
    if ip in _GEO_CACHE:
        c = _GEO_CACHE[ip]
        return c.get("country"), c.get("city")
    if _is_private_ip(ip):
        _GEO_CACHE[ip] = {"country": None, "city": None}
        return None, None
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"https://ipapi.co/{ip}/json/")
            if r.status_code == 200:
                data = r.json()
                country = data.get("country_name")
                city = data.get("city")
                _GEO_CACHE[ip] = {"country": country, "city": city}
                return country, city
    except Exception as exc:
        logger.debug("Geo lookup failed for %s: %s", ip, exc)
    _GEO_CACHE[ip] = {"country": None, "city": None}
    return None, None


def enrich_session_geo(session_id: str, ip: Optional[str]) -> None:
    """Schedule a fire-and-forget geo lookup that updates the session row.
    Safe to call from any async context; never raises and never blocks.
    """
    if not ip or _is_private_ip(ip):
        return

    async def _run():
        country, city = await _fetch_geo(ip)
        if country or city:
            try:
                await sessions_coll.update_one(
                    {"id": session_id},
                    {"$set": {"geo_country": country, "geo_city": city}},
                )
            except Exception:
                pass

    try:
        asyncio.create_task(_run())
    except RuntimeError:
        # No running loop — skip silently
        pass
