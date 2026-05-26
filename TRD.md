# DocChat — Technical Reference Document

> Last updated: 2026-05-26  
> Target audience: engineers maintaining or extending the platform

## Architecture Overview

```mermaid
graph TD
    Browser["Browser (React SPA)"] -->|"/api/*"| FastAPI
    Browser -->|"static assets"| Nginx
    Nginx -->|"reverse proxy /api"| FastAPI
    FastAPI -->|"motor (async)"| MongoDB[("MongoDB 7.0")]
    FastAPI -->|"REST / gRPC"| Qdrant[("Qdrant")]
    FastAPI -->|"litellm"| LLM["LLM Providers<br/>(Emergent / OpenAI / Anthropic / Gemini)"]
    FastAPI -->|"disk"| Files[("/app/backend/uploads")]
    FastAPI -->|"legacy fallback"| Chroma[("ChromaDB (legacy)")]
```

### RAG pipeline

```mermaid
graph LR
    Query[User query] --> Retrieve
    Retrieve -->|"top_k chunks"| Build[Build prompt with context]
    Build --> LLM1[LLM call #1]
    LLM1 -->|"TOOL_CALL: ?"| Branch{Tool calls?}
    Branch -- no --> Stream[Stream tokens to client]
    Branch -- yes --> Exec[Execute MCP tools]
    Exec --> LLM2[LLM call #2 with results]
    LLM2 --> Stream
```

### MCP tool-call loop

```mermaid
sequenceDiagram
    Client->>+FastAPI: POST /api/v2/chat (mcp_tool_ids=[...])
    FastAPI->>FastAPI: retrieve()
    FastAPI->>LLM: chat_complete(prompt+tools_section)
    LLM-->>FastAPI: "TOOL_CALL: Web Search({\"query\":...})"
    FastAPI->>MCPExecutor: execute_mcp_tool()
    MCPExecutor-->>FastAPI: {abstract, results}
    FastAPI->>LLM: chat_stream(prompt + TOOL_RESULT)
    LLM-->>FastAPI: final answer (streaming)
    FastAPI-->>-Client: SSE tokens
```

## Tech Stack

| Layer | Technology | Version | Notes |
| --- | --- | --- | --- |
| Backend runtime | Python | 3.11 | |
| API framework | FastAPI | 0.115+ | Async throughout |
| ASGI server | Uvicorn | 0.35+ | 2 workers in prod |
| Database driver | Motor | 3.7+ | Async MongoDB |
| Database | MongoDB | 7.0 | Schemaless |
| Vector store | Qdrant | latest | Hybrid dense + sparse |
| Embeddings | fastembed | 0.7+ | `all-MiniLM-L6-v2` 384-d |
| LLM gateway | litellm | latest | Routes Emergent / OpenAI / Anthropic / Gemini |
| Legacy vector store | ChromaDB | optional | Migration-only fallback |
| OCR | tesseract-ocr | system pkg | Required for scanned PDFs |
| PDF parsing | pypdf + poppler-utils | system pkg | poppler enables image extraction |
| Web crawler | httpx + BeautifulSoup + lxml | latest | Playwright optional |
| Scheduler | APScheduler | 3.x | Wired but not yet running cron |
| Frontend framework | React | 19 | CRA via craco |
| UI primitives | shadcn/ui (radix-ui) | latest | |
| Icons | @phosphor-icons/react | latest | |
| Charts | recharts | latest | |
| HTTP client | axios | 1.x | |
| Build | yarn (frozen lockfile) | 1.22+ | npm intentionally not supported |
| Reverse proxy | Nginx | 1.25-alpine | SSE-aware |
| Container runtime | Docker + Compose v2 | 24+ / 2.20+ | |

## Project Structure

```
/app
├── backend/                     # FastAPI service
│   ├── server.py                # Entry; mounts all routers, runs startup hooks
│   ├── requirements.txt         # Frozen via pip freeze
│   ├── .env.example             # Sample env (real .env is gitignored)
│   ├── core/                    # Cross-cutting helpers
│   │   ├── auth.py              # JWT issue + verify
│   │   ├── security.py          # bcrypt + share-token signing
│   │   ├── deps.py              # FastAPI DI: get_current_user, ROLE_* constants
│   │   ├── config.py            # Feature flags + tunables
│   │   └── db.py                # Motor client, collection refs, index creation
│   ├── routers/                 # One module per resource
│   │   ├── auth.py              # /auth/login, /auth/register
│   │   ├── documents.py         # CRUD + upload
│   │   ├── chat.py              # /v2/chat — streaming SSE with optional tool loop
│   │   ├── sessions.py          # /v2/sessions
│   │   ├── share.py             # /v2/share-links
│   │   ├── widgets.py           # Owner-side CRUD for widgets
│   │   ├── widget_public.py     # /api/widget/*  — public surface
│   │   ├── knowledge_base.py    # /v2/kb (CRUD, search, crawl, schedule)
│   │   ├── mcp_tools.py         # /v2/mcp/tools (CRUD + test + executions)
│   │   ├── api_keys.py          # /v2/api-keys
│   │   ├── model_analytics.py   # /v2/model-analytics
│   │   ├── admin.py             # Owner-only analytics + audit
│   │   └── settings.py          # /v2/settings (kv store, test DB upload)
│   ├── services/                # Business logic, framework-free
│   │   ├── llm.py               # litellm wrapper
│   │   ├── embeddings.py        # fastembed wrapper
│   │   ├── rag.py               # retrieve + answer{_stream}{_with_tools}
│   │   ├── chunking.py          # Page-aware splitter
│   │   ├── extraction.py        # PDF / DOCX / OCR
│   │   ├── ingestion.py         # Pipeline orchestrator
│   │   ├── kb_utils.py          # KB → doc-id resolver (additive helper)
│   │   ├── model_metrics.py     # token / cost / latency recorder
│   │   ├── qdrant/              # Collection mgmt, ingestion, hybrid search
│   │   ├── retrieval/           # Strategy router: vector / bm25 / ensemble
│   │   ├── web_crawler/         # crawler.py (httpx) + playwright_crawler.py + pipeline.py
│   │   └── db_agent/            # SQL-over-DB agent (sandbox & live)
│   ├── mcp/                     # MCP tool registry + executor
│   │   ├── registry.py
│   │   ├── executor.py
│   │   └── tools/               # builtin_*.py modules
│   └── tests/                   # pytest suite
├── frontend/                    # React SPA
│   ├── package.json
│   ├── yarn.lock                # NEVER hand-edited; `yarn install --frozen-lockfile`
│   ├── public/
│   └── src/
│       ├── App.js               # Router root
│       ├── lib/api.js           # axios w/ baseURL + auth interceptor
│       ├── lib/auth.jsx         # AuthProvider context
│       ├── components/          # ConfidenceBadge, MarkdownMessage, ShareScopeAddons, ui/*
│       └── pages/               # One file per route
├── nginx/
│   ├── nginx.conf               # Reverse proxy + SSE-friendly config
│   └── ssl/.gitkeep             # Drop fullchain.pem + privkey.pem here
├── Dockerfile                   # Backend image
├── Dockerfile.frontend          # React build + Nginx runtime
├── docker-compose.yml           # mongodb + qdrant + backend + frontend
├── docker-compose.qdrant.yml    # Qdrant-only (dev convenience)
├── .env.example                 # Authoritative variable list
├── setup.sh                     # One-click idempotent deploy
└── memory/                      # PRD / CHANGELOG / ROADMAP / test_credentials
```

## Backend Modules

### Auth (`core/security.py`, `routers/auth.py`)
- `POST /api/auth/register` — first call seeds the Owner; subsequent registrations require an Owner JWT and create Editors.
- `POST /api/auth/login` — returns `{ access_token, token_type: "bearer" }`. JWT carries `sub` (user id) and `role`. 24h TTL.
- Password hashing: bcrypt cost 12 via `passlib`.
- Token middleware: `Authorization: Bearer …` → `get_current_user`; or `X-API-Key: dck_…` → user lookup via hash table.

### Documents (`routers/documents.py`, `services/ingestion.py`, `extraction.py`, `chunking.py`)
- Status state machine: `uploading → extracting → chunking → embedding → ready` (or `failed` with `error` field).
- Owners always see all docs; Editors see their uploads + `assigned_to` array hits.
- Chunks are page-aware (`page` field preserved through to citations).

### RAG Pipeline (`services/rag.py`, `services/llm.py`, `services/embeddings.py`)
- `retrieve()` → `Qdrant.search()` → hits with `text, filename, page, document_id, chunk_id, score`.
- `build_messages()` injects retrieved chunks as `Context:\n[1] …` blocks.
- `answer_stream()` → returns `(AsyncIterator[str], hits, confidence)`.
- `answer_with_tools()` → loop: LLM call → parse `TOOL_CALL:` lines → execute MCP tools → second LLM call with `TOOL_RESULT:` block appended → return final text + `tool_calls_made`. Falls back to plain `answer()` when no tools.
- Confidence is bucketed from top-hit similarity: ≥0.75 HIGH, ≥0.5 MEDIUM, else LOW.

### Qdrant (`services/qdrant/`)
- Collection per user: `docchat_<user-id-hex>`.
- Dense vector: 384-d cosine (fastembed default).
- Sparse vector: SPLADE-style if `fastembed[sparse]` installed; silently disabled otherwise.
- Hybrid search via RRF fusion (`hybrid_search.py`).
- Server mode if `qdrant_host` looks like a hostname; **embedded mode** (filesystem path) used when `qdrant_host` starts with `/` — useful in pods without a separate container.
- Health check at `services.qdrant.client.health_check()` — every crawl preflight calls it and 503s out if down.

### Knowledge Bases (`routers/knowledge_base.py`)
- KB type: `document` (uploads-only), `web` (crawled), or `hybrid`.
- `chunk_count` / `document_count` are rollups refreshed at the end of every successful crawl.
- `search_mode`: `vector | hybrid | bm25 | ensemble`. Configurable per KB.
- Endpoints: CRUD · `/search` · `/crawl` · `/crawl/status` · `/crawl/history` · `/crawl/cancel` · `/crawl/preview` · `/schedule`.

### Web Crawler (`services/web_crawler/`)
- `crawler.py` — async httpx + BeautifulSoup + lxml. Follow-redirects, configurable user-agent, robots.txt honoured with soft-fail.
- `playwright_crawler.py` — JS-rendered crawler. Loaded lazily; if Playwright isn't installed, `_pick_crawler()` returns the httpx one.
- `pipeline.py` — `run_crawl_job(job_id)` is the background task. Tries-catches every exception and writes `status="failed" + error` to the job doc; per-page status is incremented via `$inc` so the UI sees live progress. Cancellation polled at the start of every page iteration.
- Content hash dedup: `crawl_history` filtered by `(kb_id, url)` — unchanged pages count as `pages_skipped`, not failures.

### Workflows (planned)
- Mongo collections live in `db.py`: `workflows`, `workflow_runs`, `tool_executions` (indexed by `tool_id` + `(run_id, node_id)`).
- Backend engine is NOT yet implemented. Frontend renders a coming-soon stub.

### MCP Tools (`mcp/`, `routers/mcp_tools.py`)
- Registry seeded on startup with 5 built-ins: `builtin-web-search`, `builtin-http-request`, `builtin-github`, `builtin-sql-query`, `builtin-webhook`.
- Executor dispatches by `endpoint_type`: `builtin` (Python module) or `http` (POST to `endpoint_url`).
- Every call is logged to `tool_executions` for the UI's "Recent executions" panel.
- Tool-call loop in `rag.answer_with_tools` parses `TOOL_CALL: <name>({"k":"v"})` lines via regex; tools resolvable by both id and name (case-insensitive).

### Share Links (`routers/share.py`)
- Persisted fields: `token`, `mode`, `document_ids`, `kb_ids`, `mcp_tool_ids`, `system_prompt`, expiry, password_hash, domain_restriction, creator metadata.
- Guest payload: HS256 JWT signed with `SHARE_TOKEN_SECRET`. Carries only `share_token` + `document_ids`; KBs / tools / system_prompt are pulled server-side at chat time from the persisted link record so a guest cannot tamper with them.

### Widgets (`routers/widgets.py`, `routers/widget_public.py`)
- Same KB / tool / system-prompt augmentation as share links.
- `allowed_domains` and rate limits enforced server-side; `/api/widget/:id/config` returns sanitised config.

### Admin (`routers/admin.py`)
- `/v2/admin/analytics` — counts + 30-day query volume.
- `/v2/admin/audit` — every privileged action logged via `log_event()`.
- User & feature-flag mgmt routes here.

### API Keys (`routers/api_keys.py`)
- Issued as `dck_<32-hex>`; SHA-256 hash stored; only the prefix + last 4 are persisted for display.
- Middleware in `core/deps.py` resolves `X-API-Key` → user before any role check.

## Database Schema

> All collections use a UUIDv4 `id` field as primary key; `_id` is the implicit Mongo ObjectId we never expose.

| Collection | Key fields | Indexes |
| --- | --- | --- |
| `users` | id, email, password_hash, role, name | `email` unique |
| `documents` | id, owner_id, filename, status, file_type, kb_id, category, chunk_count, assigned_to[], created_at | owner_id, kb_id, (owner_id, status), assigned_to |
| `sessions` | id, owner_id, title, scope_doc_ids[], created_at, updated_at | owner_id, updated_at |
| `messages` | id, session_id, role, content, citations[], confidence, tool_calls[], latency_ms, created_at | session_id |
| `share_links` | token, owner_id, document_ids[], kb_ids[], mcp_tool_ids[], system_prompt, mode, password_hash, expires_at, single_use, domain_restriction, opens, revoked | token unique, owner_id |
| `widgets` | id, widget_id, owner_id, name, config, document_ids[], kb_ids[], mcp_tool_ids[], system_prompt, allowed_domains[], rate_limit_hour, rate_limit_day, is_active | widget_id unique, owner_id |
| `widget_events` | widget_id, session_id, visitor_id, type, timestamp, meta | widget_id, (widget_id, timestamp) |
| `app_settings` | key, value, updated_at | key unique |
| `feature_flags` | key, value, updated_at | key unique |
| `audit_log` | id, action, actor_id, resource_type, resource_id, ip, metadata, ts | ts, actor_id |
| `knowledge_bases` | id, owner_id, name, type, web_root_url, sitemap_url, selector, exclude_selectors[], search_mode, top_k, similarity_threshold, chunk_count, document_count, last_crawled_at | owner_id |
| `crawl_jobs` | id, kb_id, owner_id, status, config, pages_found, pages_crawled, pages_skipped, pages_failed, failed_urls[], chunks_added, queued_at, started_at, ended_at, error | kb_id, (kb_id, queued_at desc), status |
| `crawl_history` | kb_id, url, content_hash, last_seen_at | (kb_id, url) unique |
| `sync_schedules` | id, kb_id, cron_expr, enabled, crawl_config | kb_id |
| `workflows` | id, owner_id, name, graph, status | owner_id |
| `workflow_runs` | id, workflow_id, status, started_at, ended_at | workflow_id, status |
| `mcp_tools` | id, owner_id, name, description, endpoint_type, endpoint_url, input_schema, enabled, is_builtin, call_count | id unique, (owner_id, is_builtin) |
| `tool_executions` | id, tool_id, run_id, node_id, status, input, result, elapsed_ms, created_at | tool_id, (run_id, node_id), (tool_id, created_at desc) |
| `agent_memory` | id, owner_id, key, value, ttl | (owner_id, key) |
| `api_keys` | id, owner_id, key_hash, key_prefix, last_used_at, revoked, created_at | key_hash unique, owner_id |
| `integrations` | id, owner_id, type, config | owner_id |
| `model_metrics` | id, model, tokens_prompt, tokens_completion, cost, latency_ms, created_at | (model, created_at desc) |
| `webhooks` | id, owner_id, url, events[] | owner_id |

## API Reference

> All routes prefixed `/api`. Auth column: 🔑 JWT or API key · 🔒 Owner only · 🌐 Public

### Auth & users
| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | /auth/register | 🌐* | First call seeds Owner; later calls require Owner JWT |
| POST | /auth/login | 🌐 | Returns access_token |
| GET | /auth/me | 🔑 | Current user |

### Documents & Chat
| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | /v2/documents | 🔑 | Multipart upload |
| GET | /v2/documents | 🔑 | List user-accessible docs |
| DELETE | /v2/documents/:id | 🔑 | Soft-delete |
| POST | /v2/chat | 🔑 + 🌐(guest_token) | SSE stream; supports `mcp_tool_ids` |
| GET | /v2/sessions | 🔑 | List sessions |
| GET | /v2/sessions/:id/messages | 🔑 | |
| PATCH | /v2/sessions/:id | 🔑 | Rename |
| DELETE | /v2/sessions/:id | 🔑 | |

### Knowledge Bases
| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET/POST | /v2/kb | 🔑 | List / create KB |
| GET/PATCH/DELETE | /v2/kb/:id | 🔑 | |
| POST | /v2/kb/:id/search | 🔑 | Returns hits w/ filename, page, chunk_index, score, kb_name |
| POST | /v2/kb/:id/crawl | 🔑 | URL preflight + Qdrant preflight; 422/503 on failure |
| POST | /v2/kb/:id/crawl/cancel | 🔑 | |
| POST | /v2/kb/:id/crawl/preview | 🔑 | Returns title, content_preview, word_count, status_code |
| GET | /v2/kb/:id/crawl/status | 🔑 | |
| GET | /v2/kb/:id/crawl/history | 🔑 | Includes `failed_urls[]` |
| POST | /v2/kb/:id/crawl/retry | 🔑 | |
| POST/DELETE | /v2/kb/:id/schedule | 🔑 | Cron — *not yet firing* |

### MCP Tools
| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET/POST | /v2/mcp/tools | 🔑 | |
| PATCH/DELETE | /v2/mcp/tools/:id | 🔑 | |
| POST | /v2/mcp/tools/:id/test | 🔑 | Returns `{ok, result|error}` |
| GET | /v2/mcp/tools/:id/executions | 🔑 | `?limit=5` |

### Share Links & Widgets
| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET/POST | /v2/share-links | 🔑 | Now accepts kb_ids, mcp_tool_ids, system_prompt |
| DELETE | /v2/share-links/:token | 🔑 | Revoke |
| GET | /share/:token | 🌐 | Guest landing page in SPA |
| GET/POST | /v2/widgets | 🔑 | |
| PATCH/DELETE | /v2/widgets/:widget_id | 🔑 | |
| GET | /v2/widgets/:widget_id/analytics | 🔑 | |
| GET | /widget/:widget_id/config | 🌐 | Public config |
| POST | /widget/:widget_id/chat | 🌐 | Public SSE |
| GET | /widget/loader.js | 🌐 | Bootstrap script |
| GET | /widget/:widget_id/iframe | 🌐 | Standalone widget HTML |

### Admin & Observability
| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | /v2/admin/analytics | 🔒 | |
| GET | /v2/admin/audit | 🔒 | |
| GET/POST/PATCH | /v2/admin/users | 🔒 | |
| GET/PATCH | /v2/admin/flags | 🔒 | |
| GET | /v2/model-analytics/summary | 🔒 | |
| GET | /v2/model-analytics/by-model | 🔒 | |
| GET | /v2/model-analytics/latency | 🔒 | |
| GET | /v2/model-analytics/cost | 🔒 | |

### Misc
| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | /health | 🌐 | Liveness |
| GET | /v2/flags | 🔑 | Feature flag snapshot |
| GET/POST | /v2/settings/* | 🔒 | KV store + test DB upload |
| POST | /v2/db-agent/query | 🔑 | NL → SQL → exec (sandbox or live) |
| GET/POST | /v2/api-keys | 🔑 | Issue / list |
| DELETE | /v2/api-keys/:id | 🔑 | Revoke |

## Environment Variables

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| MONGO_URL | ✅ | — | `mongodb://user:pass@host:27017/?authSource=admin` |
| DB_NAME | ✅ | — | Mongo database name |
| MONGO_INITDB_ROOT_USERNAME | ✅ (compose) | — | Used to bootstrap the mongo container |
| MONGO_INITDB_ROOT_PASSWORD | ✅ (compose) | — | |
| JWT_SECRET | ✅ | — | HS256 signing key for JWTs |
| SHARE_TOKEN_SECRET | ✅ | — | HS256 signing key for guest tokens |
| REACT_APP_BACKEND_URL | ✅ | — | Public origin the frontend uses for `/api` |
| EMERGENT_LLM_KEY | one of | — | Default LLM gateway |
| OPENROUTER_API_KEY | one of | — | |
| OPENAI_API_KEY | one of | — | |
| ANTHROPIC_API_KEY | one of | — | |
| LLM_PROVIDER | ❌ | emergent | `emergent | openai | anthropic | openrouter` |
| LLM_MODEL | ❌ | gpt-4o-mini | Default model id |
| EMBEDDING_PROVIDER | ❌ | local | `local | openai` |
| EMBEDDING_MODEL | ❌ | all-MiniLM-L6-v2 | |
| QDRANT_HOST | ❌ | qdrant | Hostname OR absolute path for embedded mode |
| QDRANT_PORT | ❌ | 6333 | |
| GITHUB_TOKEN | ❌ | — | Used by `builtin-github` MCP tool |
| CORS_ORIGINS | ❌ | * | Comma-separated origin list |

## Feature Flags (Mongo `feature_flags`)

| Flag | Default | Description | Module |
| --- | --- | --- | --- |
| ENABLE_WEB_CRAWLER | true | Master kill-switch | Crawler |
| ENABLE_PLAYWRIGHT_CRAWLER | false | Use Playwright instead of httpx | Crawler |
| ENABLE_BM25 | true | Surface BM25 search mode | KB |
| ENABLE_RERANKER | false | Cross-encoder reranker | RAG |
| ENABLE_HYBRID_SEARCH | true | Vector + sparse + RRF | KB |
| ENABLE_MCP_TOOLS | true | | MCP |
| ENABLE_WORKFLOWS | false | Hides nav stub | Workflows |
| ENABLE_API_KEYS | true | | API |
| ENABLE_MODEL_METRICS | true | | Admin |
| ENABLE_WIDGETS | true | | Widgets |
| ENABLE_DB_AGENT | true | | DB Agent |
| ENABLE_TEST_DB | true | SQLite sandbox upload | DB Agent |
| ENABLE_SCHEDULES | true (UI) | APScheduler not yet firing | Crawler |
| ENABLE_QDRANT | true | Else falls back to ChromaDB | Vector |

## Vector Store Details

- **Naming**: `docchat_<sha1(user_id)[:16]>` — owner-scoped; isolates tenants.
- **Dense vector**: 384-d, cosine, fastembed `BAAI/bge-small-en-v1.5` or `all-MiniLM-L6-v2`.
- **Sparse vector**: SPLADE via `fastembed[sparse]`. Auto-disabled if package not installed.
- **Hybrid fusion**: Reciprocal Rank Fusion (`k=60`) over the dense + sparse result sets.
- **Embedded mode**: pass a filesystem path as `qdrant_host` (e.g. `/app/backend/qdrant_data`) and `QdrantClient(path=…)` is used — no network listener needed. Useful in K8s pods that can't run sidecars.
- **Migration from Chroma**: at startup `services/qdrant/migration.py:migrate_if_present()` is a no-op unless `app_settings.migrate_chroma=true`.

## Security Model

- **JWT lifecycle**: 24h `access_token`; no refresh tokens. Re-login required after expiry.
- **Guest tokens**: issued only when a share-link landing page is rendered; carry `share_token`, `document_ids`, expiry. Cannot reach any route except `/v2/chat` and only with `guest_token=…`.
- **API key middleware**: runs before role-check; replaces `request.state.user` so downstream routes don't care about the auth scheme.
- **RBAC pattern**: `Depends(require_role(ROLE_X))` — owner satisfies every role. `ROLE_ADMIN` is an alias of `ROLE_OWNER` for newer code paths.
- **System prompt injection**: shares and widgets persist `system_prompt` and `mcp_tool_ids` on the link/widget record. Guests sending a chat request **cannot override these** — the server resolves them from the stored record after decoding the guest token. This prevents prompt-injection escalation from a malicious client.
- **Domain whitelist**: widget endpoints check the `Origin` header against `allowed_domains` (wildcard `*.foo.com` supported). Rejected with 403.

## Deployment

See `docker-compose.yml`, `Dockerfile`, `Dockerfile.frontend`, `nginx/nginx.conf`, and `setup.sh`.

**Production checklist**

1. `cp .env.example .env` — fill in `JWT_SECRET`, `SHARE_TOKEN_SECRET`, `MONGO_INITDB_ROOT_PASSWORD`, at least one LLM key, `REACT_APP_BACKEND_URL`.
2. Place TLS certs at `nginx/ssl/fullchain.pem` and `nginx/ssl/privkey.pem` (Let's Encrypt: `sudo certbot certonly --standalone -d yourdomain.com`).
3. `./setup.sh` — pulls images, builds, brings stack up, waits for health, prints the URL.
4. Open `https://yourdomain.com/register` to seed the first Owner. The register route is auto-disabled after the first user is created.
5. Subsequent deploys: `./setup.sh --update`. Logs: `./setup.sh --logs`.
