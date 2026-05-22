"""Chat: streaming SSE retrieval-augmented generation + non-streaming fallback."""
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.audit import log_analytics, log_event
from core.db import documents, messages, sessions, share_links
from core.deps import get_current_user, get_optional_user
from core.security import decode_guest_token
from services import rag

router = APIRouter(prefix="/v2", tags=["chat"])


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    session_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    share_token: Optional[str] = None
    guest_token: Optional[str] = None
    stream: bool = True


async def _resolve_scope(
    user: Optional[dict], body: ChatRequest
) -> tuple[List[str], Optional[str], Optional[dict]]:
    """Returns (document_ids, actor_id, guest_payload)."""
    # Guest path: strictly scoped to guest token's document_ids
    if body.guest_token:
        payload = decode_guest_token(body.guest_token)
        if not payload or payload.get("type") != "guest":
            raise HTTPException(status_code=401, detail="Invalid guest token")
        link = await share_links.find_one(
            {"token": payload["share_token"]}, {"_id": 0}
        )
        if not link or link.get("revoked"):
            raise HTTPException(status_code=401, detail="Share link revoked")
        # Expiry check
        if link.get("expires_at"):
            exp = datetime.fromisoformat(link["expires_at"])
            if exp < datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="Share link expired")
        scoped_ids = [d for d in payload["document_ids"] if d in link["document_ids"]]
        return scoped_ids, None, payload

    # Authenticated user path
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Editors get: own uploads OR docs assigned by an Owner.
    # Owners always get: everything.
    if user["role"] == "owner":
        access_clause: dict = {}
    else:
        access_clause = {
            "$or": [
                {"owner_id": user["id"]},
                {"assigned_to": user["id"]},
            ]
        }

    requested = body.document_ids or []
    if not requested:
        # Default to all user-accessible documents
        docs = await documents.find(access_clause, {"_id": 0, "id": 1}).to_list(500)
        return [d["id"] for d in docs], user["id"], None

    # Verify user has access to each requested document
    query: dict = {"id": {"$in": requested}}
    if access_clause:
        query.update(access_clause)
    allowed = await documents.find(query, {"_id": 0, "id": 1}).to_list(500)
    return [d["id"] for d in allowed], user["id"], None


async def _get_or_create_session(
    user_id: Optional[str],
    session_id: Optional[str],
    first_query: str,
    extra_fields: Optional[dict] = None,
) -> str:
    if session_id:
        existing = await sessions.find_one({"id": session_id}, {"_id": 0})
        if existing:
            return session_id
    new_id = session_id or str(uuid.uuid4())
    title = first_query[:60] + ("…" if len(first_query) > 60 else "")
    doc = {
        "id": new_id,
        "user_id": user_id,
        "title": title,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra_fields:
        doc.update(extra_fields)
    await sessions.insert_one(doc)
    return new_id


async def _save_message(session_id: str, role: str, content: str, **extra) -> str:
    msg_id = str(uuid.uuid4())
    doc = {
        "id": msg_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    await messages.insert_one(doc)
    await sessions.update_one(
        {"id": session_id},
        {
            "$set": {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "last_active_at": datetime.now(timezone.utc).isoformat(),
            },
            "$inc": {"message_count": 1},
        },
    )
    return msg_id


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    document_ids, actor_id, guest_payload = await _resolve_scope(user, body)
    is_guest = guest_payload is not None

    # Sessions: guest sessions are local to share token
    session_owner = actor_id if not is_guest else f"guest:{guest_payload['share_token']}"
    session_extra: dict = {
        # Persist exact retrieval scope so reopening the chat history restores
        # the same document selection instead of defaulting to "all".
        "scope_doc_ids": list(document_ids) if document_ids else None,
    }
    if is_guest:
        from services.visitor_meta import extract_visitor_meta

        meta = extract_visitor_meta(request)
        session_extra.update(
            {
                "is_guest": True,
                "share_token": guest_payload["share_token"],
                # Network
                "ip": meta.get("ip"),
                "ip_masked": meta.get("ip_masked"),
                "user_agent": meta.get("user_agent"),
                "accept_language": meta.get("accept_language"),
                "accept_encoding": meta.get("accept_encoding"),
                # Device
                "browser": meta.get("browser"),
                "browser_version": meta.get("browser_version"),
                "os": meta.get("os"),
                "os_version": meta.get("os_version"),
                "device_type": meta.get("device_type"),
                # Fingerprint
                "fingerprint": meta.get("fingerprint"),
                # Geo (filled async by enrich_session_geo)
                "geo_country": None,
                "geo_city": None,
            }
        )
    session_id = await _get_or_create_session(
        session_owner, body.session_id, body.query, extra_fields=session_extra
    )
    if is_guest and session_extra.get("ip"):
        # Fire-and-forget geo enrichment so chat latency isn't impacted.
        from services.visitor_meta import enrich_session_geo

        enrich_session_geo(session_id, session_extra["ip"])

    # Save user message
    await _save_message(session_id, "user", body.query, actor_id=actor_id or "guest")

    # Load short history
    history_docs = (
        await messages.find({"session_id": session_id}, {"_id": 0})
        .sort("created_at", 1)
        .to_list(20)
    )
    history = [{"role": m["role"], "content": m["content"]} for m in history_docs[:-1]]  # exclude the just-saved user msg

    await log_analytics(
        "chat.query",
        {
            "actor": actor_id or "guest",
            "session_id": session_id,
            "doc_count": len(document_ids),
            "is_guest": is_guest,
        },
    )

    if body.stream:
        async def event_gen():
            import time

            start = time.time()
            stream_iter, hits, confidence = await rag.answer_stream(
                body.query, document_ids, history=history
            )
            # Send metadata event first
            citations = [
                {
                    "index": i + 1,
                    "filename": h["filename"],
                    "page": h["page"],
                    "document_id": h["document_id"],
                    "chunk_id": h["chunk_id"],
                    "text": h["text"][:400],
                }
                for i, h in enumerate(hits)
            ]
            yield f"event: meta\ndata: {json.dumps({'session_id': session_id, 'citations': citations, 'confidence': confidence})}\n\n"

            full_text = []
            async for token in stream_iter:
                full_text.append(token)
                yield f"event: token\ndata: {json.dumps({'t': token})}\n\n"

            answer_text = "".join(full_text)
            msg_id = await _save_message(
                session_id,
                "assistant",
                answer_text,
                citations=citations,
                confidence=confidence,
                latency_ms=int((time.time() - start) * 1000),
            )
            try:
                followups = await rag.suggest_followups(body.query, answer_text, hits)
            except Exception:
                followups = []
            yield f"event: done\ndata: {json.dumps({'message_id': msg_id, 'followups': followups})}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    # Non-streaming
    import time

    start = time.time()
    text, hits, confidence = await rag.answer(body.query, document_ids, history=history)
    citations = [
        {
            "index": i + 1,
            "filename": h["filename"],
            "page": h["page"],
            "document_id": h["document_id"],
            "chunk_id": h["chunk_id"],
            "text": h["text"][:400],
        }
        for i, h in enumerate(hits)
    ]
    msg_id = await _save_message(
        session_id,
        "assistant",
        text,
        citations=citations,
        confidence=confidence,
        latency_ms=int((time.time() - start) * 1000),
    )
    try:
        followups = await rag.suggest_followups(body.query, text, hits)
    except Exception:
        followups = []
    return {
        "message_id": msg_id,
        "session_id": session_id,
        "answer": text,
        "citations": citations,
        "confidence": confidence,
        "followups": followups,
    }
