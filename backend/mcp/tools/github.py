"""Built-in GitHub tool — wraps a small surface of the public REST API.

Input shapes:
   {"op": "search_repos", "query": "..."}
   {"op": "get_file", "owner": "...", "repo": "...", "path": "..."}
   {"op": "list_issues", "owner": "...", "repo": "...", "state": "open"}
"""
from __future__ import annotations

import base64
import os
import httpx

GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "DocChat-MCP/1.0"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


async def run(tool_input: dict) -> dict:
    op = (tool_input or {}).get("op", "")
    async with httpx.AsyncClient(timeout=15.0, headers=_headers()) as client:
        if op == "search_repos":
            r = await client.get(f"{GITHUB_API}/search/repositories", params={"q": tool_input.get("query", "")})
            data = r.json()
            return {"items": [{"full_name": it["full_name"], "stars": it["stargazers_count"], "url": it["html_url"]} for it in data.get("items", [])[:10]]}
        if op == "get_file":
            owner, repo, path = tool_input.get("owner"), tool_input.get("repo"), tool_input.get("path")
            r = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}")
            data = r.json()
            if "content" in data:
                try:
                    return {"content": base64.b64decode(data["content"]).decode("utf-8", errors="replace")}
                except Exception:
                    return {"content": data["content"]}
            return data
        if op == "list_issues":
            owner, repo = tool_input.get("owner"), tool_input.get("repo")
            r = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}/issues", params={"state": tool_input.get("state", "open")})
            return {"items": [{"number": it["number"], "title": it["title"], "url": it["html_url"], "state": it["state"]} for it in r.json()[:25]]}
    return {"error": f"unknown op {op!r}"}
