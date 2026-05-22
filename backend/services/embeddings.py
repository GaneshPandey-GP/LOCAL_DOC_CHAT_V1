"""Embeddings + ChromaDB vector store — reads active embedding config from DB.

Priority:
  1. Active model_config document in MongoDB  (set from Settings UI)
  2. Environment variables / core.config      (legacy fallback)
"""
import asyncio
import logging
from typing import List, Optional

import chromadb
from chromadb.utils import embedding_functions

from core.config import CHROMA_DIR

logger = logging.getLogger("docchat.embeddings")

_chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))

# ---------------------------------------------------------------------------
# Cached embedding provider instances
# ---------------------------------------------------------------------------
_local_ef: Optional[embedding_functions.EmbeddingFunction] = None
_openai_client = None
_openai_client_key: Optional[str] = None   # tracks key the client was built with

_collection = None
_collection_name: Optional[str] = None    # tracks which collection is open


async def _get_active_config() -> dict:
    """Return the active embedding model_config from DB, or fall back to env config."""
    try:
        from core.db import model_configs
        doc = await model_configs.find_one(
            {"model_type": "embedding", "is_active": True},
            {"_id": 0},
        )
        if doc:
            return doc
    except Exception as e:
        logger.warning("Could not read active embedding config from DB: %s", e)

    # Fallback to env
    from core import config as cfg
    return {
        "provider": cfg.EMBEDDING_PROVIDER,
        "model_id": cfg.EMBEDDING_MODEL,
        "api_key": cfg.OPENAI_API_KEY if cfg.EMBEDDING_PROVIDER == "openai" else "",
    }


def _get_local_ef() -> embedding_functions.EmbeddingFunction:
    global _local_ef
    if _local_ef is None:
        _local_ef = embedding_functions.DefaultEmbeddingFunction()
    return _local_ef


def _get_openai_client(api_key: str):
    from openai import AsyncOpenAI
    global _openai_client, _openai_client_key
    if _openai_client is None or _openai_client_key != api_key:
        if not api_key:
            raise RuntimeError(
                "No API key found for OpenAI embeddings. "
                "Add one via Settings → Models or set OPENAI_API_KEY."
            )
        _openai_client = AsyncOpenAI(api_key=api_key)
        _openai_client_key = api_key
    return _openai_client


def _get_collection(collection_name: str):
    """Get or create a ChromaDB collection, rebuilding if the name changed."""
    global _collection, _collection_name
    if _collection is None or _collection_name != collection_name:
        logger.info("Opening Chroma collection: %s", collection_name)
        _collection = _chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        _collection_name = collection_name
    return _collection


async def embed_texts(texts: List[str]) -> List[List[float]]:
    config = await _get_active_config()
    provider = (config.get("provider") or "local").lower()
    model_id = config.get("model_id") or "all-MiniLM-L6-v2"
    api_key = config.get("api_key") or ""

    # Also check env as fallback for key
    if not api_key and provider == "openai":
        from core import config as cfg
        api_key = cfg.OPENAI_API_KEY

    if provider == "openai":
        client = _get_openai_client(api_key)
        resp = await client.embeddings.create(model=model_id, input=texts)
        return [d.embedding for d in resp.data]

    # local (default) — provider == "local" or unknown
    ef = _get_local_ef()
    return await asyncio.to_thread(ef, texts)


async def embed_query(query: str) -> List[float]:
    embs = await embed_texts([query])
    return embs[0]


async def _active_collection_name() -> str:
    """Derive Chroma collection name from the active embedding provider."""
    config = await _get_active_config()
    provider = (config.get("provider") or "local").lower()
    return f"docchat_{provider}"


async def add_chunks(
    document_id: str,
    owner_id: str,
    filename: str,
    chunks: List[dict],
) -> int:
    """Embed and store document chunks in ChromaDB."""
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
    col_name = await _active_collection_name()
    col = _get_collection(col_name)
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
    col_name = await _active_collection_name()
    col = _get_collection(col_name)
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
        # Try both known collection names since provider may have changed
        for name in [_collection_name, "docchat_local", "docchat_openai"]:
            if not name:
                continue
            try:
                col = _chroma_client.get_collection(name)
                col.delete(where={"document_id": document_id})
            except Exception:
                pass
    except Exception:
        pass
