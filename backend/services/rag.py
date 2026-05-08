"""RAG orchestration: retrieve -> prompt -> answer (with confidence)."""
from typing import AsyncIterator, List

from .embeddings import search_chunks
from .llm import chat_stream, chat_complete


SYSTEM_PROMPT = """You are DocChat, a precise document-grounded assistant.

Rules:
- Answer ONLY using the provided context.
- Every factual sentence MUST include an inline citation like [1], [2] that maps to the context sources.
- If the context does not contain the answer, reply exactly: "I don't have enough information in the provided documents to answer that."
- Prefer concise, well-structured markdown. Use lists, tables, and bold where helpful.
- Never invent source names, page numbers, or facts not present in the context.
"""


def _build_context(hits: List[dict]) -> str:
    blocks = []
    for i, h in enumerate(hits, start=1):
        blocks.append(
            f"[{i}] Source: {h['filename']} (page {h['page']})\n{h['text']}"
        )
    return "\n\n---\n\n".join(blocks)


def _confidence_from_hits(hits: List[dict]) -> str:
    """Map best retrieval distance to HIGH/MEDIUM/LOW.
    Thresholds are provider-dependent because MiniLM (local) and OpenAI
    produce different cosine-distance distributions for semantically similar text.
    """
    from core.config import EMBEDDING_PROVIDER

    if not hits:
        return "LOW"
    best = min((h.get("distance") or 1.0) for h in hits)
    if EMBEDDING_PROVIDER == "local":
        # MiniLM: relevant hits typically land in 0.5–1.2
        if best < 0.7:
            return "HIGH"
        if best < 1.0:
            return "MEDIUM"
        return "LOW"
    # openai text-embedding-3-small: relevant hits land in 0.15–0.55
    if best < 0.35:
        return "HIGH"
    if best < 0.6:
        return "MEDIUM"
    return "LOW"


def _dedupe_hits(hits: List[dict]) -> List[dict]:
    """Drop duplicate citations from the same (document, page) pair.
    Chroma may return multiple chunks of the same page; keep only the
    closest-distance hit per page so citations stay precise and unique.
    """
    seen: set = set()
    out: List[dict] = []
    # hits arrive sorted by ascending distance from chroma; preserve order
    for h in hits:
        key = (h.get("document_id"), h.get("page"))
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


async def retrieve(query: str, document_ids: List[str], top_k: int = 5) -> List[dict]:
    # Pull a wider candidate set from the vector store so we can dedupe
    # (document, page) pairs without losing the requested top_k.
    raw = await search_chunks(query, document_ids, top_k=max(top_k * 2, 8))
    return _dedupe_hits(raw)[:top_k]


def build_messages(query: str, hits: List[dict], history: List[dict] | None = None) -> List[dict]:
    context = _build_context(hits) if hits else "(no relevant context retrieved)"
    msgs: List[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        msgs.extend(history[-6:])  # last 3 turns
    msgs.append(
        {
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {query}",
        }
    )
    return msgs


async def answer_stream(
    query: str, document_ids: List[str], history: List[dict] | None = None, top_k: int = 5
) -> tuple[AsyncIterator[str], List[dict], str]:
    if not query or not query.strip():
        raise ValueError("Query must not be empty")
    if len(query) > 2000:
        query = query[:2000]
    hits = await retrieve(query, document_ids, top_k=top_k)
    messages = build_messages(query, hits, history)
    confidence = _confidence_from_hits(hits)
    return chat_stream(messages), hits, confidence


async def answer(
    query: str, document_ids: List[str], history: List[dict] | None = None, top_k: int = 5
) -> tuple[str, List[dict], str]:
    if not query or not query.strip():
        raise ValueError("Query must not be empty")
    if len(query) > 2000:
        query = query[:2000]
    hits = await retrieve(query, document_ids, top_k=top_k)
    messages = build_messages(query, hits, history)
    confidence = _confidence_from_hits(hits)
    text = await chat_complete(messages)
    return text, hits, confidence


async def suggest_followups(query: str, answer_text: str, hits: List[dict]) -> List[str]:
    """Generate 3 short follow-up questions."""
    if not hits:
        return []
    doc_summary = ", ".join({h["filename"] for h in hits})
    prompt = (
        f"Given this question: \"{query}\"\nAnd this answer: \"{answer_text[:500]}\"\n"
        f"Suggest 3 short follow-up questions a user might ask next, based strictly on the documents ({doc_summary}).\n"
        "Respond as a JSON array of 3 strings, nothing else."
    )
    try:
        raw = await chat_complete(
            [
                {"role": "system", "content": "You output only valid JSON arrays."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        import json
        import re

        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []
        data = json.loads(match.group(0))
        return [str(x) for x in data][:3]
    except Exception:
        return []
