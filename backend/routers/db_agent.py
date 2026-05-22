"""DB Agent router (Stream 6).

Mounted at /api/v2/db-agent and /api/v2/reports.
All endpoints are RBAC-protected (editor or owner). Reports are scoped per user.
"""
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.audit import log_event
from core.db import db_agent_audit, db_agent_reports
from core.deps import ROLE_EDITOR, ROLE_OWNER, get_current_user, require_role
from services import config_service
from services.db_agent import excel_exporter, orchestrator, schema_service
from services.db_agent.audit_service import record as audit_record

logger = logging.getLogger("docchat.routers.db_agent")

router = APIRouter(prefix="/v2/db-agent", tags=["db-agent"])
reports_router = APIRouter(prefix="/v2/reports", tags=["db-agent-reports"])


class QueryBody(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    execute: bool = True


class ReportBody(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


async def _ensure_enabled():
    """Allow the DB Agent to run when Postgres is enabled OR Test Mode is active."""
    from services.db_agent.connection import is_test_mode_active
    if await is_test_mode_active():
        return
    enabled = await config_service.get_setting("db_agent_enabled", False)
    if not enabled:
        raise HTTPException(
            status_code=400,
            detail="DB Agent is disabled. Enable it via Settings → DB Agent, or upload a Test Database.",
        )


@router.get("/status")
async def db_agent_status(user: dict = Depends(get_current_user)):
    """Lightweight status: whether the agent is enabled + reachable + current mode."""
    from services.db_agent.connection import is_test_mode_active
    enabled = await config_service.get_setting("db_agent_enabled", False)
    test_mode = await is_test_mode_active()
    return {
        "enabled": bool(enabled) or test_mode,
        "configured": bool(await config_service.get_setting("db_agent_postgres_host", "")),
        "mode": "test" if test_mode else "live",
        "test_mode": test_mode,
    }


@router.get("/schema")
async def db_agent_schema(_: dict = Depends(require_role(ROLE_EDITOR))):
    """Return the introspected schema (limited to the allowlisted schemas)."""
    await _ensure_enabled()
    try:
        schema = await schema_service.introspect()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return schema


@router.post("/query")
async def db_agent_query(
    body: QueryBody,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    """Run a natural-language analytics query end-to-end."""
    await _ensure_enabled()
    ip = request.client.host if request.client else None
    out = await orchestrator.run_query(
        user_id=user["id"],
        user_role=user["role"],
        natural_query=body.query,
        execute=body.execute,
        ip=ip,
    )
    return out


@router.post("/explain")
async def db_agent_explain(
    body: QueryBody,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    """Generate SQL + EXPLAIN plan without executing."""
    await _ensure_enabled()
    ip = request.client.host if request.client else None
    body.execute = False
    return await orchestrator.run_query(
        user_id=user["id"],
        user_role=user["role"],
        natural_query=body.query,
        execute=False,
        ip=ip,
    )


@router.post("/report")
async def db_agent_report(
    body: ReportBody,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    """Run a query and persist a downloadable Excel report."""
    await _ensure_enabled()
    ip = request.client.host if request.client else None
    out = await orchestrator.run_query(
        user_id=user["id"],
        user_role=user["role"],
        natural_query=body.query,
        execute=True,
        ip=ip,
    )
    if out.get("blocked") or out.get("error"):
        return out

    report_id = str(uuid.uuid4())
    path = excel_exporter.build_xlsx(
        report_id=report_id,
        natural_query=body.query,
        sql=out.get("sql", ""),
        explanation=out.get("explanation", ""),
        result=out.get("result", {}),
        user_email=user.get("email"),
    )
    doc = {
        "id": report_id,
        "user_id": user["id"],
        "user_email": user.get("email"),
        "query": body.query,
        "sql": out.get("sql", ""),
        "explanation": out.get("explanation", ""),
        "row_count": out.get("result", {}).get("row_count", 0),
        "elapsed_ms": out.get("result", {}).get("elapsed_ms", 0),
        "file_path": path,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db_agent_reports.insert_one(doc)
    await log_event(
        "db_agent.report_generated",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="db_agent_report",
        resource_id=report_id,
        ip=ip,
        metadata={"row_count": doc["row_count"], "elapsed_ms": doc["elapsed_ms"]},
    )
    safe = {k: v for k, v in doc.items() if k not in ("file_path",)}
    return {"report": safe, "sql": doc["sql"], "result": out.get("result")}


@reports_router.get("/history")
async def report_history(
    limit: int = Query(50, le=200),
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    """List reports for the current user (admin sees all)."""
    q: dict = {} if user["role"] in (ROLE_OWNER, "owner") else {"user_id": user["id"]}
    cursor = db_agent_reports.find(q, {"_id": 0, "file_path": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(limit)


@reports_router.get("/{report_id}")
async def report_detail(
    report_id: str,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    doc = await db_agent_reports.find_one({"id": report_id}, {"_id": 0, "file_path": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    if user["role"] not in (ROLE_OWNER, "owner") and doc["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    return doc


@reports_router.get("/{report_id}/download")
async def report_download(
    report_id: str,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    doc = await db_agent_reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    if user["role"] not in (ROLE_OWNER, "owner") and doc["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    path = Path(doc["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report file no longer exists")
    return FileResponse(
        path=path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"docchat-report-{report_id}.xlsx",
    )


@router.get("/audit")
async def db_agent_audit_log(
    limit: int = Query(100, le=500),
    outcome: Optional[str] = None,
    _: dict = Depends(require_role(ROLE_OWNER)),
):
    """Owner-only — aggregate audit trail of every DB Agent invocation."""
    q: dict = {}
    if outcome:
        q["outcome"] = outcome
    cursor = db_agent_audit.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(limit)
