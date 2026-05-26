"""MongoDB connection and collection access."""
import os
from motor.motor_asyncio import AsyncIOMotorClient

_mongo_url = os.environ["MONGO_URL"]
_db_name = os.environ["DB_NAME"]

client = AsyncIOMotorClient(_mongo_url)
db = client[_db_name]

# Collections
users = db.users
documents = db.documents
sessions = db.sessions
messages = db.messages
share_links = db.share_links
feedback = db.feedback
audit_log = db.audit_log
analytics_events = db.analytics_events

# Embed widget collections
embed_widgets = db.embed_widgets
widget_sessions = db.widget_sessions
widget_events = db.widget_events

# Model configurations (stored in DB, not .env)
model_configs = db.model_configs

# Centralized app settings (Stream 3 — runtime config with .env > DB > default)
app_settings = db.app_settings

# DB Agent (Stream 6) — separate analytics pipeline
db_agent_reports = db.db_agent_reports
db_agent_audit = db.db_agent_audit
db_agent_configs = db.db_agent_configs

# ── Enterprise AI Platform (Mar 2026) ────────────────────────────────────────
knowledge_bases = db.knowledge_bases
crawl_jobs = db.crawl_jobs
crawl_history = db.crawl_history
sync_schedules = db.sync_schedules
workflows = db.workflows
workflow_runs = db.workflow_runs
mcp_tools = db.mcp_tools
tool_executions = db.tool_executions
agent_memory = db.agent_memory
api_keys = db.api_keys
integrations = db.integrations
model_metrics = db.model_metrics
webhooks = db.webhooks


async def init_indexes():
    """Create indexes for common queries."""
    await users.create_index("email", unique=True)
    await documents.create_index([("owner_id", 1), ("created_at", -1)])
    await documents.create_index("content_hash")  # fast duplicate detection
    await sessions.create_index([("user_id", 1), ("updated_at", -1)])
    await messages.create_index([("session_id", 1), ("created_at", 1)])
    await share_links.create_index("token", unique=True)
    await audit_log.create_index([("created_at", -1)])
    await audit_log.create_index([("actor_id", 1), ("created_at", -1)])
    await analytics_events.create_index([("created_at", -1)])
    # Embed widget indexes
    await embed_widgets.create_index("widget_id", unique=True)
    await embed_widgets.create_index([("owner_id", 1), ("created_at", -1)])
    await widget_sessions.create_index([("widget_id", 1), ("started_at", -1)])
    await widget_sessions.create_index([("widget_id", 1), ("visitor_id", 1)])
    await widget_events.create_index([("widget_id", 1), ("event_type", 1), ("created_at", -1)])
    await widget_events.create_index([("widget_id", 1), ("visitor_id", 1), ("event_type", 1), ("created_at", -1)])
    # Model configs
    await model_configs.create_index("id", unique=True)
    await model_configs.create_index([("model_type", 1), ("is_active", 1)])
    # App settings (Stream 3)
    await app_settings.create_index("key", unique=True)
    # Document category (Stream 1) — composite index for filtered listing
    await documents.create_index([("category", 1), ("created_at", -1)])
    # DB Agent (Stream 6)
    await db_agent_reports.create_index("id", unique=True)
    await db_agent_reports.create_index([("user_id", 1), ("created_at", -1)])
    await db_agent_audit.create_index([("created_at", -1)])
    await db_agent_audit.create_index([("user_id", 1), ("created_at", -1)])
    await db_agent_configs.create_index("key", unique=True)
    # ── Enterprise AI Platform indexes ──────────────────────────────────────
    await knowledge_bases.create_index("id", unique=True)
    await knowledge_bases.create_index([("owner_id", 1), ("created_at", -1)])
    await knowledge_bases.create_index("type")
    await crawl_jobs.create_index("id", unique=True)
    await crawl_jobs.create_index([("kb_id", 1), ("status", 1)])
    await crawl_jobs.create_index([("kb_id", 1), ("started_at", -1)])
    await crawl_history.create_index([("kb_id", 1), ("url", 1)])
    await crawl_history.create_index("content_hash")
    await sync_schedules.create_index("kb_id", unique=True)
    await workflows.create_index("id", unique=True)
    await workflows.create_index([("owner_id", 1), ("created_at", -1)])
    await workflow_runs.create_index("id", unique=True)
    await workflow_runs.create_index([("workflow_id", 1), ("status", 1)])
    await workflow_runs.create_index([("workflow_id", 1), ("started_at", -1)])
    await mcp_tools.create_index("id", unique=True)
    await mcp_tools.create_index([("owner_id", 1), ("enabled", 1)])
    await tool_executions.create_index([("run_id", 1), ("node_id", 1)])
    await tool_executions.create_index("tool_id")
    await tool_executions.create_index([("tool_id", 1), ("created_at", -1)])
    await agent_memory.create_index([("session_id", 1), ("key", 1)])
    await api_keys.create_index("key_hash", unique=True)
    await api_keys.create_index("owner_id")
    await model_metrics.create_index([("model_id", 1), ("created_at", -1)])
    await webhooks.create_index("id", unique=True)
    await webhooks.create_index("owner_id")
