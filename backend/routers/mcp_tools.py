"""MCP tools router (Module 6)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.audit import log_event
from core.db import mcp_tools, tool_executions
from core.deps import ROLE_ADMIN, ROLE_EDITOR, get_current_user, require_role

from mcp.executor import execute_mcp_tool
from mcp.registry import get_tool, list_tools

router = APIRouter(prefix="/v2/mcp", tags=["mcp"])


class ToolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=512)
    endpoint_type: str = Field(default="http")   # http | builtin
    endpoint_url: Optional[str] = None
    timeout_ms: int = 30000
    input_schema: dict = Field(default_factory=dict)
    enabled: bool = True


class ToolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint_url: Optional[str] = None
    timeout_ms: Optional[int] = None
    input_schema: Optional[dict] = None
    enabled: Optional[bool] = None


def _is_admin(user: dict) -> bool:
    return user.get("role") in (ROLE_ADMIN, "owner")


def _ensure_owner(tool: dict, user: dict) -> None:
    if tool.get("is_builtin"):
        if not _is_admin(user):
            raise HTTPException(403, "Built-in tools can only be modified by admins")
        return
    if not _is_admin(user) and tool.get("owner_id") != user["id"]:
        raise HTTPException(403, "Forbidden")


@router.post("/tools", status_code=201)
async def create_tool(body: ToolCreate, user: dict = Depends(require_role(ROLE_EDITOR))):
    tool_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": tool_id, "owner_id": user["id"], "created_at": now,
        "is_builtin": False, "call_count": 0,
        **body.model_dump(),
    }
    await mcp_tools.insert_one(doc)
    await log_event("mcp.tool.created", actor_id=user["id"], actor_role=user["role"],
                    resource_type="mcp_tool", resource_id=tool_id, metadata={"name": body.name})
    doc.pop("_id", None)
    return doc


@router.get("/tools")
async def list_user_tools(user: dict = Depends(get_current_user), builtin_only: bool = False):
    return await list_tools(user["id"], builtin_only=builtin_only)


@router.get("/tools/{tool_id}")
async def get_one(tool_id: str, user: dict = Depends(get_current_user)):
    tool = await get_tool(tool_id)
    if not tool:
        raise HTTPException(404, "Tool not found")
    if not tool.get("is_builtin") and not _is_admin(user) and tool["owner_id"] != user["id"]:
        raise HTTPException(403, "Forbidden")
    return tool


@router.patch("/tools/{tool_id}")
async def update_tool(tool_id: str, body: ToolUpdate, user: dict = Depends(require_role(ROLE_EDITOR))):
    tool = await get_tool(tool_id)
    if not tool:
        raise HTTPException(404, "Tool not found")
    _ensure_owner(tool, user)
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if not upd:
        return tool
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    await mcp_tools.update_one({"id": tool_id}, {"$set": upd})
    return await get_tool(tool_id)


@router.delete("/tools/{tool_id}")
async def delete_tool(tool_id: str, user: dict = Depends(require_role(ROLE_EDITOR))):
    tool = await get_tool(tool_id)
    if not tool:
        raise HTTPException(404, "Tool not found")
    if tool.get("is_builtin"):
        raise HTTPException(400, "Built-in tools cannot be deleted")
    _ensure_owner(tool, user)
    await mcp_tools.delete_one({"id": tool_id})
    return {"ok": True}


@router.post("/tools/{tool_id}/test")
async def test_tool(tool_id: str, body: dict, user: dict = Depends(require_role(ROLE_EDITOR))):
    tool = await get_tool(tool_id)
    if not tool:
        raise HTTPException(404, "Tool not found")
    if not tool.get("is_builtin"):
        _ensure_owner(tool, user)
    try:
        result = await execute_mcp_tool(tool_id, body or {}, run_id="test", node_id="test")
        await mcp_tools.update_one({"id": tool_id}, {"$inc": {"call_count": 1}})
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:500]}


@router.get("/tools/{tool_id}/executions")
async def tool_executions_history(
    tool_id: str,
    limit: int = Query(50, le=200),
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    cursor = tool_executions.find({"tool_id": tool_id}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(limit)
