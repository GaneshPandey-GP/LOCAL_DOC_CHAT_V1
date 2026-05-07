# DocChat — Docker Deployment Guide

Self-contained Docker setup for the DocChat RAG application. MongoDB is
bundled as a service — **no manual MongoDB install is required** on the
host. All persistent data (database, uploaded documents, vector index)
lives in named Docker volumes.

---

## 1. Services

| Service    | Image / Build                | Port (host) | Purpose                                   |
| ---------- | ---------------------------- | ----------- | ----------------------------------------- |
| `mongodb`  | `mongo:7.0`                  | — (internal) *[27017 in dev]* | Primary datastore (users, docs, sessions, share links, audit log, widget analytics) |
| `backend`  | `./backend/Dockerfile`       | — (internal) *[8001 in dev]*  | FastAPI API, ingestion pipeline, OCR, RAG retrieval |
| `frontend` | `./frontend/Dockerfile`      | `3000`      | React SPA (nginx in prod, CRA dev server in dev) |

### Features supported out-of-the-box
- Document uploads (PDF, DOCX, PPTX, XLSX, images)
- OCR / image extraction (Tesseract + poppler-utils baked into backend image)
- Embeddings + vector storage (ChromaDB persistent volume)
- RAG retrieval with hybrid search / reranking feature flags
- Share links with signed tokens
- Owner / editor / RBAC workflows
- Embed widget + widget analytics
- Audit log persistence

---

## 2. Prerequisites

- **Docker Engine** ≥ 24.x
- **Docker Compose v2** (`docker compose`, not `docker-compose`)
- ~4 GB free RAM and ~5 GB disk for the images + volumes

No other dependencies are required on the host (MongoDB, Node, Python,
Tesseract — all bundled in images).

---

## 3. One-time setup

```bash
cp .env.example .env
# edit .env: set strong MONGO_INITDB_ROOT_PASSWORD, JWT_SECRET,
# SHARE_TOKEN_SECRET, and at least one LLM provider key.
```

Generate strong secrets:

```bash
openssl rand -hex 32   # use for JWT_SECRET
openssl rand -hex 32   # use for SHARE_TOKEN_SECRET
openssl rand -base64 24 # use for MONGO_INITDB_ROOT_PASSWORD
```

---

## 4. Production

Build and start everything:

```bash
docker compose up -d --build
```

Check health:

```bash
docker compose ps
curl http://localhost:3000/           # frontend
docker compose exec backend curl -fsS http://localhost:8001/api/health
```

The frontend is the only service bound to a host port (`3000`). Put a
reverse proxy (Caddy / nginx / Traefik) in front of it for TLS and to
forward `/api/*` to the backend container on the `docchat-net`
network. Example nginx snippet:

```nginx
location /api/ {
    proxy_pass         http://backend:8001;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
}
location / {
    proxy_pass http://frontend:3000;
}
```

Stop:

```bash
docker compose down            # keep volumes
docker compose down -v         # WIPE volumes (DB + uploads + chroma)
```

---

## 5. Development (hot-reload)

Overlays `docker-compose.dev.yml` on top of the base file:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Differences:

- `backend` runs `uvicorn --reload` with source bind-mounted from `./backend`
- `frontend` runs CRACO dev server with source bind-mounted from `./frontend`;
  `node_modules` is kept inside a named volume to avoid arch mismatches
- MongoDB port `27017` is published to the host for Compass / mongosh
- Backend port `8001` is published to the host

Shortcut alias:

```bash
alias dccd='docker compose -f docker-compose.yml -f docker-compose.dev.yml'
dccd up --build
dccd logs -f backend
dccd exec backend bash
```

---

## 6. Persistent volumes

| Volume              | Mount path (in container)      | Contains                                       |
| ------------------- | ------------------------------ | ---------------------------------------------- |
| `mongo_data`        | `/data/db`                     | MongoDB databases                              |
| `mongo_config`      | `/data/configdb`               | MongoDB config DB                              |
| `backend_uploads`   | `/app/backend/uploads`         | Uploaded source files (owner/editor workflow) |
| `backend_chroma`    | `/app/backend/chroma_db`       | ChromaDB vector index (RAG retrieval state)    |

Backup example:

```bash
docker run --rm \
  -v docchat_mongo_data:/data \
  -v $PWD:/backup \
  alpine tar czf /backup/mongo-$(date +%F).tgz -C /data .
```

---

## 7. Networking

A single bridge network `docchat-net` is created. Inside it:

- `backend` reaches the database via `mongodb://mongodb:27017` (host `mongodb`)
- `frontend` reaches the API via `http://backend:8001` (only relevant if you
  add server-side proxying inside nginx — at runtime the browser uses
  `REACT_APP_BACKEND_URL` baked at build time)

Only the `frontend` port is exposed to the host by default. Backend and
MongoDB are isolated on the internal network.

---

## 8. Health checks & startup ordering

Every service has a `healthcheck`:

- **mongodb**: `mongosh ... ping` every 15 s
- **backend**: `GET /api/health` every 30 s
- **frontend**: `wget --spider /` every 30 s

`depends_on.condition: service_healthy` enforces startup ordering —
backend only starts after MongoDB reports healthy, and frontend only
starts after backend reports healthy.

---

## 9. Environment variables — reference

All variables are documented inline in `.env.example`. Key ones:

| Variable                         | Required | Notes                                                      |
| -------------------------------- | -------- | ---------------------------------------------------------- |
| `MONGO_INITDB_ROOT_USERNAME`     | ✅       | Mongo root user (used in backend connection string)        |
| `MONGO_INITDB_ROOT_PASSWORD`     | ✅       | Strong password — never commit                             |
| `DB_NAME`                        | ✅       | Application database name                                  |
| `JWT_SECRET`                     | ✅       | 32+ byte random — required for auth tokens                 |
| `SHARE_TOKEN_SECRET`             | ✅       | Used to sign share-link tokens                             |
| `CORS_ORIGINS`                   | ✅       | Comma-separated allowed origins                            |
| `REACT_APP_BACKEND_URL`          | ✅       | Public URL of the API (baked into the prod bundle)         |
| `LLM_PROVIDER`                   | recommended | `emergent` or `openrouter`                              |
| `EMBEDDING_PROVIDER`             | recommended | `local` (no API key) or `openai`                        |
| `EMERGENT_LLM_KEY` / `OPENAI_API_KEY` / `OPENROUTER_API_KEY` | conditional | At least one matching the chosen provider |

Credentials are **never hard-coded** in any Dockerfile or compose file — everything flows from `.env`.

---

## 10. Troubleshooting

- **Backend crashes on startup with `MONGO_URL` KeyError**
  → Forgot to copy `.env`. Run `cp .env.example .env` and re-run
    `docker compose up`.

- **Uploads or chat history disappear after `docker compose down -v`**
  → `-v` removes named volumes. Use `docker compose down` (no `-v`) to
    preserve data, or take a backup first (§6).

- **OCR returns empty text**
  → Tesseract + poppler are baked in, but scanned PDFs must have the
    `ENABLE_SCANNED_PDF_OCR=true` flag (default). Check backend logs
    for `pdftoppm OK` / `Tesseract OK` on startup.

- **`REACT_APP_BACKEND_URL` change not reflected in prod**
  → CRA bakes env vars at build time. Rebuild the frontend image:
    `docker compose build --no-cache frontend && docker compose up -d frontend`.

- **Port already in use (3000 / 8001 / 27017)**
  → Change `FRONTEND_PORT` / `BACKEND_PORT` / `MONGO_PORT` in `.env`.
