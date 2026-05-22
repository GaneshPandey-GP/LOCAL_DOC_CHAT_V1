"""Document upload, list, delete, permissions, status."""
import hashlib
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.audit import log_event
from core.config import UPLOAD_DIR
from core.db import documents, share_links, users as users_coll
from core.deps import ROLE_EDITOR, ROLE_OWNER, get_current_user, require_role
from services.embeddings import delete_document_chunks
from services.extraction import (
    ALL_KNOWN_EXTENSIONS,
    current_supported_extensions,
    file_type_label,
)
from services.ingestion import ingest_document

router = APIRouter(prefix="/v2/documents", tags=["documents"])

# ── Upload validation constants ───────────────────────────────────────────────
MAX_FILE_SIZE_MB = 50
ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md",
    ".pptx", ".xlsx", ".csv",
    ".png", ".jpg", ".jpeg",
}


class DocumentOut(BaseModel):
    id: str
    filename: str
    size: int
    mime_type: Optional[str] = None
    file_type: Optional[str] = None
    owner_id: str
    owner_name: Optional[str] = None
    status: str
    progress: int
    chunk_count: int = 0
    page_count: int = 0
    tags: List[str] = []
    assigned_to: List[str] = []
    created_at: str
    indexed_at: Optional[str] = None
    error: Optional[str] = None


@router.post("/ingest")
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tags: str = Form(""),
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    ext = Path(file.filename or "").suffix.lower()

    # ── Hard validation: size + allowed extensions ────────────────────────────
    if file.size and file.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_FILE_SIZE_MB} MB limit.",
        )
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"File type '{ext}' is not supported.",
        )

    enabled_exts = current_supported_extensions()

    if ext in ALL_KNOWN_EXTENSIONS and ext not in enabled_exts:
        # Known format but its feature flag is OFF — reject with a clear reason.
        flag_map = {
            ".pptx": "ENABLE_PPTX_SUPPORT",
            ".xlsx": "ENABLE_EXCEL_SUPPORT",
            ".csv": "ENABLE_EXCEL_SUPPORT",
            ".png": "ENABLE_IMAGE_OCR",
            ".jpg": "ENABLE_IMAGE_OCR",
            ".jpeg": "ENABLE_IMAGE_OCR",
        }
        flag = flag_map.get(ext, "the corresponding feature flag")
        raise HTTPException(
            status_code=400,
            detail=f"{ext} uploads are disabled. Enable {flag} in backend/.env to ingest this format.",
        )
    if ext not in enabled_exts:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    # ── Read file content & compute SHA-256 hash for duplicate detection ──
    raw_content = await file.read()
    if len(raw_content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_FILE_SIZE_MB} MB limit.",
        )
    content_hash = hashlib.sha256(raw_content).hexdigest()

    # ── Duplicate check: global (same hash, any owner) ──
    # Per spec: prevent the same document from being uploaded twice regardless
    # of who uploads it. This avoids duplicate embeddings/index entries.
    existing = await documents.find_one(
        {"content_hash": content_hash},
        {"_id": 0, "id": 1, "filename": 1, "status": 1, "created_at": 1, "owner_id": 1},
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DUPLICATE",
                "message": "Document already exists",
                "existing_id": existing["id"],
                "existing_filename": existing["filename"],
                "existing_status": existing["status"],
            },
        )

    # ── Save to disk ──
    doc_id = str(uuid.uuid4())
    disk_path = UPLOAD_DIR / f"{doc_id}{ext}"
    disk_path.write_bytes(raw_content)
    size = len(raw_content)

    parsed_tags = [t.strip() for t in tags.split(",") if t.strip()]

    doc = {
        "id": doc_id,
        "filename": file.filename,
        "disk_path": str(disk_path),
        "size": size,
        "mime_type": file.content_type,
        "file_type": file_type_label(file.filename or ""),
        "owner_id": user["id"],
        "owner_name": user.get("name"),
        "status": "queued",
        "progress": 5,
        "chunk_count": 0,
        "page_count": 0,
        "tags": parsed_tags,
        "assigned_to": [],
        "content_hash": content_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "indexed_at": None,
        "error": None,
    }
    await documents.insert_one(doc)

    async def _run():
        try:
            await ingest_document(doc_id, disk_path, file.filename, user["id"])
        except Exception:
            pass

    background_tasks.add_task(_run)

    await log_event(
        "document.upload",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="document",
        resource_id=doc_id,
        ip=request.client.host if request.client else None,
        metadata={"filename": file.filename, "size": size},
    )

    return {"id": doc_id, "job_id": doc_id, "status": "queued"}


@router.get("", response_model=List[DocumentOut])
async def list_documents(
    q: Optional[str] = None,
    tag: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    query: dict = {}
    # Owners see all documents. Editors see ONLY their own uploads + docs
    # explicitly assigned to them by an Owner.
    if user["role"] != "owner":
        query["$or"] = [
            {"owner_id": user["id"]},
            {"assigned_to": user["id"]},
        ]
    if q:
        query["filename"] = {"$regex": q, "$options": "i"}
    if tag:
        query["tags"] = tag

    cursor = documents.find(query, {"_id": 0, "disk_path": 0}).sort("created_at", -1)
    return await cursor.to_list(500)


def _user_can_access_doc(user: dict, doc: dict) -> bool:
    if user["role"] == "owner":
        return True
    if doc.get("owner_id") == user["id"]:
        return True
    if user["id"] in (doc.get("assigned_to") or []):
        return True
    return False


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await documents.find_one({"id": doc_id}, {"_id": 0, "disk_path": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not _user_can_access_doc(user, doc):
        raise HTTPException(status_code=403, detail="Forbidden")
    return doc


@router.get("/{doc_id}/processing-status")
async def processing_status(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await documents.find_one(
        {"id": doc_id},
        {"_id": 0, "status": 1, "progress": 1, "chunk_count": 1, "error": 1, "owner_id": 1, "assigned_to": 1},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not _user_can_access_doc(user, doc):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "status": doc.get("status"),
        "progress": doc.get("progress", 0),
        "chunk_count": doc.get("chunk_count", 0),
        "error": doc.get("error"),
    }


@router.get("/{doc_id}/file")
async def serve_document_file(doc_id: str, user: dict = Depends(get_current_user)):
    """Serve the original uploaded file for in-app preview/download.
    Access mirrors list visibility: owner OR uploader OR assigned editor.
    """
    doc = await documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not _user_can_access_doc(user, doc):
        raise HTTPException(status_code=403, detail="Forbidden")
    disk_path = Path(doc["disk_path"])
    if not disk_path.exists():
        raise HTTPException(status_code=404, detail="File no longer on disk")
    return FileResponse(
        path=disk_path,
        media_type=doc.get("mime_type") or "application/octet-stream",
        filename=doc.get("filename") or disk_path.name,
    )


class PermissionsBody(BaseModel):
    tags: Optional[List[str]] = None


class AssignmentBody(BaseModel):
    editor_ids: List[str]


@router.patch("/{doc_id}/assignments")
async def update_assignments(
    doc_id: str,
    body: AssignmentBody,
    request: Request,
    actor: dict = Depends(require_role(ROLE_OWNER)),
):
    """Owner-only: assign or unassign editors to a document.
    Pass the FULL list of editor user ids that should have access; this
    replaces any prior assignment.
    """
    doc = await documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Validate editor_ids reference existing editor accounts
    valid_ids: List[str] = []
    if body.editor_ids:
        cursor = users_coll.find(
            {"id": {"$in": body.editor_ids}, "role": {"$in": [ROLE_EDITOR, ROLE_OWNER]}},
            {"_id": 0, "id": 1},
        )
        valid_ids = [u["id"] async for u in cursor]

    await documents.update_one(
        {"id": doc_id},
        {"$set": {"assigned_to": valid_ids}},
    )
    await log_event(
        "document.assignments_updated",
        actor_id=actor["id"],
        actor_role=actor["role"],
        resource_type="document",
        resource_id=doc_id,
        ip=request.client.host if request.client else None,
        metadata={"assigned_to": valid_ids},
    )
    return {"ok": True, "assigned_to": valid_ids}


@router.patch("/{doc_id}/permissions")
async def update_permissions(
    doc_id: str,
    body: PermissionsBody,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    doc = await documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if user["role"] != "owner" and doc["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    update: dict = {}
    if body.tags is not None:
        update["tags"] = body.tags
    if update:
        await documents.update_one({"id": doc_id}, {"$set": update})
    await log_event(
        "document.permissions_updated",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="document",
        resource_id=doc_id,
        ip=request.client.host if request.client else None,
        metadata=update,
    )
    return {"ok": True}


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    doc = await documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if user["role"] != "owner" and doc["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Secure deletion: file, chunks, references in share links
    try:
        Path(doc["disk_path"]).unlink(missing_ok=True)
    except Exception:
        pass
    delete_document_chunks(doc_id)
    await documents.delete_one({"id": doc_id})
    # Remove this doc from any share links that reference it
    await share_links.update_many(
        {"document_ids": doc_id},
        {"$pull": {"document_ids": doc_id}},
    )

    await log_event(
        "document.delete",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="document",
        resource_id=doc_id,
        ip=request.client.host if request.client else None,
        metadata={"filename": doc["filename"]},
    )
    return {"ok": True}


@router.post("/{doc_id}/reprocess")
async def reprocess_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    """Re-trigger ingestion for a failed or stalled document."""
    doc = await documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if user["role"] != "owner" and doc["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    disk_path = Path(doc["disk_path"])
    if not disk_path.exists():
        raise HTTPException(status_code=400, detail="Original file no longer on disk. Please re-upload.")

    # Reset status
    await documents.update_one(
        {"id": doc_id},
        {"$set": {"status": "queued", "progress": 5, "error": None, "chunk_count": 0}},
    )
    # Remove existing chunks from vector store
    delete_document_chunks(doc_id)

    async def _run():
        try:
            await ingest_document(doc_id, disk_path, doc["filename"], doc["owner_id"])
        except Exception:
            pass

    background_tasks.add_task(_run)

    await log_event(
        "document.reprocess",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="document",
        resource_id=doc_id,
        ip=request.client.host if request.client else None,
        metadata={"filename": doc["filename"]},
    )
    return {"id": doc_id, "status": "queued"}


# ---------------------------------------------------------------------------
# Google Slides (stub) — API-ready scaffold behind ENABLE_GOOGLE_SLIDES
# ---------------------------------------------------------------------------
class GoogleSlidesBody(BaseModel):
    presentation_id: str
    title: Optional[str] = None


@router.post("/ingest-google-slides")
async def ingest_google_slides(
    body: GoogleSlidesBody,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    """Stub: reserves the endpoint + record shape. Full implementation needs
    Google API credentials and the presentations.get() traversal in
    services.extraction.extract_google_slides."""
    from core.config import is_enabled

    if not is_enabled("ENABLE_GOOGLE_SLIDES"):
        raise HTTPException(
            status_code=400,
            detail="Google Slides ingestion is disabled. Enable ENABLE_GOOGLE_SLIDES in backend/.env and configure Google API credentials.",
        )
    raise HTTPException(
        status_code=501,
        detail="Google Slides ingestion flag is ON but the integration is not yet implemented. Add credentials and wire services.extraction.extract_google_slides to complete.",
    )
