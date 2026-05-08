"""Embeddings + ChromaDB vector store. Pluggable embedding provider."""
import asyncio
from typing import List, Optional

import chromadb
from chromadb.utils import embedding_functions

from core.config import (
    CHROMA_COLLECTION,
    CHROMA_DIR,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    OPENAI_API_KEY,
)

_chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))

# ---------------------------------------------------------------------------
# Embedding provider abstraction
# ---------------------------------------------------------------------------
_local_ef: Optional[embedding_functions.EmbeddingFunction] = None
_openai_client = None


def _get_local_ef() -> embedding_functions.EmbeddingFunction:
    """ChromaDB default embedding function (onnx MiniLM, 384d, no API key)."""
    global _local_ef
    if _local_ef is None:
        _local_ef = embedding_functions.DefaultEmbeddingFunction()
    return _local_ef


def _get_openai():
    from openai import AsyncOpenAI

    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY not set. Either add it or switch EMBEDDING_PROVIDER=local."
            )
        _openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


async def embed_texts(texts: List[str]) -> List[List[float]]:
    if EMBEDDING_PROVIDER == "openai":
        client = _get_openai()
        resp = await client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
        return [d.embedding for d in resp.data]
    # local (default)
    ef = _get_local_ef()
    # chromadb EF is synchronous; run in threadpool to avoid blocking the event loop
    return await asyncio.to_thread(ef, texts)


async def embed_query(query: str) -> List[float]:
    embs = await embed_texts([query])
    return embs[0]


# ---------------------------------------------------------------------------
# Chroma collection (lazy-init so provider change works without restart loops)
# ---------------------------------------------------------------------------
_collection = None


def _get_collection():
    global _collection
    if _collection is None:
        _collection = _chroma_client.get_or_create_collection(
            name=CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"}
        )
    return _collection


async def add_chunks(
    document_id: str,
    owner_id: str,
    filename: str,
    chunks: List[dict],
) -> int:
    """chunks = [{id, text, page, index}, ...]"""
    if not chunks:
        return 0
    texts = [c["text"] for c in chunks]
    embeddings = await embed_texts(texts)
    ids = [c["id"] for c in chunks]
    metadatas = [
        {
            "document_id": document_id,
            "owner_id": owner_id,
            "filename": filename,
            "page": c.get("page", 1),
            "chunk_index": c.get("index", 0),
        }
        for c in chunks
    ]
    col = _get_collection()
    col.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
    return len(chunks)


async def search_chunks(
    query: str,
    document_ids: List[str],
    top_k: int = 5,
) -> List[dict]:
    if not document_ids:
        return []
    query_emb = await embed_query(query)
    where = (
        {"document_id": {"$in": document_ids}}
        if len(document_ids) > 1
        else {"document_id": document_ids[0]}
    )
    col = _get_collection()
    results = col.query(
        query_embeddings=[query_emb],
        n_results=top_k,
        where=where,
    )
    hits = []
    if not results.get("ids") or not results["ids"][0]:
        return hits
    for i, _id in enumerate(results["ids"][0]):
        meta = results["metadatas"][0][i]
        hits.append(
            {
                "chunk_id": _id,
                "text": results["documents"][0][i],
                "distance": results["distances"][0][i] if results.get("distances") else None,
                "document_id": meta.get("document_id"),
                "filename": meta.get("filename"),
                "page": meta.get("page"),
                "chunk_index": meta.get("chunk_index"),
            }
        )
    return hits


def delete_document_chunks(document_id: str) -> None:
    try:
        col = _get_collection()
        col.delete(where={"document_id": document_id})
    except Exception:
        pass
