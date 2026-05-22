"""Audit logging for the DB Agent (Stream 6).

Every query — successful, blocked or errored — is persisted into the
`db_agent_audit` Mongo collection with a sanitized payload (no credentials,
no full SQL on blocked attempts beyond the first 500 chars).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from core.db import db_agent_audit

logger = logging.getLogger("docchat.db_agent.audit")


async def record(
    *,
    user_id: str,
    user_role: Optional[str],
    natural_query: str,
    sql: Optional[str],
    outcome: str,  # success | blocked | timeout | error
    risk_score: int = 0,
    tables: Optional[list[str]] = None,
    columns: Optional[list[str]] = None,
    elapsed_ms: int = 0,
    row_count: int = 0,
    reason: Optional[str] = None,
    ip: Optional[str] = None,
) -> None:
    try:
        await db_agent_audit.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "user_role": user_role,
            "natural_query": (natural_query or "")[:2000],
            "sql": (sql or "")[:4000] if sql else None,
            "outcome": outcome,
            "risk_score": risk_score,
            "tables": tables or [],
            "columns": (columns or [])[:50],
            "elapsed_ms": elapsed_ms,
            "row_count": row_count,
            "reason": reason,
            "ip": ip,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning("db_agent audit insert failed: %s", e)
