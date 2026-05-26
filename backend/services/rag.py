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


def build_messages(query: str, hits: List[dict], history: List[dict] | None = None, system_prompt: str | None = None) -> List[dict]:
    context = _build_context(hits) if hits else "(no relevant context retrieved)"
    sys_text = (system_prompt or SYSTEM_PROMPT).strip() or SYSTEM_PROMPT
    msgs: List[dict] = [{"role": "system", "content": sys_text}]
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
    query: str, document_ids: List[str], history: List[dict] | None = None, top_k: int = 5,
    system_prompt: str | None = None,
) -> tuple[AsyncIterator[str], List[dict], str]:
    if not query or not query.strip():
        raise ValueError("Query must not be empty")
    if len(query) > 2000:
        query = query[:2000]
    hits = await retrieve(query, document_ids, top_k=top_k)
    messages = build_messages(query, hits, history, system_prompt=system_prompt)
    confidence = _confidence_from_hits(hits)
    return chat_stream(messages), hits, confidence


async def answer(
    query: str, document_ids: List[str], history: List[dict] | None = None, top_k: int = 5,
    system_prompt: str | None = None,
) -> tuple[str, List[dict], str]:
    if not query or not query.strip():
        raise ValueError("Query must not be empty")
    if len(query) > 2000:
        query = query[:2000]
    hits = await retrieve(query, document_ids, top_k=top_k)
    messages = build_messages(query, hits, history, system_prompt=system_prompt)
    confidence = _confidence_from_hits(hits)
    text = await chat_complete(messages)
    return text, hits, confidence


# ── MCP-aware variants ──────────────────────────────────────────────────────
import json as _json
import re as _re
import time as _time


_TOOL_CALL_RE = _re.compile(r"TOOL_CALL:\s*([A-Za-z0-9_\-\. ]+?)\s*\((\{.*?\})\)", _re.DOTALL)


def _format_tools_section(tools: List[dict]) -> str:
    if not tools:
        return ""
    lines = ["", "You have access to the following tools. Invoke a tool ONLY when you cannot answer from the provided context alone.",
             "Call a tool by emitting a line of the exact form:",
             '  TOOL_CALL: <tool_name_or_id>({"key": "value"})',
             "After tools execute, their results are appended to the conversation as TOOL_RESULT lines and you must produce the final answer.",
             "", "Available tools:"]
    for t in tools:
        schema = _json.dumps(t.get("input_schema") or {}, separators=(",", ":"))
        lines.append(f"- name='{t.get('name')}' id={t.get('id')} — {t.get('description','')[:200]}  | input_schema={schema}")
    return "\n".join(lines)


async def _resolve_tools(mcp_tool_ids: List[str]) -> List[dict]:
    from mcp.registry import get_tool
    out: List[dict] = []
    for tid in mcp_tool_ids or []:
        t = await get_tool(tid)
        if t and t.get("enabled") is not False:
            out.append(t)
    return out


async def _run_tool_calls(text: str, tools_by_name: dict) -> tuple[List[dict], str]:
    """Parse TOOL_CALL: lines, execute each, return (tool_calls_made, formatted_results_block).

    `tools_by_name` is indexed by BOTH tool name and tool id so the LLM can
    use either in its TOOL_CALL invocation.
    """
    from mcp.executor import execute_mcp_tool
    matches = list(_TOOL_CALL_RE.finditer(text or ""))
    if not matches:
        return [], ""
    results: List[dict] = []
    blocks: List[str] = []
    for m in matches:
        name = m.group(1).strip()
        raw_args = m.group(2).strip()
        tool = tools_by_name.get(name) or tools_by_name.get(name.lower())
        t0 = _time.perf_counter()
        if not tool:
            blocks.append(f"TOOL_RESULT: {name} → error: unknown tool")
            results.append({"tool_id": None, "tool_name": name, "input": raw_args,
                            "result": {"error": "unknown tool"}, "elapsed_ms": 0})
            continue
        try:
            tool_input = _json.loads(raw_args)
        except Exception as e:
            blocks.append(f"TOOL_RESULT: {name} → error: invalid JSON args ({e})")
            results.append({"tool_id": tool["id"], "tool_name": name, "input": raw_args,
                            "result": {"error": f"invalid JSON args: {e}"}, "elapsed_ms": 0})
            continue
        try:
            res = await execute_mcp_tool(tool["id"], tool_input, run_id="chat", node_id="chat")
            elapsed = int((_time.perf_counter() - t0) * 1000)
            preview = _json.dumps(res, default=str)
            if len(preview) > 1500:
                preview = preview[:1500] + "…"
            blocks.append(f"TOOL_RESULT: {tool.get('name')} → {preview}")
            results.append({"tool_id": tool["id"], "tool_name": tool.get("name"), "input": tool_input,
                            "result": res, "elapsed_ms": elapsed})
        except Exception as e:
            elapsed = int((_time.perf_counter() - t0) * 1000)
            blocks.append(f"TOOL_RESULT: {tool.get('name')} → error: {e}")
            results.append({"tool_id": tool["id"], "tool_name": tool.get("name"), "input": tool_input,
                            "result": {"error": str(e)[:300]}, "elapsed_ms": elapsed})
    return results, "\n".join(blocks)


def _build_tool_aware_messages(query: str, hits: List[dict], history: List[dict] | None,
                                system_prompt: str | None, tools: List[dict]) -> List[dict]:
    sys_text = (system_prompt or SYSTEM_PROMPT).strip() or SYSTEM_PROMPT
    if tools:
        sys_text = sys_text + "\n" + _format_tools_section(tools)
    msgs: List[dict] = [{"role": "system", "content": sys_text}]
    if history:
        msgs.extend(history[-6:])
    context = _build_context(hits) if hits else "(no relevant context retrieved)"
    msgs.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"})
    return msgs


async def answer_with_tools(
    query: str,
    document_ids: List[str],
    mcp_tool_ids: List[str] | None = None,
    history: List[dict] | None = None,
    system_prompt: str | None = None,
    top_k: int = 5,
) -> tuple[str, List[dict], str, List[dict]]:
    """Non-streaming RAG with optional MCP tool-call loop.

    Falls back to plain `answer()` when mcp_tool_ids is empty/None so existing
    callers see zero behaviour change.
    """
    if not mcp_tool_ids:
        text, hits, conf = await answer(query, document_ids, history=history, top_k=top_k, system_prompt=system_prompt)
        return text, hits, conf, []

    if not query or not query.strip():
        raise ValueError("Query must not be empty")
    if len(query) > 2000:
        query = query[:2000]

    tools = await _resolve_tools(mcp_tool_ids)
    # Index by both name and id so LLMs can use either form.
    tools_by_name: dict = {}
    for t in tools:
        tools_by_name[t["name"]] = t
        tools_by_name[t["name"].lower()] = t
        tools_by_name[t["id"]] = t

    hits = await retrieve(query, document_ids, top_k=top_k)
    confidence = _confidence_from_hits(hits)
    messages = _build_tool_aware_messages(query, hits, history, system_prompt, tools)

    first_pass = await chat_complete(messages)
    tool_calls_made, results_block = await _run_tool_calls(first_pass, tools_by_name)
    if not tool_calls_made:
        return first_pass, hits, confidence, []

    # Second pass with tool results appended
    messages.append({"role": "assistant", "content": first_pass})
    messages.append({"role": "user", "content": "Tool results below — produce the final answer for the user.\n" + results_block})
    final = await chat_complete(messages)
    return final, hits, confidence, tool_calls_made


async def answer_stream_with_tools(
    query: str,
    document_ids: List[str],
    mcp_tool_ids: List[str] | None = None,
    history: List[dict] | None = None,
    system_prompt: str | None = None,
    top_k: int = 5,
) -> tuple[AsyncIterator[str], List[dict], str, List[dict]]:
    """Streaming variant — tool calls run before the streamed answer begins."""
    if not mcp_tool_ids:
        stream, hits, conf = await answer_stream(query, document_ids, history=history, top_k=top_k, system_prompt=system_prompt)
        return stream, hits, conf, []

    if not query or not query.strip():
        raise ValueError("Query must not be empty")
    if len(query) > 2000:
        query = query[:2000]

    tools = await _resolve_tools(mcp_tool_ids)
    tools_by_name: dict = {}
    for t in tools:
        tools_by_name[t["name"]] = t
        tools_by_name[t["name"].lower()] = t
        tools_by_name[t["id"]] = t

    hits = await retrieve(query, document_ids, top_k=top_k)
    confidence = _confidence_from_hits(hits)
    messages = _build_tool_aware_messages(query, hits, history, system_prompt, tools)

    first_pass = await chat_complete(messages)
    tool_calls_made, results_block = await _run_tool_calls(first_pass, tools_by_name)
    if not tool_calls_made:
        # No tool calls — stream the first pass as the final answer
        async def _replay():
            yield first_pass
        return _replay(), hits, confidence, []

    messages.append({"role": "assistant", "content": first_pass})
    messages.append({"role": "user", "content": "Tool results below — produce the final answer for the user.\n" + results_block})
    return chat_stream(messages), hits, confidence, tool_calls_made


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
