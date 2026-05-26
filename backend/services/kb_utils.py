"""Knowledge-Base helper utilities shared between routers and the chat pipeline.

These functions are intentionally side-effect free so they can be safely called
from public widget / share-link paths without leaking authentication state.
"""
from __future__ import annotations

from typing import List, Optional

from core.db import documents


async def resolve_kb_document_ids(kb_ids: Optional[List[str]]) -> List[str]:
    """Return the list of ready document IDs that belong to the given KBs.

    - Empty / None input returns [].
    - Only documents with `status == "ready"` are returned so callers don't
      try to retrieve from chunks that are still ingesting.
    """
    if not kb_ids:
        return []
    cursor = documents.find(
        {"kb_id": {"$in": list(kb_ids)}, "status": "ready"},
        {"_id": 0, "id": 1},
    )
    return [d["id"] async for d in cursor]
