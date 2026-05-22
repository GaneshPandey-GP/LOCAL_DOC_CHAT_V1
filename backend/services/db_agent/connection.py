"""Postgres connection pool for the DB Agent (Stream 6).

Uses asyncpg as a read-only analytics pool. Credentials come from
config_service so they can be set at runtime from the Settings UI.
Connection pool is rebuilt automatically when the DSN changes.
"""
import logging
from typing import Optional

from services import config_service

logger = logging.getLogger("docchat.db_agent.connection")

try:
    import asyncpg  # type: ignore
    _ASYNCPG_AVAILABLE = True
except Exception:  # pragma: no cover — optional dep
    asyncpg = None  # type: ignore
    _ASYNCPG_AVAILABLE = False

_pool = None
_pool_key: Optional[str] = None


def _dsn_from(cfg: dict) -> str:
    user = cfg.get("db_agent_postgres_user") or ""
    pwd = cfg.get("db_agent_postgres_password") or ""
    host = cfg.get("db_agent_postgres_host") or ""
    port = cfg.get("db_agent_postgres_port") or 5432
    db = cfg.get("db_agent_postgres_db") or ""
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


async def _gather_config() -> dict:
    return {
        "db_agent_enabled": await config_service.get_setting("db_agent_enabled", False),
        "db_agent_postgres_host": await config_service.get_setting("db_agent_postgres_host", ""),
        "db_agent_postgres_port": await config_service.get_setting("db_agent_postgres_port", 5432),
        "db_agent_postgres_db": await config_service.get_setting("db_agent_postgres_db", ""),
        "db_agent_postgres_user": await config_service.get_setting("db_agent_postgres_user", ""),
        "db_agent_postgres_password": await config_service.get_setting("db_agent_postgres_password", ""),
        "db_agent_query_timeout_sec": int(await config_service.get_setting("db_agent_query_timeout_sec", 30)),
    }


async def get_pool():
    """Return the asyncpg pool, building it lazily and rebuilding on DSN change."""
    global _pool, _pool_key
    if not _ASYNCPG_AVAILABLE:
        raise RuntimeError(
            "asyncpg is not installed. Add it to backend/requirements.txt to enable "
            "the DB Agent's PostgreSQL connectivity."
        )
    cfg = await _gather_config()
    if not cfg["db_agent_enabled"]:
        raise RuntimeError("DB Agent is disabled. Enable it via Settings → DB Agent.")
    if not (cfg["db_agent_postgres_host"] and cfg["db_agent_postgres_db"] and cfg["db_agent_postgres_user"]):
        raise RuntimeError(
            "DB Agent PostgreSQL credentials are not configured. "
            "Provide host, database and user via Settings → DB Agent."
        )
    dsn = _dsn_from(cfg)
    if _pool is None or _pool_key != dsn:
        if _pool is not None:
            try:
                await _pool.close()
            except Exception:
                pass
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=5,
            command_timeout=cfg["db_agent_query_timeout_sec"],
            server_settings={"default_transaction_read_only": "on"},
        )
        _pool_key = dsn
        logger.info("DB Agent pool created host=%s db=%s", cfg["db_agent_postgres_host"], cfg["db_agent_postgres_db"])
    return _pool


async def close_pool() -> None:
    global _pool, _pool_key
    if _pool is not None:
        try:
            await _pool.close()
        except Exception:
            pass
        _pool = None
        _pool_key = None


# ─────────────────────────────────────────────────────────────────────────────
# Test Database (sandbox SQLite) routing
#
# When a `.db` file has been uploaded via Settings → Test Database, the
# orchestrator/executor/schema_service route ALL queries to that file
# instead of the production Postgres pool. Production config (host/user/pwd)
# is left untouched — removing the file reverts seamlessly to live mode.
# ─────────────────────────────────────────────────────────────────────────────
async def get_test_db_path() -> str:
    """Return the active test-DB filesystem path, or empty string."""
    path = await config_service.get_setting("db_agent_test_db_path", "")
    if not path:
        return ""
    from pathlib import Path
    return path if Path(path).exists() else ""


async def is_test_mode_active() -> bool:
    return bool(await get_test_db_path())
