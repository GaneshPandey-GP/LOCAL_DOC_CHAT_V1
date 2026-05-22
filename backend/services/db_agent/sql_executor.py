"""Safe SQL execution layer for the DB Agent (Stream 6).

All queries run on a read-only asyncpg connection with:
  • forced read-only transaction
  • per-query statement_timeout (ms)
  • configurable row cap applied at fetch-time

When Settings → Test Database has an active `.db` upload, queries route to
that SQLite file instead (read-only, opened via `mode=ro` URI). All other
guards (validator, audit, query_guard) remain identical.
"""
import asyncio
import logging
import sqlite3
import time
from typing import Any

from services import config_service

from .connection import get_pool, get_test_db_path

logger = logging.getLogger("docchat.db_agent.executor")


def _sqlite_run(db_path: str, sql: str, params: list | None, timeout_sec: int, cap: int) -> dict:
    """Synchronous SQLite execution — invoked via asyncio.to_thread."""
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=timeout_sec)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql, params or [])
        records = cur.fetchall()
        columns = [d[0] for d in (cur.description or [])]
        rows: list[dict[str, Any]] = []
        for i, rec in enumerate(records):
            if i >= cap:
                break
            rows.append({k: rec[k] for k in rec.keys()})
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": len(records) > cap,
        }
    finally:
        conn.close()


def _sqlite_explain(db_path: str, sql: str) -> dict:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute("EXPLAIN QUERY PLAN " + sql).fetchall()
        plan = [" | ".join(str(c) for c in r) for r in rows]
        return {"plan": plan}
    finally:
        conn.close()


async def execute(sql: str, params: list | None = None, row_cap: int | None = None) -> dict:
    """Run a validated SELECT and return {columns, rows, row_count, elapsed_ms}."""
    timeout_sec = int(await config_service.get_setting("db_agent_query_timeout_sec", 30))
    cap = int(row_cap or await config_service.get_setting("db_agent_row_cap", 5000))

    # ── Test-mode branch: route to SQLite sandbox ──────────────────────────
    test_path = await get_test_db_path()
    if test_path:
        t0 = time.perf_counter()
        try:
            res = await asyncio.to_thread(_sqlite_run, test_path, sql, params, timeout_sec, cap)
        except sqlite3.Error as e:
            raise RuntimeError(f"SQLite error: {e}") from e
        res["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        return res

    # ── Live Postgres path (untouched) ─────────────────────────────────────
    pool = await get_pool()
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
    test_path = await get_test_db_path()
    if test_path:
        return await asyncio.to_thread(_sqlite_explain, test_path, sql)

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch("EXPLAIN " + sql)
    plan = [r[0] for r in rows]
    return {"plan": plan}
