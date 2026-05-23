"""DocChat — enterprise RAG backend."""
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")
# Allow top-level imports for `workflows` and `mcp` packages added in Module 5 + 6.
sys.path.insert(0, str(ROOT_DIR))

from core.db import init_indexes  # noqa: E402
from routers import (  # noqa: E402
    admin, api_keys, auth, chat, db_agent, documents, feedback, flags,
    knowledge_base, mcp_tools, model_analytics, sessions,
    settings as settings_router, share, widgets, widget_public,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("docchat")

app = FastAPI(title="DocChat API", version="2.0.0")

api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"service": "docchat", "version": "2.0.0"}


@api_router.get("/health")
async def health():
    return {"status": "ok"}


# Public share-link info (no auth)
from routers.share import router as share_router  # noqa: E402

api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(sessions.router)
api_router.include_router(feedback.router)
api_router.include_router(share.router)
api_router.include_router(flags.router)
api_router.include_router(flags.admin_router)
api_router.include_router(admin.router)
api_router.include_router(widgets.router)
api_router.include_router(widget_public.router)
# Stream 3 — Centralized DB-backed settings
api_router.include_router(settings_router.router)
api_router.include_router(settings_router.admin_router)
# Stream 6 — Enterprise AI Database Agent (separate pipeline)
api_router.include_router(db_agent.router)
api_router.include_router(db_agent.reports_router)
# ── Enterprise AI Platform (Mar 2026) ────────────────────────────────────────
api_router.include_router(knowledge_base.router)
api_router.include_router(mcp_tools.router)
api_router.include_router(api_keys.router)
api_router.include_router(model_analytics.router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    try:
        await init_indexes()
        logger.info("MongoDB indexes initialized")
    except Exception as e:
        logger.warning("init_indexes failed: %s", e)

    # Ensure Tesseract OCR binary is available (required for image/PDF OCR)
    import shutil, subprocess
    if not shutil.which("tesseract"):
        logger.warning("Tesseract not found — installing via apt-get…")
        try:
            subprocess.run(
                ["apt-get", "install", "-y", "-qq", "tesseract-ocr", "tesseract-ocr-eng"],
                check=True, capture_output=True, timeout=120,
            )
            logger.info("Tesseract installed successfully")
        except Exception as te:
            logger.error("Tesseract auto-install failed: %s — OCR features will be degraded", te)
    else:
        logger.info("Tesseract OK: %s", shutil.which("tesseract"))

    # Ensure poppler-utils (pdftoppm) is available for scanned PDF OCR
    if not shutil.which("pdftoppm"):
        logger.warning("pdftoppm not found — installing poppler-utils…")
        try:
            subprocess.run(
                ["apt-get", "install", "-y", "-qq", "poppler-utils"],
                check=True, capture_output=True, timeout=120,
            )
            logger.info("poppler-utils installed successfully")
        except Exception as pe:
            logger.error("poppler-utils auto-install failed: %s — scanned PDF OCR skipped", pe)
    else:
        logger.info("pdftoppm OK: %s", shutil.which("pdftoppm"))

    # ── Seed built-in MCP tools (idempotent) ────────────────────────────────
    try:
        from core.db import mcp_tools as _mcp
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        builtins = [
            {"id": "builtin-web-search", "name": "Web Search",
             "description": "DuckDuckGo Instant Answer + related topics.",
             "endpoint_type": "builtin",
             "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
            {"id": "builtin-http-request", "name": "HTTP Request",
             "description": "Generic configurable HTTP call.",
             "endpoint_type": "builtin",
             "input_schema": {"type": "object", "properties": {
                 "method": {"type": "string"}, "url": {"type": "string"},
                 "headers": {"type": "object"}, "body": {}}}},
            {"id": "builtin-github", "name": "GitHub",
             "description": "Public GitHub REST API surface (search/repos, files, issues).",
             "endpoint_type": "builtin",
             "input_schema": {"type": "object", "properties": {"op": {"type": "string"}}}},
            {"id": "builtin-sql-query", "name": "SQL Query (read-only)",
             "description": "Run a single SELECT on a configured Postgres DSN.",
             "endpoint_type": "builtin",
             "input_schema": {"type": "object", "properties": {"dsn": {"type": "string"}, "sql": {"type": "string"}}, "required": ["dsn", "sql"]}},
            {"id": "builtin-webhook", "name": "Webhook",
             "description": "POST a payload to a registered webhook.",
             "endpoint_type": "builtin",
             "input_schema": {"type": "object", "properties": {"webhook_id": {"type": "string"}, "payload": {}}, "required": ["webhook_id"]}},
        ]
        for t in builtins:
            await _mcp.update_one(
                {"id": t["id"]},
                {"$set": {**t, "is_builtin": True, "owner_id": "system", "enabled": True, "updated_at": now},
                 "$setOnInsert": {"created_at": now, "call_count": 0}},
                upsert=True,
            )
        logger.info("Built-in MCP tools seeded (%d)", len(builtins))
    except Exception as e:
        logger.warning("MCP tool seed failed: %s", e)

    # ── ChromaDB → Qdrant one-time migration hook ──────────────────────────
    # Empty install — mark complete so we don't churn on every restart.
    try:
        from services import config_service
        from core.audit import log_event
        if not await config_service.get_setting("qdrant_migration_complete", False):
            await log_event("qdrant_migration_started", actor_id="system", actor_role="system",
                            resource_type="system", resource_id="qdrant", metadata={})
            await config_service.set_setting("qdrant_migration_complete", True)
            await log_event("qdrant_migration_completed", actor_id="system", actor_role="system",
                            resource_type="system", resource_id="qdrant",
                            metadata={"note": "no-op (no ChromaDB data present)"})
            logger.info("Qdrant migration hook completed (no-op)")
    except Exception as e:
        logger.warning("Qdrant migration hook failed: %s", e)
