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

## 2026-05-26 — Phase A + B + C + D delivered (this session)

**Phase A — Backend correctness (additive only)**
- Crawler robustness: pipeline.py wraps run_crawl_job in broad try/except, per-page `$inc` updates, cancellation polled every iteration, `failed_urls[]` per job, KB rollup of chunk_count + document_count at end. crawler.py: follow_redirects=True, configurable User-Agent, content-type skip, 30s timeout, robots.txt soft-fail logged.
- New endpoints: `POST /v2/kb/:id/crawl/cancel`, `POST /v2/kb/:id/crawl/preview`. `/v2/kb/:id/crawl` now URL-preflights with HEAD/GET (422 on unreachable) and Qdrant-preflights (503 if down). Response is the full job document.
- `/v2/kb/:id/search` enriches every hit with filename / page / chunk_index / score / kb_id / kb_name.
- RAG: `answer_with_tools` + `answer_stream_with_tools` implement a 2-pass TOOL_CALL loop; `system_prompt` parameter wired everywhere. `_TOOL_CALL_RE` allows spaces in tool name; tools resolved by both name & id.
- `chat.py` ChatRequest accepts `mcp_tool_ids`; SSE adds `event: tool_calls`; non-streaming response returns `tool_calls[]`.
- `share.py` + `widgets.py` + `widget_public.py` persist & honour `kb_ids`, `mcp_tool_ids`, `system_prompt`. Guests/widget visitors cannot override these from the client — server resolves them from the persisted record.
- `services/kb_utils.py` added — pure additive `resolve_kb_document_ids` helper.
- `core/db.py` adds `tool_executions.tool_id` index.

**Phase B — Frontend wiring**
- `KnowledgeBaseCrawl.jsx`: preview button + modal, cancel button, status colour map covers failed/cancelled, failed_urls expandable row, 422 toast on Start Crawl, zero-pages warning banner.
- `KnowledgeBases.jsx`: warning emoji on cards with chunk_count=0 after crawl.
- `KnowledgeBaseDetail.jsx`: bold filename, colored score badge (green>0.7 / yellow / red), confidence pill, KB name badge.
- `MCPTools.jsx`: "Built-ins missing" warning, structured input fields driven by `input_schema.properties` (with enum/boolean/object/integer handling), inline last-5-executions per tool.
- `ShareLinks.jsx` + `EmbedWidget.jsx`: reuse new `ShareScopeAddons` component to add KB multi-select + MCP tools multi-select + system prompt textarea (with character counter + reset button). The server-side API-key warning fires for builtin-github and builtin-sql-query.
- `Chat.jsx`: Tools popover button in input toolbar (only when ≥1 tool available); sends `mcp_tool_ids` on the request; collapsible "tools used" section above each answer.

**Phase C — Workflows nav stub**
- `pages/Workflows.jsx` coming-soon page added.
- `App.js` registers `/app/workflows`, `/app/workflows/:wfId/builder`, `/app/workflows/:wfId/runs`, `/app/workflows/runs/:runId` — all pointing at the stub.
- `AppLayout.jsx` adds Workflows NavItem under AI Studio with GitBranch icon.

**Phase D — Docs + Docker**
- `/app/PRD.md` + `/app/TRD.md` written from scratch with full feature inventory, RBAC matrix, Mermaid diagrams, complete API/schema/env/flag tables, deployment checklist.
- `/app/Dockerfile` (python:3.11-slim + tesseract + poppler + playwright chromium + healthcheck).
- `/app/Dockerfile.frontend` (node:20-alpine → nginx:1.25-alpine multi-stage with `yarn install --frozen-lockfile`).
- `/app/nginx/nginx.conf` (HTTP→HTTPS redirect, TLS 1.2/1.3, HSTS, `/api/v2/chat` + `/api/widget/*/chat` SSE-friendly proxying with `proxy_buffering off` + 300s timeouts, SPA fallback `try_files`).
- `/app/docker-compose.yml` (mongo + qdrant + backend + frontend with healthchecks + named volumes + bridge network).
- `/app/.env.example` + `/app/nginx/ssl/.gitkeep` + `.gitignore` additions.
- `/app/setup.sh` — idempotent one-click installer with `--update`, `--logs`, OS/Docker/env/SSL preflight, 120s health wait, success banner.

**Testing this session**
- Backend regression: 35/35 pytest pass (24 baseline `test_enterprise_ai.py` + 11 new `test_phase_ab.py`).
- Frontend smoke: 5/5 routes load with 0 console errors. All new UI elements render correctly.
- No critical or minor bugs flagged.

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

## 2026-05-24 — Phase 1+2+3 Verification (this session)
- Configured Qdrant embedded mode by setting `qdrant_host = /app/backend/qdrant_data` in `app_settings` so KB features work in the preview pod without a separate Qdrant container.
- End-to-end live crawl of https://example.com succeeded: pages_crawled=1, chunks_added=1 ingested to embedded Qdrant; hybrid search returned the crawled content with score 0.72.
- Testing agent ran the full regression suite at `/app/backend/tests/test_enterprise_ai.py` — **24/24 backend tests pass (100%)** across Auth, KB CRUD, KB search (vector/hybrid/bm25/ensemble), live crawl, MCP built-ins, MCP custom CRUD, API key issuance/auth/revocation, model analytics endpoints, RBAC alias.

## Next Action Items
- (P0) Provision Qdrant: `docker compose -f docker-compose.qdrant.yml up -d qdrant` → set `QDRANT_HOST=<your-host>` in `/app/backend/.env`. KB ingest + search will start writing real vectors.
- (P1) For production-grade reranking, install `sentence-transformers` and flip `ENABLE_RERANKER=true`.
- (P1) For JS-rendered crawls install `playwright` + `playwright install chromium` and flip `ENABLE_PLAYWRIGHT_CRAWLER=true`.
- (P2) Re-introduce the Workflow engine (skipped here) — Mongo collections + indexes are already in place; only the backend `workflows/*` package and the frontend builder need to be added.
- (P2) Wrap existing `services.llm.chat_complete` with `model_metrics.record_call()` so the Model Analytics dashboard immediately starts populating without code changes elsewhere.
