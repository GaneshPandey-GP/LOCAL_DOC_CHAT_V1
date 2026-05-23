"""MCP tool registry — Mongo-backed lookup."""
from __future__ import annotations

from typing import Optional

from core.db import mcp_tools


async def get_tool(tool_id: str) -> Optional[dict]:
    return await mcp_tools.find_one({"id": tool_id}, {"_id": 0})


async def list_tools(owner_id: str, builtin_only: bool = False) -> list[dict]:
    if builtin_only:
        q = {"is_builtin": True}
    else:
        q = {"$or": [{"is_builtin": True}, {"owner_id": owner_id}]}
    cursor = mcp_tools.find(q, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(500)
