"""Enterprise AI Database Agent (Stream 6).

Architectural separation mandate:
  • This module is COMPLETELY SEPARATE from the RAG pipeline (services.rag).
  • No shared code paths. No context merging. Parallel system.
  • RAG  → MongoDB + ChromaDB (unstructured intelligence)
  • This → PostgreSQL (structured analytics)
"""
