# DocChat — PRD / Project Record

## Original problem statement
> "just create a docker file"
>
> Refined by user: produce separate Dockerfiles for frontend & backend, a
> full `docker-compose.yml` setup (+ dev overlay), optimized for both dev
> and prod, with MongoDB bundled (not installed on host), persistent
> volumes for uploads / vector store / DB, health checks, startup
> dependency handling, env examples, and deployment docs. No code
> refactors, no running containers.

## Stack detected (from uploaded DOC_CHAT-master zip)
- **Backend**: Python 3.11 + FastAPI + Motor (MongoDB) + ChromaDB + Tesseract OCR + poppler-utils; port `8001`
- **Frontend**: React 19 + CRACO + Tailwind (yarn); dev port `3000`, prod served via nginx on `3000`
- **DB**: MongoDB (motor async driver, indexes created on startup)
- **Vector store**: ChromaDB persistent client at `backend/chroma_db`
- **Uploads**: `backend/uploads`

## Deliverables (all created — no code changes made to the app)
| File | Purpose |
| --- | --- |
| `backend/Dockerfile` | Multi-stage production image (wheels builder → slim runtime) with Tesseract, poppler, libmagic, non-root user, healthcheck |
| `backend/Dockerfile.dev` | Single-stage dev image with `uvicorn --reload` |
| `backend/.dockerignore` | Excludes `__pycache__`, local state dirs, secrets |
| `frontend/Dockerfile` | Multi-stage: yarn build → nginx:1.27-alpine; `REACT_APP_BACKEND_URL` via build-arg |
| `frontend/Dockerfile.dev` | CRA dev server with polling enabled for bind-mount hot-reload |
| `frontend/nginx.conf` | SPA fallback, gzip, long-cache for `/static/`, security headers |
| `frontend/.dockerignore` | Excludes `node_modules`, `build`, secrets |
| `docker-compose.yml` | Prod stack: mongodb + backend + frontend + named volumes + internal bridge network + healthchecks |
| `docker-compose.dev.yml` | Dev overlay: hot-reload, bind mounts, host-published ports |
| `.env.example` | Root env template consumed by compose |
| `backend/.env.example` | Reference for bare-metal backend runs |
| `frontend/.env.example` | Reference for bare-metal frontend runs |
| `DOCKER.md` | End-to-end deployment guide (prod, dev, volumes, networking, troubleshooting) |

## Guarantees
- ✅ MongoDB runs **inside docker-compose** — no host install needed
- ✅ Persistent volumes: `mongo_data`, `mongo_config`, `backend_uploads`, `backend_chroma`
- ✅ Internal bridge network `docchat-net` — backend connects via `mongodb://mongodb:27017`
- ✅ `depends_on` + healthchecks enforce proper startup order (mongo → backend → frontend)
- ✅ No credentials hard-coded; everything flows from `.env`
- ✅ Env structure preserved (`MONGO_URL`, `DB_NAME`, `REACT_APP_BACKEND_URL` untouched in code)
- ✅ Supports OCR, embeddings, share links, RAG, owner/editor workflows, widget analytics
- ✅ No application code refactored; only infra files added
- ✅ Nothing was built or run

## Backlog (P1/P2)
- P1: Add optional Traefik/Caddy sidecar for TLS termination in `docker-compose.prod.yml`
- P2: Add GitHub Actions workflow to build & push images to a registry
- P2: Add `docker-compose.monitoring.yml` overlay (Prometheus + Grafana) for RAG metrics

## Next action items
- User runs `cp .env.example .env`, fills in secrets + LLM key, then `docker compose up -d --build`
