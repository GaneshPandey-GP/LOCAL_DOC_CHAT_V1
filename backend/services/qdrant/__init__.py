"""Qdrant vector store package — replaces ChromaDB as the primary vector backend.

Submodules:
  client          — singleton AsyncQdrantClient + health check
  collections     — per-tenant collection lifecycle
  ingestion       — chunk upsert (dense + optional sparse SPLADE)
  hybrid_search   — RRF-fused dense + sparse retrieval
  retrieval       — high-level pipeline (rewrite → search → dedup → rerank)
"""
