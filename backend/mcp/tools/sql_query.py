"""Built-in read-only SQL tool over asyncpg.

Input: {"dsn": "postgres://…", "sql": "SELECT …", "params": [...]}
Output: {"columns": [...], "rows": [...], "row_count": N}

Strict allowlist — rejects anything that isn't SELECT/WITH (multiple-statement
detection delegated to a simple split + first-token check).
"""
from __future__ import annotations

import re

try:
    import asyncpg
    _AVAILABLE = True
except Exception:
    _AVAILABLE = False


def _is_select_only(sql: str) -> bool:
    stmts = [s.strip() for s in sql.split(";") if s.strip()]
    if len(stmts) != 1:
        return False
    first = re.match(r"\s*(\w+)", stmts[0])
    if not first:
        return False
    return first.group(1).upper() in ("SELECT", "WITH")


async def run(tool_input: dict) -> dict:
    if not _AVAILABLE:
        return {"error": "asyncpg not installed"}
    dsn = (tool_input or {}).get("dsn") or ""
    sql = (tool_input or {}).get("sql") or ""
    params = (tool_input or {}).get("params") or []
    if not dsn:
        return {"error": "dsn required"}
    if not _is_select_only(sql):
        return {"error": "Only single SELECT/WITH queries are allowed"}
    conn = await asyncpg.connect(dsn=dsn, server_settings={"default_transaction_read_only": "on"})
    try:
        async with conn.transaction(readonly=True):
            stmt = await conn.prepare(sql)
            recs = await stmt.fetch(*params, timeout=30)
            rows = [dict(r) for r in recs[:1000]]
            cols = list(rows[0].keys()) if rows else []
            return {"columns": cols, "rows": rows, "row_count": len(rows)}
    finally:
        await conn.close()
