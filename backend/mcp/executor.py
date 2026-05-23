"""MCP tool executor — dispatches builtin or HTTP tools and audits each call."""
from __future__ import annotations

import importlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from core.db import tool_executions

from .registry import get_tool

logger = logging.getLogger("docchat.mcp.executor")


_BUILTIN_MAP = {
    "builtin-web-search": "mcp.tools.web_search",
    "builtin-github": "mcp.tools.github",
    "builtin-sql-query": "mcp.tools.sql_query",
    "builtin-http-request": "mcp.tools.http_request",
    "builtin-webhook": "mcp.tools.webhook",
}


async def execute_mcp_tool(
    tool_id: str,
    tool_input: dict,
    context: Optional[dict] = None,
    run_id: Optional[str] = None,
    node_id: Optional[str] = None,
) -> Any:
    tool = await get_tool(tool_id)
    if not tool:
        raise ValueError(f"Tool not found: {tool_id}")
    if tool.get("enabled") is False:
        raise ValueError(f"Tool disabled: {tool_id}")

    started = time.perf_counter()
    status = "success"
    err: Optional[str] = None
    result: Any = None
    try:
        if tool.get("endpoint_type") == "builtin":
            module_name = _BUILTIN_MAP.get(tool_id)
            if not module_name:
                # convention: id "builtin-foo-bar" -> mcp.tools.foo_bar
                if tool_id.startswith("builtin-"):
                    module_name = "mcp.tools." + tool_id.replace("builtin-", "").replace("-", "_")
            if not module_name:
                raise ValueError(f"No builtin handler for {tool_id}")
            mod = importlib.import_module(module_name)
            run = getattr(mod, "run")
            result = await run(tool_input) if _is_async(run) else run(tool_input)
        elif tool.get("endpoint_type") == "http":
            endpoint = tool.get("endpoint_url")
            if not endpoint:
                raise ValueError("HTTP tool missing endpoint_url")
            timeout = float(tool.get("timeout_ms", 30000)) / 1000.0
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(endpoint, json={"input": tool_input, "context": context or {}})
                if resp.status_code >= 400:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                try:
                    result = resp.json()
                except Exception:
                    result = {"raw": resp.text[:4000]}
        else:
            raise ValueError(f"Unsupported endpoint_type: {tool.get('endpoint_type')}")
    except Exception as e:
        status = "error"
        err = str(e)[:500]
        logger.warning("MCP tool %s failed: %s", tool_id, e)
        raise
    finally:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        try:
            await tool_executions.insert_one({
                "id": str(uuid.uuid4()),
                "tool_id": tool_id,
                "run_id": run_id,
                "node_id": node_id,
                "input": tool_input,
                "status": status,
                "error": err,
                "elapsed_ms": elapsed_ms,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass

    return result


def _is_async(fn) -> bool:
    import inspect
    return inspect.iscoroutinefunction(fn)
