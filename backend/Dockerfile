# ============================================================================
# DocChat Backend - Production Dockerfile (multi-stage, optimized)
# ============================================================================
# Builds a minimal runtime image for the FastAPI backend, including every
# OS dependency the ingestion/OCR/RAG pipeline needs (tesseract, poppler,
# libmagic, libgl for chromadb/onnxruntime).
# ============================================================================

# -------- Stage 1: builder (compile wheels) ---------------------------------
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build-time system libs (compilers + dev headers for cryptography, pillow,
# pymupdf, lxml, onnxruntime, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libffi-dev \
        libssl-dev \
        libxml2-dev \
        libxslt1-dev \
        libjpeg-dev \
        zlib1g-dev \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .

# Build wheels into /wheels for a cached, reusable layer
RUN pip install --upgrade pip setuptools wheel \
 && pip wheel --wheel-dir=/wheels -r requirements.txt

# -------- Stage 2: runtime --------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/backend \
    UPLOAD_DIR=/app/backend/uploads \
    CHROMA_DIR=/app/backend/chroma_db

# Runtime OS deps required by the app at run-time:
#   tesseract-ocr + eng traineddata  -> image & scanned-PDF OCR
#   poppler-utils (pdftoppm)         -> rasterize PDFs for OCR
#   libmagic1                         -> file type detection
#   libgl1, libglib2.0-0             -> onnxruntime / chromadb default EF
#   libxml2, libxslt1.1              -> python-docx / lxml / pptx
#   curl                              -> healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        poppler-utils \
        libmagic1 \
        libgl1 \
        libglib2.0-0 \
        libxml2 \
        libxslt1.1 \
        libjpeg62-turbo \
        zlib1g \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for runtime
RUN groupadd --system --gid 1001 docchat \
 && useradd  --system --uid 1001 --gid docchat --create-home docchat

WORKDIR /app/backend

# Install pre-built wheels from builder
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels

# Copy application source
COPY . /app/backend

# Ensure writable dirs for uploads + chroma persistence (volume-mounted at runtime)
RUN mkdir -p /app/backend/uploads /app/backend/chroma_db \
 && chown -R docchat:docchat /app/backend

USER docchat

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8001/api/health || exit 1

# Single worker by default; tune via WEB_CONCURRENCY env var
ENV WEB_CONCURRENCY=2

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port 8001 --workers ${WEB_CONCURRENCY}"]
