"""LLM-driven natural-language → SQL generation (Stream 6).

Uses an OpenAI-compatible chat completion. The active model can be configured
independently from the main RAG LLM via:
  • db_agent_llm_provider / db_agent_llm_model / db_agent_llm_api_key / db_agent_llm_base_url
  • Or falls back to the RAG-active LLM (services.llm) when not set.

Critical: the LLM is shown ONLY the introspected schema subset, never the user
input verbatim without guard checks, and never the raw connection string.
"""
import json
import logging
import re
from typing import Optional

from openai import AsyncOpenAI

from services import config_service

from . import schema_service

logger = logging.getLogger("docchat.db_agent.sql_generator")

SYSTEM_PROMPT_PG = """You are a senior SQL analyst working on a read-only PostgreSQL analytics replica.

RULES (absolute):
1. Generate ONE PostgreSQL SELECT (or WITH … SELECT) statement only.
2. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, EXEC, COPY.
3. Reference only tables/columns from the schema given below. Do NOT invent.
4. Always include a LIMIT clause (cap at {row_cap}) unless the user explicitly asks for an aggregate.
5. Prefer parameterized JOINs, GROUP BY, window functions for analytics.
6. Output STRICT JSON in the form:
   {{"sql": "...", "explanation": "one-paragraph plain-English summary"}}
   No markdown, no commentary outside the JSON object.

ALLOWED SCHEMA:
{schema_text}
"""

SYSTEM_PROMPT_SQLITE = """You are a senior SQL analyst working on a read-only SQLite sandbox database (Test Mode).

RULES (absolute):
1. Generate ONE SQLite SELECT (or WITH … SELECT) statement only.
2. Use SQLite-compatible syntax — no PostgreSQL-only functions (no date_trunc, no ::cast, no INTERVAL keyword). Prefer `strftime`, `date`, `julianday`, CAST(x AS …).
3. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, EXEC.
4. Reference only tables/columns from the schema given below. Do NOT invent.
5. Always include a LIMIT clause (cap at {row_cap}) unless the user explicitly asks for an aggregate.
6. Output STRICT JSON in the form:
   {{"sql": "...", "explanation": "one-paragraph plain-English summary"}}
   No markdown, no commentary outside the JSON object.

ALLOWED SCHEMA:
{schema_text}
"""

# Backward-compat alias
SYSTEM_PROMPT = SYSTEM_PROMPT_PG


async def _get_client_and_model() -> tuple[AsyncOpenAI, str]:
    """Build the LLM client for the DB agent, falling back to the RAG LLM."""
    provider = await config_service.get_setting("db_agent_llm_provider", "")
    model_id = await config_service.get_setting("db_agent_llm_model", "")
    api_key = await config_service.get_setting("db_agent_llm_api_key", "")
    base_url = await config_service.get_setting("db_agent_llm_base_url", "")

    if not (provider and model_id):
        # Fallback to whatever services.llm has active
        from services.llm import _get_active_config  # type: ignore
        cfg = await _get_active_config()
        provider = provider or cfg.get("provider", "emergent")
        model_id = model_id or cfg.get("model_id", "gpt-4o-mini")
        api_key = api_key or cfg.get("api_key") or ""
        base_url = base_url or cfg.get("api_base_url") or ""

    # Resolve key/base from env if still missing
    from core import config as cfg_mod
    if not api_key:
        if provider == "emergent":
            api_key = cfg_mod.EMERGENT_LLM_KEY
        elif provider == "openrouter":
            api_key = cfg_mod.OPENROUTER_API_KEY
        elif provider == "openai":
            api_key = cfg_mod.OPENAI_API_KEY
    if not base_url:
        if provider == "emergent":
            base_url = cfg_mod.EMERGENT_BASE_URL
        elif provider == "openrouter":
            base_url = cfg_mod.OPENROUTER_BASE_URL

    if not api_key:
        raise RuntimeError(
            "No LLM API key for the DB Agent. Configure db_agent_llm_api_key in "
            "Settings → DB Agent, or set the active RAG LLM."
        )
    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return AsyncOpenAI(**kwargs), model_id


def _clean_sql(sql: str) -> str:
    s = (sql or "").strip()
    s = re.sub(r"^```(?:sql)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    return s


async def generate_sql(natural_query: str, row_cap: int = 1000) -> dict:
    """Return {"sql": str, "explanation": str}."""
    schema = await schema_service.introspect()
    schema_text = schema_service.format_for_llm(schema)
    # Pick dialect-aware prompt based on the introspected engine
    template = SYSTEM_PROMPT_SQLITE if schema.get("engine") == "sqlite" else SYSTEM_PROMPT_PG
    system = template.format(row_cap=row_cap, schema_text=schema_text)

    client, model = await _get_client_and_model()
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": natural_query.strip()},
        ],
        temperature=0,
    )
    raw = (resp.choices[0].message.content or "").strip()
    # Try strict JSON first; if fails, salvage SQL block.
    try:
        # Strip markdown fences if model didn't follow the JSON-only rule
        cleaned = re.sub(r"^```(?:json)?", "", raw).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        data = json.loads(cleaned)
        sql = _clean_sql(str(data.get("sql", "")))
        explanation = str(data.get("explanation", "")) or "Generated SQL"
    except Exception:
        # Salvage: extract first SQL-looking block
        m = re.search(r"(?:```sql)?\s*(SELECT[\s\S]+?)(?:```|$)", raw, re.IGNORECASE)
        sql = _clean_sql(m.group(1) if m else raw)
        explanation = "Generated SQL (unstructured response)"

    return {"sql": sql, "explanation": explanation}
