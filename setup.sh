#!/bin/bash
# ─── DocChat one-click installer ─────────────────────────────────────────────
# Idempotent: safe to run multiple times. Supports --update and --logs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colours
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[0;34m'; NC='\033[0m'
ok()    { echo -e "${G}✓${NC} $*"; }
warn()  { echo -e "${Y}⚠${NC} $*"; }
err()   { echo -e "${R}✗${NC} $*" >&2; }
info()  { echo -e "${B}→${NC} $*"; }

# ── flag parsing ───────────────────────────────────────────────────────────
MODE="install"
case "${1:-}" in
    --update) MODE="update" ;;
    --logs)   MODE="logs" ;;
    --help|-h)
        cat <<EOF
DocChat installer

Usage: ./setup.sh              First-time install (or re-validate config)
       ./setup.sh --update     Pull latest images, rebuild, restart
       ./setup.sh --logs       Tail combined service logs
       ./setup.sh --help       Show this message
EOF
        exit 0
        ;;
    "" ) ;;
    *) err "Unknown flag: $1"; exit 2 ;;
esac

# ── quick paths ────────────────────────────────────────────────────────────
if [[ "$MODE" == "logs" ]]; then
    exec docker compose logs -f
fi

# ── 1. OS check ────────────────────────────────────────────────────────────
if [[ "$(uname -s)" != "Linux" ]]; then
    warn "Detected $(uname -s). DocChat is verified on Ubuntu 22.04 / 24.04."
fi
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    if [[ "${ID:-}" != "ubuntu" ]] || [[ "${VERSION_ID:-}" != "22.04" && "${VERSION_ID:-}" != "24.04" ]]; then
        warn "OS ${PRETTY_NAME:-unknown} is untested. Continuing anyway."
    fi
fi

# ── 2. Prerequisites ───────────────────────────────────────────────────────
need_install=0
if ! command -v docker >/dev/null 2>&1; then
    err "Docker is not installed."
    need_install=1
fi
if ! docker compose version >/dev/null 2>&1; then
    err "Docker Compose v2 is not installed (need 'docker compose', not 'docker-compose')."
    need_install=1
fi
if [[ $need_install -eq 1 ]]; then
    cat <<EOF

Install Docker Engine + Compose plugin:
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker \$USER
    # log out & back in so the group takes effect

Then re-run: ./setup.sh
EOF
    exit 1
fi
ok "Docker $(docker --version | awk '{print $3}' | tr -d ,) + Compose $(docker compose version --short)"

# Skip env/SSL/build prompts in --update mode
if [[ "$MODE" == "install" ]]; then
    # ── 3. .env file ───────────────────────────────────────────────────────
    if [[ ! -f .env ]]; then
        if [[ ! -f .env.example ]]; then
            err ".env.example not found. Is this the DocChat repo root?"
            exit 1
        fi
        cp .env.example .env
        warn ".env file created from .env.example — EDIT IT NOW before continuing."
        warn "Set JWT_SECRET, SHARE_TOKEN_SECRET, MONGO password, and your LLM API key, then re-run this script."
        echo
        echo "Generate secrets quickly:"
        echo "  echo \"JWT_SECRET=\$(openssl rand -hex 32)\""
        echo "  echo \"SHARE_TOKEN_SECRET=\$(openssl rand -hex 32)\""
        exit 1
    fi
    ok ".env present"

    # ── 4. Required env vars ───────────────────────────────────────────────
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a

    missing=()
    [[ -z "${JWT_SECRET:-}" ]]          && missing+=("JWT_SECRET")
    [[ -z "${SHARE_TOKEN_SECRET:-}" ]]  && missing+=("SHARE_TOKEN_SECRET")
    [[ -z "${MONGO_URL:-}" ]]           && missing+=("MONGO_URL")
    [[ -z "${REACT_APP_BACKEND_URL:-}" ]] && missing+=("REACT_APP_BACKEND_URL")

    if [[ -z "${EMERGENT_LLM_KEY:-}" && -z "${OPENAI_API_KEY:-}" && -z "${OPENROUTER_API_KEY:-}" && -z "${ANTHROPIC_API_KEY:-}" ]]; then
        missing+=("EMERGENT_LLM_KEY or OPENAI_API_KEY or OPENROUTER_API_KEY or ANTHROPIC_API_KEY")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        err "Missing required env variables:"
        for v in "${missing[@]}"; do echo "   - $v"; done
        exit 1
    fi
    ok "Required env vars set"

    # ── 5. SSL certs ───────────────────────────────────────────────────────
    if [[ ! -f nginx/ssl/fullchain.pem || ! -f nginx/ssl/privkey.pem ]]; then
        warn "SSL certificates not found at nginx/ssl/."
        warn "Place fullchain.pem and privkey.pem there, or use Let's Encrypt:"
        warn "   sudo certbot certonly --standalone -d yourdomain.com"
        read -rp "Continue without SSL? (LOCAL TESTING ONLY) [y/N] " ans
        if [[ ! "$ans" =~ ^[Yy]$ ]]; then
            err "Aborting. Provision SSL certs and re-run."
            exit 1
        fi
        warn "Continuing without SSL — DO NOT USE THIS IN PRODUCTION."
    else
        ok "SSL certs present"
    fi
fi

# ── 6. Build / pull ────────────────────────────────────────────────────────
info "Pulling base images …"
docker compose pull --ignore-pull-failures || true
info "Building DocChat images …"
if [[ "$MODE" == "update" ]]; then
    docker compose up -d --no-deps --build
else
    docker compose build --no-cache
    info "Starting services …"
    docker compose up -d
fi

# ── 7. Wait for health ─────────────────────────────────────────────────────
info "Waiting for services to become healthy …"
deadline=$((SECONDS + 120))
healthy=0
while [[ $SECONDS -lt $deadline ]]; do
    healthy_count=$(docker compose ps --format json 2>/dev/null \
        | python3 -c "import sys,json;cnt=0
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    try:
        d=json.loads(line)
    except Exception:
        continue
    if isinstance(d,list):
        for x in d:
            if x.get('Health')=='healthy' or x.get('State')=='running' and not x.get('Health'):
                cnt+=1
    else:
        if d.get('Health')=='healthy' or (d.get('State')=='running' and not d.get('Health')):
            cnt+=1
print(cnt)" 2>/dev/null || echo 0)
    if [[ "$healthy_count" -ge 4 ]]; then
        healthy=1; echo; break
    fi
    printf '.'
    sleep 5
done

if [[ $healthy -eq 0 ]]; then
    err "Services failed to become healthy in 120 seconds."
    err "Check logs: docker compose logs"
    exit 1
fi
ok "All services healthy"

# ── 8. Backend smoke test ──────────────────────────────────────────────────
info "Verifying backend …"
if ! docker compose exec -T backend curl -fsS http://localhost:8001/api/health >/dev/null 2>&1; then
    err "Backend health check failed — check logs: docker compose logs backend"
    exit 1
fi
ok "Backend responding"

# ── 9. Success banner ──────────────────────────────────────────────────────
set +u
URL="${REACT_APP_BACKEND_URL:-https://localhost}"
set -u
cat <<EOF

${G}
   ____             ____ _           _
  |  _ \  ___   ___|  _ \ |__   __ _| |_
  | | | |/ _ \ / __| | | | '_ \ / _\` | __|
  | |_| | (_) | (__| |_| | | | | (_| | |_
  |____/ \___/ \___|____/|_| |_|\__,_|\__|
${NC}
   DocChat is up.

   ${B}URL${NC}        : ${URL}
   ${B}Register${NC}   : ${URL}/register     (first call creates the Owner; route auto-disables afterwards)
   ${B}Logs${NC}       : ./setup.sh --logs
   ${B}Update${NC}     : ./setup.sh --update

EOF
