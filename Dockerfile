# ─── DocChat Backend Image ───────────────────────────────────────────────────
# Python 3.11 slim base with the system libs OCR + PDF + Playwright need.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies. Single RUN layer to keep image lean.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        poppler-utils \
        libglib2.0-0 \
        libsm6 \
        libxrender1 \
        libxext6 \
        curl \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps BEFORE copying code so the layer is cached
# unless requirements.txt itself changes.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Now copy the application source.
COPY backend/ /app/backend/

# Install Playwright Chromium browser (required for JS-rendered crawls).
# --with-deps installs the OS libs Chromium needs.
RUN pip install --no-cache-dir playwright && \
    playwright install --with-deps chromium || \
    echo "Playwright install failed — JS-rendered crawler will fall back to httpx."

WORKDIR /app/backend

EXPOSE 8001

# Liveness probe. Compose / orchestrators use this to know when the API is up.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8001/api/health || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
