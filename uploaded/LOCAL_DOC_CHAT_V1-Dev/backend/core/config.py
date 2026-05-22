"""Application configuration and feature flags."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")


def _bool_env(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


# Core secrets
JWT_SECRET = os.environ.get("JWT_SECRET", "docchat-dev-secret-change-in-prod")
import warnings  # noqa: E402
if JWT_SECRET == "docchat-dev-secret-change-in-prod":
    warnings.warn(
        "JWT_SECRET is using the default insecure value. "
        "Set JWT_SECRET in .env before deploying.",
        stacklevel=2,
    )
JWT_ALGORITHM = "HS256"
JWT_ACCESS_EXPIRE_MINUTES = 60 * 24  # 24h
JWT_REFRESH_EXPIRE_DAYS = 30
SHARE_TOKEN_SECRET = os.environ.get("SHARE_TOKEN_SECRET", JWT_SECRET + "-share")

# ---------------------------------------------------------------------------
# Provider configuration — runtime-switchable via env vars.
#
# LLM_PROVIDER        = "emergent" | "openrouter"   (default: emergent)
# EMBEDDING_PROVIDER  = "local"    | "openai"       (default: local)
#
#   emergent:    uses EMERGENT_LLM_KEY against the Emergent proxy.
#                Chat works; embeddings NOT supported on the proxy.
#   openrouter:  uses OPENROUTER_API_KEY against openrouter.ai.
#   local:       uses ChromaDB's DefaultEmbeddingFunction (onnx MiniLM, 384d).
#                No API key required.
#   openai:      uses OPENAI_API_KEY against OpenAI directly (1536d).
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "emergent").lower()
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "local").lower()

# Keys
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
EMERGENT_BASE_URL = os.environ.get(
    "EMERGENT_BASE_URL", "https://integrations.emergentagent.com/llm"
)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Models (each provider has sensible defaults; override via env)
LLM_MODEL = os.environ.get(
    "LLM_MODEL",
    "gpt-4o-mini" if LLM_PROVIDER == "emergent" else "openai/gpt-4o-mini",
)
EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL",
    "all-MiniLM-L6-v2" if EMBEDDING_PROVIDER == "local" else "text-embedding-3-small",
)

# Storage
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/app/backend/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR = Path(os.environ.get("CHROMA_DIR", "/app/backend/chroma_db"))
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# Collection name varies by embedding provider to avoid dim mismatch
CHROMA_COLLECTION = f"docchat_{EMBEDDING_PROVIDER}"

# Feature flags
FEATURE_FLAGS = {
    "ENABLE_HYBRID_SEARCH": _bool_env("ENABLE_HYBRID_SEARCH", True),
    "ENABLE_RERANKING": _bool_env("ENABLE_RERANKING", False),
    "ENABLE_QUERY_REWRITING": _bool_env("ENABLE_QUERY_REWRITING", False),
    "ENABLE_MULTI_QUERY_EXPANSION": _bool_env("ENABLE_MULTI_QUERY_EXPANSION", False),
    "ENABLE_STREAMING": _bool_env("ENABLE_STREAMING", True),
    "ENABLE_CONFIDENCE_SCORING": _bool_env("ENABLE_CONFIDENCE_SCORING", True),
    "ENABLE_HALLUCINATION_DETECTION": _bool_env("ENABLE_HALLUCINATION_DETECTION", False),
    "ENABLE_OCR": _bool_env("ENABLE_OCR", False),
    "ENABLE_TABLE_EXTRACTION": _bool_env("ENABLE_TABLE_EXTRACTION", True),
    "ENABLE_ENTITY_EXTRACTION": _bool_env("ENABLE_ENTITY_EXTRACTION", False),
    "ENABLE_PII_MASKING": _bool_env("ENABLE_PII_MASKING", False),
    "ENABLE_RBAC": _bool_env("ENABLE_RBAC", True),
    "ENABLE_SHARE_LINKS": _bool_env("ENABLE_SHARE_LINKS", True),
    "ENABLE_EMBEDDING_CACHE": _bool_env("ENABLE_EMBEDDING_CACHE", False),
    "ENABLE_QUERY_CACHE": _bool_env("ENABLE_QUERY_CACHE", False),
    "ENABLE_BACKGROUND_INGESTION": _bool_env("ENABLE_BACKGROUND_INGESTION", True),
    "ENABLE_ANALYTICS_DASHBOARD": _bool_env("ENABLE_ANALYTICS_DASHBOARD", True),
    "ENABLE_AUDIT_LOG": _bool_env("ENABLE_AUDIT_LOG", True),
    # --- Extended document format support (Feb 2026) ---
    "ENABLE_PPTX_SUPPORT": _bool_env("ENABLE_PPTX_SUPPORT", True),
    "ENABLE_EXCEL_SUPPORT": _bool_env("ENABLE_EXCEL_SUPPORT", True),
    "ENABLE_IMAGE_OCR": _bool_env("ENABLE_IMAGE_OCR", True),
    "ENABLE_SCANNED_PDF_OCR": _bool_env("ENABLE_SCANNED_PDF_OCR", True),
    "ENABLE_GOOGLE_SLIDES": _bool_env("ENABLE_GOOGLE_SLIDES", False),
    # --- Advanced multi-modal extraction (May 2026) ---
    "ENABLE_ADVANCED_OCR": _bool_env("ENABLE_ADVANCED_OCR", True),
    "ENABLE_IMAGE_IN_PDF_OCR": _bool_env("ENABLE_IMAGE_IN_PDF_OCR", True),
    "ENABLE_PPTX_IMAGE_OCR": _bool_env("ENABLE_PPTX_IMAGE_OCR", True),
    "ENABLE_VISION_LLM_FOR_PDF_IMAGES": _bool_env("ENABLE_VISION_LLM_FOR_PDF_IMAGES", False),
    # --- Embeddable chat widget (Apr 2026) ---
    "ENABLE_EMBED_WIDGET": _bool_env("ENABLE_EMBED_WIDGET", True),
}


def is_enabled(flag: str) -> bool:
    return FEATURE_FLAGS.get(flag, False)
