"""DB Agent orchestrator (Stream 6).

Pipeline:
   user_query  →  query_guard  →  schema_introspect  →  sql_generator
              →  sql_validator →  RBAC (in router)  →  sql_executor
              →  audit_service →  (optional) excel_exporter
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from services import config_service

from . import audit_service, query_guard, schema_service, sql_executor, sql_generator, sql_validator

logger = logging.getLogger("docchat.db_agent.orchestrator")


async def run_query(
    *,
    user_id: str,
    user_role: str,
    natural_query: str,
    execute: bool = True,
    ip: Optional[str] = None,
) -> dict:
    """Run the full pipeline. Returns a dict with sql / explanation / rows / etc.

    If `execute=False`, only generates + validates SQL and returns the EXPLAIN plan.
    """
    # 1) Input guard
    verdict = query_guard.check_user_input(natural_query)
    if not verdict.allowed:
        await audit_service.record(
            user_id=user_id, user_role=user_role,
            natural_query=natural_query, sql=None,
            outcome="blocked", risk_score=verdict.risk,
            reason="; ".join(verdict.reasons), ip=ip,
        )
        return {
            "blocked": True,
            "reasons": verdict.reasons,
            "risk_score": verdict.risk,
        }

    # 2) Generate SQL
    row_cap = int(await config_service.get_setting("db_agent_row_cap", 5000))
    try:
        gen = await sql_generator.generate_sql(natural_query, row_cap=row_cap)
    except Exception as e:
        await audit_service.record(
            user_id=user_id, user_role=user_role,
            natural_query=natural_query, sql=None,
            outcome="error", reason=f"sql_generation_failed: {e}", ip=ip,
        )
        return {"error": "Failed to generate SQL", "detail": str(e)}

    sql = gen["sql"]
    explanation = gen.get("explanation", "")

    # 3) Validate AST
    schema = await schema_service.introspect()
    allowlist = schema_service.column_allowlist(schema)
    validation = sql_validator.validate(sql, column_allowlist=allowlist)
    if not validation.ok:
        await audit_service.record(
            user_id=user_id, user_role=user_role,
            natural_query=natural_query, sql=sql,
            outcome="blocked", risk_score=80,
            reason="; ".join(validation.reasons),
            tables=validation.tables_referenced,
            columns=validation.columns_referenced,
            ip=ip,
        )
        return {
            "blocked": True,
            "sql": sql,
            "explanation": explanation,
            "reasons": validation.reasons,
        }

    # 4) Cost estimation (cheap heuristic) — record but don't block
    cost = query_guard.estimate_query_cost(sql)

    # 5) Execute or explain only
    if not execute:
        try:
            plan = await sql_executor.explain(sql)
        except Exception as e:
            await audit_service.record(
                user_id=user_id, user_role=user_role,
                natural_query=natural_query, sql=sql,
                outcome="error", reason=f"explain_failed: {e}", ip=ip,
            )
            return {"error": "Explain failed", "detail": str(e), "sql": sql}
        return {
            "sql": sql,
            "explanation": explanation,
            "plan": plan["plan"],
            "estimated_cost": cost,
        }

    try:
        result = await sql_executor.execute(sql)
    except Exception as e:
        outcome = "timeout" if "timeout" in str(e).lower() else "error"
        await audit_service.record(
            user_id=user_id, user_role=user_role,
            natural_query=natural_query, sql=sql,
            outcome=outcome, reason=str(e), ip=ip,
        )
        return {"error": "Execution failed", "detail": str(e), "sql": sql}

    await audit_service.record(
        user_id=user_id, user_role=user_role,
        natural_query=natural_query, sql=sql,
        outcome="success",
        tables=validation.tables_referenced,
        columns=validation.columns_referenced,
        elapsed_ms=result.get("elapsed_ms", 0),
        row_count=result.get("row_count", 0),
        ip=ip,
    )
    return {
        "sql": sql,
        "explanation": explanation,
        "result": result,
        "estimated_cost": cost,
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
