"""Token-aware text chunking using tiktoken."""
from typing import List

import tiktoken

_ENCODER = tiktoken.get_encoding("cl100k_base")

DEFAULT_CHUNK_TOKENS = 500
DEFAULT_OVERLAP = 75


def chunk_text(text: str, chunk_tokens: int = DEFAULT_CHUNK_TOKENS, overlap: int = DEFAULT_OVERLAP) -> List[str]:
    text = text.strip()
    if not text:
        return []
    tokens = _ENCODER.encode(text)
    if len(tokens) <= chunk_tokens:
        return [text]

    chunks: List[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_tokens, len(tokens))
        chunk = _ENCODER.decode(tokens[start:end])
        chunks.append(chunk.strip())
        if end == len(tokens):
            break
        start = end - overlap
    return [c for c in chunks if c]
