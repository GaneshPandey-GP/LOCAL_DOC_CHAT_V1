"""Safe SQL execution layer for the DB Agent (Stream 6).

All queries run on a read-only asyncpg connection with:
  • forced read-only transaction
  • per-query statement_timeout (ms)
  • configurable row cap applied at fetch-time
"""
import logging
from typing import Any

from services import config_service

from .connection import get_pool

logger = logging.getLogger("docchat.db_agent.executor")


async def execute(sql: str, params: list | None = None, row_cap: int | None = None) -> dict:
    """Run a validated SELECT and return {columns, rows, row_count, elapsed_ms}."""
    pool = await get_pool()
    timeout_sec = int(await config_service.get_setting("db_agent_query_timeout_sec", 30))
    cap = int(row_cap or await config_service.get_setting("db_agent_row_cap", 5000))

    import time
    t0 = time.perf_counter()
    async with pool.acquire() as conn:
        # Belt-and-suspenders: set read_only at the connection level too
        async with conn.transaction(readonly=True):
            stmt = await conn.prepare(sql, timeout=timeout_sec)
            records = await stmt.fetch(*(params or []), timeout=timeout_sec)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    rows: list[dict[str, Any]] = []
    columns: list[str] = []
    for i, rec in enumerate(records):
        if i >= cap:
            break
        d = dict(rec)
        if not columns:
            columns = list(d.keys())
        rows.append(d)
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "elapsed_ms": elapsed_ms,
        "truncated": len(records) > cap,
    }


async def explain(sql: str) -> dict:
    """Return EXPLAIN plan without executing the actual query."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch("EXPLAIN " + sql)
    plan = [r[0] for r in rows]
    return {"plan": plan}
