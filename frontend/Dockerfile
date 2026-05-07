# ============================================================================
# DocChat Frontend - Production Dockerfile (multi-stage, nginx served)
# ============================================================================
# Stage 1 builds the React app via CRACO; Stage 2 serves the static bundle
# through nginx on port 80. REACT_APP_BACKEND_URL is baked at build time.
# ============================================================================

# -------- Stage 1: build ----------------------------------------------------
FROM node:20-bookworm-slim AS builder

ENV CI=true \
    GENERATE_SOURCEMAP=false \
    NODE_OPTIONS=--max-old-space-size=4096

WORKDIR /app/frontend

# Install deps first for optimal layer caching
COPY package.json yarn.lock* ./
RUN corepack enable \
 && yarn install --frozen-lockfile --network-timeout 600000

# Build arg so REACT_APP_BACKEND_URL is compiled into the static bundle
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=${REACT_APP_BACKEND_URL}

# Copy source and build
COPY . .
RUN yarn build

# -------- Stage 2: runtime (nginx) ------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Non-root-friendly nginx config (listens on 3000 to match dev parity)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built static assets
COPY --from=builder /app/frontend/build /usr/share/nginx/html

# Healthcheck (wget is in nginx:alpine base image)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --spider -q http://localhost:3000/ || exit 1

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
