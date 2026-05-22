"""Background document ingestion pipeline."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from core.db import documents
from services.chunking import chunk_text
from services.embeddings import add_chunks
from services.extraction import extract_text


async def ingest_document(document_id: str, file_path: Path, filename: str, owner_id: str) -> None:
    """Extract -> chunk -> embed -> index. Updates document status in MongoDB.

    Extraction runs in a threadpool because OCR (tesseract, pdf2image),
    openpyxl, and python-pptx are all blocking CPU work and would otherwise
    stall the asyncio event loop.
    """
    try:
        await documents.update_one(
            {"id": document_id},
            {"$set": {"status": "extracting", "progress": 10}},
        )
        pages = await asyncio.to_thread(extract_text, file_path, filename)
        if not pages:
            raise ValueError("No extractable text found")

        await documents.update_one(
            {"id": document_id},
            {"$set": {"status": "chunking", "progress": 35}},
        )
        chunks_payload = []
        chunk_counter = 0
        for page_num, page_text in pages:
            for ct in chunk_text(page_text):
                chunks_payload.append(
                    {
                        "id": f"{document_id}:{chunk_counter}",
                        "text": ct,
                        "page": page_num,
                        "index": chunk_counter,
                    }
                )
                chunk_counter += 1

        if not chunks_payload:
            raise ValueError("No chunks produced")

        await documents.update_one(
            {"id": document_id},
            {"$set": {"status": "embedding", "progress": 60}},
        )
        count = await add_chunks(document_id, owner_id, filename, chunks_payload)

        await documents.update_one(
            {"id": document_id},
            {
                "$set": {
                    "status": "ready",
                    "progress": 100,
                    "chunk_count": count,
                    "page_count": len(pages),
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
    except Exception as e:
        await documents.update_one(
            {"id": document_id},
            {"$set": {"status": "failed", "progress": 0, "error": str(e)}},
        )
        raise
