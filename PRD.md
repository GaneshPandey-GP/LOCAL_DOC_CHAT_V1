# DocChat — Product Requirements Document

> Last updated: 2026-05-26  
> Status: Live · Self-hostable Enterprise AI Platform

## Executive Summary

DocChat is a self-hosted, enterprise-grade AI platform for grounded question-answering and agentic workflows over your own documents and websites. Teams upload PDFs, Office documents, and code, or crawl entire websites into Knowledge Bases; their questions are answered with inline citations, confidence scoring, and optional tool calls — all without any of the content ever leaving the customer's infrastructure.

DocChat solves four problems that public chat assistants cannot:

1. **Data sovereignty** — every byte of content, every embedding, every chat log stays in containers the customer runs.
2. **Citation-grade trust** — answers are bound to specific document chunks, page numbers, and confidence levels.
3. **Per-link / per-widget scoping** — share a curated subset of documents with a partner without giving them broader workspace access.
4. **Tool-augmented retrieval** — let the assistant call MCP tools (web search, HTTP APIs, SQL, GitHub, webhooks) when the documents alone aren't enough.

## Target Users

| Persona | Goal | Surfaces they use |
| --- | --- | --- |
| **Enterprise Admin (Owner role)** | Manages users, KBs, feature flags, and platform-level config | Admin pages, Settings, Feature Flags, Model Analytics |
| **Knowledge Worker (Editor role)** | Uploads documents, runs chat, builds share links and widgets | Documents, Chat, Knowledge Bases, Share Links, Embed Widget |
| **External Guest** | Reads/queries a single shared scope | Guest Share page (`/share/:token`) |
| **Developer integrating via API** | Embeds the widget, calls the API with an API key | API Keys page, Embed Widget install snippets, public `/api/v2/widget/*` |
| **Compliance / Auditor** | Verifies who shared what, when, with whom | Audit Log, Share Link History |

## Core Use Cases

1. **Upload docs and chat** — drag a PDF, get an answer with `[1]`-style citations and a HIGH/MEDIUM/LOW confidence badge in under 5 seconds.
2. **Share with a partner** — generate a tokenised share link scoped to exactly 3 documents, optionally with a password and 24h expiry.
3. **Embed on website** — paste one `<script>` tag; visitors get a branded chat widget that can only answer from the configured corpus.
4. **Crawl a website into a KB** — point DocChat at `https://docs.example.com`, set depth and selector, and chat with the live content. Re-crawl on a cron.
5. **Augment answers with tools** — enable the *Web Search* and *HTTP Request* MCP tools so the assistant can fetch fresh info inside the answer loop.
6. **Audit & observe** — see who asked what, latency, cost per model, and rate-limit hits per widget.

## Feature Inventory

### Document Management
| Feature | Status | Description |
| --- | --- | --- |
| Multi-format upload | Live | PDF, DOCX, PPTX, XLSX, CSV, TXT, MD |
| OCR for scanned docs | Live | Tesseract fallback when PyPDF returns empty text |
| Bulk assignment to editors | Live | Owner assigns docs to editors without re-uploading |
| Document categories | Live | Free-form tag per document |
| Status pipeline | Live | uploading → extracting → chunking → embedding → ready |

### Chat & RAG
| Feature | Status | Description |
| --- | --- | --- |
| Streaming SSE answers | Live | `event: meta` / `token` / `tool_calls` / `done` |
| Inline citations | Live | `[1]`-style markers wired to the citation panel |
| Confidence scoring | Live | HIGH / MEDIUM / LOW from top-hit similarity |
| Session history | Live | Saved per user; rename / delete |
| Follow-up suggestions | Live | Generated post-answer |
| Feedback ↑/↓ | Live | Stored on assistant message |
| Tool-augmented answers | Live | Optional `mcp_tool_ids` on `/v2/chat` |

### Knowledge Bases
| Feature | Status | Description |
| --- | --- | --- |
| KB CRUD | Live | document / web / hybrid types |
| Per-KB search modes | Live | vector, hybrid, bm25, ensemble |
| Per-KB top-k & threshold | Live | Owner-tunable |
| KB rollup stats | Live | chunk_count + document_count refreshed after crawl |
| Search Test tab | Live | Query the KB directly with full source attribution |

### Web Crawler
| Feature | Status | Description |
| --- | --- | --- |
| BFS recursive crawl | Live | Respects `same_origin`, `depth`, `max_pages` |
| Sitemap crawl | Live | Pulls every URL from an `sitemap.xml` |
| Single-page crawl | Live | One-shot ingest |
| robots.txt | Live | Honoured when `respect_robots=true`; soft-fail logged |
| Custom selector / exclude | Live | CSS selectors strip nav/footer noise |
| Rate limiting | Live | `rate_limit_rps` per host |
| Incremental sync | Live | Skip unchanged content via content-hash |
| Crawl preview | Live | `/v2/kb/:id/crawl/preview` — fetch one URL and inspect |
| Crawl cancel | Live | `/v2/kb/:id/crawl/cancel` mid-flight |
| Failed-URL inspection | Live | `failed_urls[]` shown in history |
| Playwright (JS-rendered) | Planned | Gated behind `ENABLE_PLAYWRIGHT_CRAWLER` — falls back to httpx today |
| Scheduled cron | Live (UI) / Pending firing | APScheduler integration is wired in DB but not yet running |

### Workflows
| Feature | Status | Description |
| --- | --- | --- |
| Workflow tables & indexes | Live | Mongo collections seeded |
| Visual canvas | Planned | ReactFlow editor — coming-soon stub today |
| DAG engine | Planned | Tracked as P2 in `ROADMAP.md` |

### MCP Tools
| Feature | Status | Description |
| --- | --- | --- |
| Built-in tools | Live | `builtin-web-search`, `builtin-http-request`, `builtin-github`, `builtin-sql-query`, `builtin-webhook` |
| Custom HTTP tools | Live | Register any HTTP endpoint with JSON schema |
| Execution history | Live | Per tool, 5 most recent runs in UI |
| Tool-call loop in RAG | Live | `rag.answer_with_tools` + streaming variant |
| Tools popover in chat | Live | Toggle which tools an answer may use |

### Share Links
| Feature | Status | Description |
| --- | --- | --- |
| Public / Password / Expiring | Live | Three creation modes |
| Single-use & domain restriction | Live | Optional |
| Per-creator metadata | Live | Filter history by editor/owner |
| KB scoping | Live | A share can include whole KBs |
| MCP tools per share | Live | Guest gets tool-augmented answers |
| Custom system prompt per share | Live | Override the default assistant persona |
| Revoke / history / analytics | Live | Audit-grade |

### Embed Widgets
| Feature | Status | Description |
| --- | --- | --- |
| Visual builder | Live | Brand colour, launcher, dark mode |
| Domain whitelist | Live | Server-side enforced |
| Rate limits | Live | Per-hour / per-day, per widget |
| KB scoping | Live | Widget can include whole KBs |
| MCP tools per widget | Live | Widget answers can call tools |
| Custom system prompt | Live | Per-widget persona |
| Visitor analytics | Live | Sessions, queries, top questions, domain breakdown |

### Admin & Analytics
| Feature | Status | Description |
| --- | --- | --- |
| User management | Live | Owners create editors |
| Audit log | Live | Every privileged action |
| Feature flags | Live | Hot-toggle on/off |
| Platform analytics | Live | Documents, sessions, query volume |
| Model analytics | Live | Per-model tokens, cost, latency |

### API Access
| Feature | Status | Description |
| --- | --- | --- |
| API key issuance | Live | `dck_` prefixed; one-way hash stored |
| API key revoke | Live | Immediate effect |
| Header auth | Live | `X-API-Key` middleware on every protected route |

## User Roles & Permissions

| Capability | Admin (Owner) | Editor | API Key (Editor scope) | Guest |
| --- | --- | --- | --- | --- |
| Upload documents | ✅ | ✅ | ✅ | ❌ |
| Chat with own docs | ✅ | ✅ | ✅ | ❌ |
| Chat with assigned docs | ✅ | ✅ | ✅ | ❌ |
| Chat scoped to share token | n/a | n/a | n/a | ✅ |
| Create KB | ✅ | ✅ | ✅ | ❌ |
| Trigger crawl | ✅ | ✅ | ✅ | ❌ |
| Workflows (planned) | 🔒 | 🔒 | 🔒 | ❌ |
| Manage MCP tools | ✅ | ✅ | ✅ | ❌ |
| Create share link | ✅ | ✅ | ✅ | ❌ |
| Create widget | ✅ | ✅ | ✅ | ❌ |
| Platform analytics | 🔒 | ❌ | ❌ | ❌ |
| Model analytics | 🔒 | ❌ | ❌ | ❌ |
| Audit log | 🔒 | ❌ | ❌ | ❌ |
| Manage users | 🔒 | ❌ | ❌ | ❌ |
| Feature flags | 🔒 | ❌ | ❌ | ❌ |

Legend: ✅ allowed · ❌ forbidden · 🔒 admin-only

## Non-Functional Requirements

### Performance
- First streaming token under 1.5 s for cached embeddings, under 3 s cold.
- Ingestion throughput target: 60 pages/minute (CPU-bound on extraction).
- Crawl throughput: configurable via `rate_limit_rps`; default 2/sec/host.

### Security
- JWT with bcrypt password hashing (cost 12).
- API keys stored as SHA-256 hashes; raw value only shown at creation.
- Guest tokens are HS256 JWTs signed with `SHARE_TOKEN_SECRET`; carry document IDs but no user identity.
- System prompts on shares/widgets are injected server-side from the persisted record — guests cannot override them via the client.
- Domain whitelist on widgets enforced server-side (header `Origin` check), not just CSS.
- All routes prefixed with `/api`; non-API paths fall through to the React SPA.

### Scalability
- Stateless backend (MongoDB + Qdrant hold all state). Horizontally scalable behind any load balancer.
- Background tasks via FastAPI `BackgroundTasks` today; queue planned (Redis + RQ) for Phase 2.

### Browser compatibility
- Modern evergreen browsers (Chrome 110+, Firefox 110+, Safari 16+). Widget loader supports clipboard `execCommand` fallback for non-secure contexts.

## Known Limitations

- Workflow engine (visual + runtime) is stubbed — only the data model and the MCP tool registry it will use are in place.
- Sync schedules can be saved in the UI but **APScheduler is not yet firing them** — cron crawls won't trigger automatically.
- No OAuth or SSO — JWT email/password only.
- No multi-tenancy — every Owner shares the same workspace.
- No vLLM / local-only LLM today; runs through the Emergent LLM key by default. Per-deployment override planned.
- No Prometheus/OpenTelemetry endpoints yet — model latency is recorded but not exposed externally.
- No native Chrome extension.

## Roadmap

**Phase 1 (current sprint)**
- Crawler robustness + cancel/preview + KB stats UI
- MCP tools wired into RAG; per-share & per-widget tool / KB / system-prompt scoping
- Workflow nav stub; production Docker setup + one-click `setup.sh`

**Phase 2 (next)**
- APScheduler crawl cron actually firing
- Redis + RQ queue for ingestion & crawls
- Workflow visual canvas (ReactFlow) + DAG runtime
- OAuth / SSO

**Phase 3 (later)**
- vLLM-served local LLMs
- Prometheus / OpenTelemetry metrics endpoint
- Native Chrome extension for ad-hoc page ingestion
- Multi-tenant workspaces
