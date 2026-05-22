"""DocChat — enterprise RAG backend."""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from core.db import init_indexes  # noqa: E402
from routers import admin, auth, chat, documents, feedback, flags, sessions, share, widgets, widget_public  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("docchat")

app = FastAPI(title="DocChat API", version="2.0.0")

api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"service": "docchat", "version": "2.0.0"}


@api_router.get("/health")
async def health():
    return {"status": "ok"}


# Public share-link info (no auth)
from routers.share import router as share_router  # noqa: E402

api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(sessions.router)
api_router.include_router(feedback.router)
api_router.include_router(share.router)
api_router.include_router(flags.router)
api_router.include_router(flags.admin_router)
api_router.include_router(admin.router)
api_router.include_router(widgets.router)
api_router.include_router(widget_public.router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    try:
        await init_indexes()
        logger.info("MongoDB indexes initialized")
    except Exception as e:
        logger.warning("init_indexes failed: %s", e)

    # Ensure Tesseract OCR binary is available (required for image/PDF OCR)
    import shutil, subprocess
    if not shutil.which("tesseract"):
        logger.warning("Tesseract not found — installing via apt-get…")
        try:
            subprocess.run(
                ["apt-get", "install", "-y", "-qq", "tesseract-ocr", "tesseract-ocr-eng"],
                check=True, capture_output=True, timeout=120,
            )
            logger.info("Tesseract installed successfully")
        except Exception as te:
            logger.error("Tesseract auto-install failed: %s — OCR features will be degraded", te)
    else:
        logger.info("Tesseract OK: %s", shutil.which("tesseract"))

    # Ensure poppler-utils (pdftoppm) is available for scanned PDF OCR
    if not shutil.which("pdftoppm"):
        logger.warning("pdftoppm not found — installing poppler-utils…")
        try:
            subprocess.run(
                ["apt-get", "install", "-y", "-qq", "poppler-utils"],
                check=True, capture_output=True, timeout=120,
            )
            logger.info("poppler-utils installed successfully")
        except Exception as pe:
            logger.error("poppler-utils auto-install failed: %s — scanned PDF OCR skipped", pe)
    else:
        logger.info("pdftoppm OK: %s", shutil.which("pdftoppm"))
