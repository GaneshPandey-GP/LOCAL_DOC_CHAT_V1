"""Schema introspection for the DB Agent (Stream 6).

Returns ONLY the schemas/tables the agent is allowed to see (allowlist from
settings: db_agent_allowed_schemas, comma-separated; defaults to "public").
The LLM must never see anything outside this subset.
"""
import logging
from typing import Optional

from services import config_service

from .connection import get_pool

logger = logging.getLogger("docchat.db_agent.schema")

_cached_schema: Optional[dict] = None
_cached_key: Optional[str] = None


async def _allowed_schemas() -> list[str]:
    raw = await config_service.get_setting("db_agent_allowed_schemas", "public")
    return [s.strip() for s in str(raw).split(",") if s.strip()]


async def introspect(force: bool = False) -> dict:
    """Return {schemas: [...], tables: {schema.table: [{column, type, nullable}]}}."""
    global _cached_schema, _cached_key
    schemas = await _allowed_schemas()
    cache_key = ",".join(sorted(schemas))
    if not force and _cached_schema is not None and _cached_key == cache_key:
        return _cached_schema

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT table_schema, table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = ANY($1::text[])
            ORDER BY table_schema, table_name, ordinal_position
            """,
            schemas,
        )
    tables: dict[str, list[dict]] = {}
    for r in rows:
        key = f"{r['table_schema']}.{r['table_name']}"
        tables.setdefault(key, []).append({
            "column": r["column_name"],
            "type": r["data_type"],
            "nullable": (r["is_nullable"] == "YES"),
        })
    _cached_schema = {"schemas": schemas, "tables": tables}
    _cached_key = cache_key
    return _cached_schema


def invalidate() -> None:
    global _cached_schema, _cached_key
    _cached_schema = None
    _cached_key = None


def format_for_llm(schema: dict, limit_tables: int = 40) -> str:
    """Format the schema in a compact, LLM-friendly form."""
    lines = []
    items = list(schema["tables"].items())[:limit_tables]
    for tbl, cols in items:
        col_str = ", ".join(f"{c['column']}:{c['type']}" for c in cols[:30])
        lines.append(f"- {tbl}({col_str})")
    if len(schema["tables"]) > limit_tables:
        lines.append(f"… ({len(schema['tables']) - limit_tables} more tables truncated)")
    return "\n".join(lines)


def column_allowlist(schema: dict) -> set[str]:
    """Return the set of fully-qualified table.column identifiers permitted."""
    out: set[str] = set()
    for tbl, cols in schema["tables"].items():
        for c in cols:
            out.add(f"{tbl}.{c['column']}")
            out.add(c["column"])  # unqualified for convenience
    return out
