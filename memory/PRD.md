# DocChat — Enterprise AI Platform Extension (Mar 2026)

## Scope delivered (per spec, with user-confirmed scope reductions)
- **Module 1 — Qdrant service layer** (replaces ChromaDB as the primary vector backend; ChromaDB kept importable for legacy code paths). Client, collections, ingestion (dense + optional SPLADE sparse), hybrid_search (RRF), retrieval orchestrator. Graceful 503 / fallback when Qdrant is unreachable.
- **Module 2 — Knowledge Base management**: full router at `/api/v2/kb` (CRUD, crawl trigger, schedule upsert, analytics, ad-hoc search). Mongo collections + indexes per spec.
- **Module 3 — Web crawler**: httpx + bs4 + markdownify BFS crawler, Playwright fallback (flag-gated), pipeline that does incremental hash-skip ingestion straight into Qdrant.
- **Module 4 — Advanced retrieval**: query rewriter, cross-encoder reranker (lazy-loaded; flag-gated), six named search strategies, context compression.
- **Module 6 — MCP tool ecosystem**: registry + dispatch executor + 5 built-in tools (web_search, http_request, github, sql_query, webhook). Router at `/api/v2/mcp` + per-tool audit log.
- **Module 8 — API keys**: `dck_…` keys with hashed storage, `X-API-Key` header path in `core.deps.get_current_user`, revocation, call-count tracking.
- **Module 9 — Model metrics + observability**: `services/model_metrics.py` and admin-only router at `/api/v2/model-analytics` (summary, by-model, latency percentiles, daily cost).

## Out of scope (skipped on user direction)
- **Module 5 — Workflow engine + visual builder**: all `backend/workflows/*`, the workflow router, and the four workflow frontend pages (`Workflows.jsx`, `WorkflowBuilder.jsx`, `WorkflowRuns.jsx`, `WorkflowRunDetail.jsx`). Mongo collections + indexes for workflows/workflow_runs are still created (so a future enable is a single feature flag flip).

## Pragmatic compromises (confirmed by user)
- **Qdrant**: docker-compose entry added (`docker-compose.qdrant.yml`). The Kubernetes preview pod cannot run Qdrant; `services/qdrant/client.health_check()` reports false and the KB endpoints degrade to clear error messages. Spin Qdrant up via `docker compose -f docker-compose.qdrant.yml up -d` then set `QDRANT_HOST` in `.env`.
- **Heavy ML deps**: only the lightweight critical set installed (`qdrant-client`, `beautifulsoup4`, `markdownify`, `networkx`, `RestrictedPython`, `APScheduler`, `rank-bm25`). The reranker uses `sentence-transformers` (lazy + flag-gated) — installs only when explicitly added; until then `rerank()` is a no-op pass-through. Playwright disabled by default — flip `ENABLE_PLAYWRIGHT_CRAWLER` + install browsers later.
- **ChromaDB → Qdrant migration**: no-op hook in `startup()` that sets `qdrant_migration_complete=True` and emits audit events. The empty install has no ChromaDB data to migrate.
- **ROLE_ADMIN**: added as alias for `ROLE_OWNER` in `core/deps.py`. No existing code refactored.

## Files created
**Backend (24):**
- `services/qdrant/{__init__,client,collections,ingestion,hybrid_search,retrieval}.py`
- `services/retrieval/{__init__,query_rewriter,reranker,search_strategies,context_compression}.py`
- `services/web_crawler/{__init__,crawler,playwright_crawler,pipeline}.py`
- `services/model_metrics.py`
- `mcp/{__init__,registry,executor}.py` and `mcp/tools/{__init__,web_search,github,sql_query,http_request,webhook}.py`
- `routers/{knowledge_base,mcp_tools,api_keys,model_analytics}.py`

**Frontend (5):**
- `pages/{KnowledgeBases,KnowledgeBaseDetail,KnowledgeBaseCrawl,MCPTools,ModelAnalytics}.jsx`

**Infrastructure:**
- `docker-compose.qdrant.yml` — Qdrant service definition with healthcheck and named volume.

## Files modified (additive only)
- `core/deps.py` — `ROLE_ADMIN` alias; X-API-Key path in `get_current_user`
- `core/config.py` — 14 new feature flags via existing `_bool_env()` helper
- `core/db.py` — 13 new collections + their indexes
- `services/config_service.py` — 17 new DEFAULT_SETTINGS keys for the new modules
- `server.py` — `sys.path` for top-level packages, 4 new router registrations, builtin MCP tool seed (idempotent), Qdrant migration hook
- `requirements.txt` — added qdrant-client / beautifulsoup4 / markdownify / networkx / RestrictedPython / APScheduler / rank-bm25 (versions pinned)
- `package.json` — `@xyflow/react`, `react-hot-toast` (via yarn add)
- `App.js` — 5 new routes
- `AppLayout.jsx` — Knowledge + AI Studio sections, Model Analytics admin link

## API delta
- `GET POST DELETE /api/v2/kb` + `GET PATCH /:id` + `POST /:id/crawl` + `GET /:id/crawl/status` + `GET /:id/crawl/history` + `POST /:id/crawl/retry` + `POST /:id/schedule` + `DELETE /:id/schedule` + `GET /schedules/all` + `GET /:id/analytics` + `POST /:id/search`
- `POST GET DELETE /api/v2/mcp/tools` + `GET PATCH /:id` + `POST /:id/test` + `GET /:id/executions`
- `POST GET DELETE /api/v2/api-keys`
- `GET /api/v2/model-analytics/{summary,by-model,latency,cost}`

## Verified end-to-end
- Backend boots clean (5 builtin MCP tools seeded, Qdrant migration hook ran no-op)
- Login still works; existing routes untouched
- `GET /api/v2/kb` + `POST /api/v2/kb` create returns 201 with full doc
- `GET /api/v2/mcp/tools` returns the 5 seeded builtins
- `POST /api/v2/mcp/tools/builtin-web-search/test` returns `{ok:true}` against DuckDuckGo
- `GET /api/v2/api-keys` works
- `GET /api/v2/model-analytics/summary` returns zero-state struct
- Knowledge Bases UI lists the seeded test KB; MCP Tools UI lists 5 builtins with test buttons
- Lint clean on all new files

## Next Action Items
- (P0) Provision Qdrant: `docker compose -f docker-compose.qdrant.yml up -d qdrant` → set `QDRANT_HOST=<your-host>` in `/app/backend/.env`. KB ingest + search will start writing real vectors.
- (P1) For production-grade reranking, install `sentence-transformers` and flip `ENABLE_RERANKER=true`.
- (P1) For JS-rendered crawls install `playwright` + `playwright install chromium` and flip `ENABLE_PLAYWRIGHT_CRAWLER=true`.
- (P2) Re-introduce the Workflow engine (skipped here) — Mongo collections + indexes are already in place; only the backend `workflows/*` package and the frontend builder need to be added.
- (P2) Wrap existing `services.llm.chat_complete` with `model_metrics.record_call()` so the Model Analytics dashboard immediately starts populating without code changes elsewhere.
