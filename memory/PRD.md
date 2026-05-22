# DocChat v2.0 — Production Enhancement (Surgical Patch)

## Original problem statement
Apply the v2.0 surgical patch described in `docchat_enhancement_spec.md`:
seven work streams across Document Categories, Bulk Assignment, Centralized
DB-backed Config, Combined Filter Correctness, Search Icon Alignment,
Enterprise AI Database Agent, and Responsive Design. **Do not refactor unrelated
code. Do not run tests/builds/migrations. Preserve existing UI/UX and APIs.**

## Architecture (unchanged)
- Frontend: React 18 + Tailwind + shadcn/ui + Axios.
- Backend: FastAPI + MongoDB + ChromaDB + JWT/RBAC + audit log + feature flags.
- New (Stream 6): separate analytics pipeline — PostgreSQL read replica
  consumed via `backend/services/db_agent/*`. **No shared code with the RAG
  pipeline.**

## Streams delivered (Feb 2026)
- **S1 Document Category** — schema extension + ingest validation + filter +
  badge column + dropdown in upload modal.
- **S2 Bulk Document Assignment** — `POST /api/v2/documents/bulk-assign`
  (admin RBAC, idempotent `$addToSet`, audit logged). UI checkbox column +
  "Assign selected" admin toolbar.
- **S3 Centralized DB-Backed Config** — `services/config_service.py`
  resolver (`.env` > `app_settings` collection > default), public read
  endpoint `/api/v2/settings/public`, owner CRUD at `/api/admin/settings`,
  and an `App Settings` accordion in Settings.jsx.
- **S4 Combined Filter Correctness** — all filters AND-composed server-side
  in a single Mongo query. Frontend now pushes `status / access /
  uploaded_by / category / q` directly to `/api/v2/documents`.
- **S5 Search Icon Alignment** — restructured the search field; icon lives
  in its own relative wrapper around the `<Input>` with `top-1/2
  -translate-y-1/2` so it stays centered at every breakpoint.
- **S6 Enterprise AI Database Agent** (full, separate pipeline) —
  `services/db_agent/{orchestrator,schema_service,sql_generator,
  sql_validator,sql_executor,excel_exporter,query_guard,audit_service,
  connection}.py`. New router at `/api/v2/db-agent/*` and
  `/api/v2/reports/*`. Postgres pool runs `default_transaction_read_only=on`
  with `command_timeout`. SQL goes through prompt-injection guard → AST
  validation (allowlist of `SELECT/WITH`, hard-block on DDL/DML/forbidden
  functions) → safe execution → Excel export (openpyxl). All events
  recorded in `db_agent_audit`. Frontend page `DBAgent.jsx` + DB Agent
  configuration section in Settings.jsx (Postgres creds + optional
  SQL-generation LLM override; defaults to Emergent LLM key).
- **S7 Responsive Design** — Tailwind responsive prefixes across AppLayout
  (mobile hamburger drawer), Dashboard (filter row wraps, table collapses
  columns md/sm, 44px touch targets), Chat (session list hidden on mobile,
  full-width chat, full-width modals), UploadDialog & Assign dialogs.

## Files created
- `backend/services/config_service.py`
- `backend/services/db_agent/__init__.py`
- `backend/services/db_agent/audit_service.py`
- `backend/services/db_agent/connection.py`
- `backend/services/db_agent/excel_exporter.py`
- `backend/services/db_agent/orchestrator.py`
- `backend/services/db_agent/query_guard.py`
- `backend/services/db_agent/schema_service.py`
- `backend/services/db_agent/sql_executor.py`
- `backend/services/db_agent/sql_generator.py`
- `backend/services/db_agent/sql_validator.py`
- `backend/routers/db_agent.py`
- `backend/routers/settings.py`
- `frontend/src/pages/DBAgent.jsx`

## Files modified
- `backend/server.py` (register new routers)
- `backend/core/db.py` (new collections + indexes for app_settings, db_agent_*)
- `backend/routers/documents.py` (category, server-side filters, bulk-assign)
- `backend/requirements.txt` (+asyncpg, +sqlparse)
- `frontend/src/App.js` (DBAgent route)
- `frontend/src/pages/AppLayout.jsx` (hamburger drawer, DB Agent nav link)
- `frontend/src/pages/Dashboard.jsx` (category column/filter, bulk-assign,
  server-side filter call, search icon fix, responsive grid)
- `frontend/src/pages/Chat.jsx` (responsive layout, hide session list on mobile)
- `frontend/src/pages/Settings.jsx` (App Settings + DB Agent sections)
- `frontend/src/components/UploadDialog.jsx` (category dropdown, mobile width)

## API surface deltas
- `GET /api/v2/documents` now accepts `category`, `status`, `uploaded_by`,
  `access` (in addition to existing `q`, `tag`). All compose AND on server.
- `POST /api/v2/documents/ingest` now requires `category` form field.
- `POST /api/v2/documents/bulk-assign` (new, admin) — `{document_ids[],
  editor_ids[]}` → `{ok, matched, modified, …}`.
- `GET /api/v2/settings/public` (auth user) — non-secret URLs/limits.
- `GET /api/admin/settings` (owner) — full merged config + source map.
- `PUT /api/admin/settings/{key}` / `DELETE /api/admin/settings/{key}`
  (owner) — runtime override CRUD.
- DB Agent: `GET /api/v2/db-agent/status`, `GET /api/v2/db-agent/schema`,
  `POST /api/v2/db-agent/query`, `POST /api/v2/db-agent/explain`,
  `POST /api/v2/db-agent/report`, `GET /api/v2/db-agent/audit`,
  `GET /api/v2/reports/history`, `GET /api/v2/reports/{id}`,
  `GET /api/v2/reports/{id}/download`.

## New collections / indexes
- `app_settings` — { key (unique), value, updated_at }
- `documents` — added compound index `(category, created_at desc)`
- `db_agent_reports` — { id (unique), user_id, created_at desc compound }
- `db_agent_audit` — `created_at desc`, `(user_id, created_at desc)`
- `db_agent_configs` — reserved (future per-tenant agent configs)

## Migration notes
- Legacy documents without a `category` field are rendered as
  `"Uncategorized"` by the API and the badge UI. No data migration needed
  (resolver handles the absence transparently).
- `app_settings` is created lazily on first PUT; an empty collection makes
  the resolver fall through to `.env` / defaults — application starts
  identically.
- New backend deps `asyncpg` and `sqlparse` were added to
  `requirements.txt`; install on next dependency refresh.

## Backward compatibility
- All existing endpoints retain their previous responses (category appears
  as an additional field).
- Old `q`/`tag` filters still work and now compose with the new filters.
- Single-document `PATCH /v2/documents/{id}/assignments` is unchanged;
  bulk-assign is purely additive.
- Old client builds that don't send `category` will receive a 400 — this is
  intentional per Stream 1 acceptance criteria.

## Backlog / next actions
- Wire CI lint + smoke test in pipeline.
- (P1) Add per-tenant DB Agent configs (multi-cluster analytics).
- (P1) Encrypt API key fields at rest in Mongo (today plain strings).
- (P2) Surface DB Agent audit log in Admin Audit page.
- (P2) Schema-level allowlist tightening with column-level constraints.
