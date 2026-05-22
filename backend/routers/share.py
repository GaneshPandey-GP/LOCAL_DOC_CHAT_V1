"""Secure share links with strict document-scope isolation."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.audit import log_analytics, log_event
from core.db import documents, messages, share_links, sessions as sessions_coll
from core.deps import ROLE_EDITOR, ROLE_OWNER, require_role
from core.security import (
    create_guest_token,
    decode_guest_token,
    generate_share_token,
    hash_share_password,
    verify_share_password,
)

router = APIRouter(prefix="/v2/share-links", tags=["share-links"])


class CreateShareLinkBody(BaseModel):
    document_ids: List[str] = Field(min_length=1)
    mode: Literal["public", "password", "expiring"] = "public"
    password: Optional[str] = None
    expires_in_hours: Optional[int] = None
    single_use: bool = False
    domain_restriction: Optional[str] = None  # e.g. "@company.com"
    title: Optional[str] = None


class ShareLinkOut(BaseModel):
    token: str
    mode: str
    document_ids: List[str]
    document_filenames: List[str] = []
    title: Optional[str]
    single_use: bool
    opens: int
    revoked: bool
    expires_at: Optional[str]
    created_at: str
    domain_restriction: Optional[str]
    creator_id: Optional[str] = None
    creator_role: Optional[str] = None
    creator_name: Optional[str] = None
    creator_email: Optional[str] = None


class VerifyBody(BaseModel):
    password: Optional[str] = None
    email: Optional[str] = None


@router.post("", response_model=ShareLinkOut)
async def create_share_link(
    body: CreateShareLinkBody,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    # Verify user has access to every requested document.
    # Owners can share any doc; editors can share docs they uploaded
    # OR docs explicitly assigned to them by an Owner.
    doc_query: dict = {"id": {"$in": body.document_ids}}
    if user["role"] != "owner":
        doc_query["$or"] = [
            {"owner_id": user["id"]},
            {"assigned_to": user["id"]},
        ]
    found = await documents.find(doc_query, {"_id": 0, "id": 1}).to_list(500)
    found_ids = {d["id"] for d in found}
    missing = set(body.document_ids) - found_ids
    if missing:
        raise HTTPException(status_code=403, detail=f"No access to documents: {list(missing)}")

    token = generate_share_token()
    expires_at = None
    if body.mode == "expiring":
        hours = body.expires_in_hours or 24
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()

    password_hash = None
    if body.mode == "password":
        if not body.password:
            raise HTTPException(status_code=400, detail="Password required for password mode")
        password_hash = hash_share_password(body.password)

    link = {
        "token": token,
        "mode": body.mode,
        "document_ids": body.document_ids,
        "owner_id": user["id"],
        # Creator metadata — owner-visibility & filtering
        "creator_id": user["id"],
        "creator_role": user["role"],
        "creator_name": user.get("name"),
        "creator_email": user.get("email"),
        "title": body.title,
        "password_hash": password_hash,
        "expires_at": expires_at,
        "single_use": body.single_use,
        "domain_restriction": body.domain_restriction,
        "opens": 0,
        "revoked": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await share_links.insert_one(link)
    await log_event(
        "share_link.create",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="share_link",
        resource_id=token,
        ip=request.client.host if request.client else None,
        metadata={"mode": body.mode, "doc_count": len(body.document_ids)},
    )
    return _public_link(link)


def _public_link(link: dict, filenames_by_id: Optional[dict] = None) -> dict:
    doc_ids = link.get("document_ids", []) or []
    filenames = (
        [filenames_by_id.get(i) for i in doc_ids if filenames_by_id.get(i)]
        if filenames_by_id is not None
        else []
    )
    return {
        "token": link["token"],
        "mode": link["mode"],
        "document_ids": doc_ids,
        "document_filenames": filenames,
        "title": link.get("title"),
        "single_use": link.get("single_use", False),
        "opens": link.get("opens", 0),
        "revoked": link.get("revoked", False),
        "expires_at": link.get("expires_at"),
        "created_at": link["created_at"],
        "domain_restriction": link.get("domain_restriction"),
        "creator_id": link.get("creator_id") or link.get("owner_id"),
        "creator_role": link.get("creator_role"),
        "creator_name": link.get("creator_name"),
        "creator_email": link.get("creator_email"),
    }


@router.get("", response_model=List[ShareLinkOut])
async def list_share_links(user: dict = Depends(require_role(ROLE_EDITOR))):
    query = {} if user["role"] == "owner" else {"owner_id": user["id"]}
    links = await share_links.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    # Resolve filenames for display in the listing
    all_doc_ids = sorted({d for link in links for d in (link.get("document_ids") or [])})
    filenames_by_id: dict = {}
    if all_doc_ids:
        async for d in documents.find(
            {"id": {"$in": all_doc_ids}}, {"_id": 0, "id": 1, "filename": 1}
        ):
            filenames_by_id[d["id"]] = d["filename"]
    return [_public_link(link, filenames_by_id) for link in links]


@router.delete("/{token}")
async def revoke_share_link(
    token: str,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    link = await share_links.find_one({"token": token}, {"_id": 0})
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    if user["role"] != "owner" and link["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    await share_links.update_one({"token": token}, {"$set": {"revoked": True}})
    await log_event(
        "share_link.revoke",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="share_link",
        resource_id=token,
        ip=request.client.host if request.client else None,
    )
    return {"ok": True}


@router.delete("/{token}/purge")
async def purge_share_link(
    token: str,
    request: Request,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    """Hard-delete a share link AND cascade-delete all guest sessions
    and messages tied to it. Use this when you want to remove the audit
    trail entirely (e.g. erasure / GDPR). Soft revoke remains available
    via DELETE /{token}.
    """
    link = await share_links.find_one({"token": token}, {"_id": 0})
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    if user["role"] != "owner" and link.get("creator_id", link.get("owner_id")) != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Cascade
    sess_cursor = sessions_coll.find(
        {"is_guest": True, "share_token": token}, {"_id": 0, "id": 1}
    )
    sess_ids = [s["id"] async for s in sess_cursor]
    if sess_ids:
        await messages.delete_many({"session_id": {"$in": sess_ids}})
        await sessions_coll.delete_many({"id": {"$in": sess_ids}})
    await share_links.delete_one({"token": token})

    await log_event(
        "share_link.purge",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="share_link",
        resource_id=token,
        ip=request.client.host if request.client else None,
        metadata={"sessions_deleted": len(sess_ids)},
    )
    return {"ok": True, "sessions_deleted": len(sess_ids)}


@router.get("/{token}/info")
async def get_share_info(token: str):
    """Public endpoint: returns minimal info so frontend knows if password needed."""
    link = await share_links.find_one({"token": token}, {"_id": 0, "password_hash": 0, "owner_id": 0})
    if not link or link.get("revoked"):
        raise HTTPException(status_code=404, detail="Link not found or revoked")
    if link.get("expires_at"):
        exp = datetime.fromisoformat(link["expires_at"])
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Link expired")
    if link.get("single_use") and link.get("opens", 0) > 0:
        raise HTTPException(status_code=410, detail="Link already used")
    # List document filenames
    docs = await documents.find(
        {"id": {"$in": link["document_ids"]}}, {"_id": 0, "id": 1, "filename": 1}
    ).to_list(100)
    return {
        "token": token,
        "mode": link["mode"],
        "title": link.get("title"),
        "requires_password": link["mode"] == "password",
        "requires_email": bool(link.get("domain_restriction")),
        "domain_restriction": link.get("domain_restriction"),
        "documents": docs,
        "expires_at": link.get("expires_at"),
    }


@router.post("/{token}/verify")
async def verify_share_link(token: str, body: VerifyBody, request: Request):
    link = await share_links.find_one({"token": token}, {"_id": 0})
    if not link or link.get("revoked"):
        raise HTTPException(status_code=404, detail="Link not found or revoked")
    if link.get("expires_at"):
        exp = datetime.fromisoformat(link["expires_at"])
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Link expired")
    if link.get("single_use") and link.get("opens", 0) > 0:
        raise HTTPException(status_code=410, detail="Link already used")

    if link["mode"] == "password":
        if not body.password or not verify_share_password(body.password, link["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid password")

    if link.get("domain_restriction"):
        if not body.email:
            raise HTTPException(status_code=400, detail="Email required")
        if not body.email.lower().endswith(link["domain_restriction"].lower()):
            raise HTTPException(status_code=403, detail="Email domain not allowed")

    # Increment opens, issue scoped guest token
    await share_links.update_one({"token": token}, {"$inc": {"opens": 1}})
    guest_token = create_guest_token(token, link["document_ids"], ttl_seconds=3600)

    await log_event(
        "share_link.open",
        actor_id=None,
        actor_role="guest",
        resource_type="share_link",
        resource_id=token,
        ip=request.client.host if request.client else None,
        metadata={"email": body.email},
    )
    await log_analytics("share_link.open", {"token": token})

    docs = await documents.find(
        {"id": {"$in": link["document_ids"]}}, {"_id": 0, "id": 1, "filename": 1}
    ).to_list(100)

    return {
        "guest_token": guest_token,
        "document_ids": link["document_ids"],
        "documents": docs,
        "title": link.get("title"),
        "mode": link["mode"],
    }



@router.get("/{token}/document/{doc_id}/file")
async def serve_shared_document_file(
    token: str,
    doc_id: str,
    x_guest_token: Optional[str] = Header(None),
):
    """Serve a document file for a verified guest of this share link.
    The guest token must:
      - decode validly,
      - match the requested share-link token,
      - include the requested doc_id in its scoped document_ids.
    The link itself must still be active (not revoked / not expired).
    """
    if not x_guest_token:
        raise HTTPException(status_code=401, detail="Missing guest token")
    payload = decode_guest_token(x_guest_token)
    if not payload or payload.get("type") != "guest":
        raise HTTPException(status_code=401, detail="Invalid guest token")
    if payload.get("share_token") != token:
        raise HTTPException(status_code=403, detail="Token / link mismatch")
    if doc_id not in (payload.get("document_ids") or []):
        raise HTTPException(status_code=403, detail="Document not in scope")

    link = await share_links.find_one({"token": token}, {"_id": 0})
    if not link or link.get("revoked"):
        raise HTTPException(status_code=404, detail="Link not found or revoked")
    if link.get("expires_at"):
        exp = datetime.fromisoformat(link["expires_at"])
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Link expired")
    if doc_id not in (link.get("document_ids") or []):
        # Defence-in-depth: link itself no longer references this doc
        raise HTTPException(status_code=403, detail="Document not in scope")

    doc = await documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    disk_path = Path(doc["disk_path"])
    if not disk_path.exists():
        raise HTTPException(status_code=404, detail="File no longer on disk")
    return FileResponse(
        path=disk_path,
        media_type=doc.get("mime_type") or "application/octet-stream",
        filename=doc.get("filename") or disk_path.name,
    )



# ---------------------------------------------------------------------------
# Share-link CHAT HISTORY (owner: all; editor: own links only)
# ---------------------------------------------------------------------------
@router.get("/history/sessions")
async def list_share_history(
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    """Return guest chat sessions across share links visible to the caller.
    - Owner sees every guest session.
    - Editors see only sessions tied to share links they created.
    Each session item includes link metadata, document filenames,
    message count, and timestamps for client-side filtering.
    """
    # Build the set of share-link tokens the caller can see
    link_query: dict = {}
    if user["role"] != ROLE_OWNER:
        link_query["creator_id"] = user["id"]
    visible_links = await share_links.find(
        link_query,
        {"_id": 0, "password_hash": 0},
    ).to_list(2000)
    if not visible_links:
        return []

    by_token = {link["token"]: link for link in visible_links}

    # Pull guest sessions for those tokens
    sess_cursor = sessions_coll.find(
        {"is_guest": True, "share_token": {"$in": list(by_token.keys())}},
        {"_id": 0},
    ).sort("updated_at", -1)
    sessions_list = await sess_cursor.to_list(1000)
    if not sessions_list:
        return []

    # Counts + last activity per session (single aggregation)
    sess_ids = [s["id"] for s in sessions_list]
    pipeline = [
        {"$match": {"session_id": {"$in": sess_ids}}},
        {
            "$group": {
                "_id": "$session_id",
                "msg_count": {"$sum": 1},
                "last_activity": {"$max": "$created_at"},
            }
        },
    ]
    counts: dict = {}
    async for row in messages.aggregate(pipeline):
        counts[row["_id"]] = {
            "msg_count": row["msg_count"],
            "last_activity": row["last_activity"],
        }

    # Filenames for documents involved (union across all visible links)
    all_doc_ids = sorted({d for link in visible_links for d in (link.get("document_ids") or [])})
    filenames_by_id: dict = {}
    if all_doc_ids:
        async for d in documents.find(
            {"id": {"$in": all_doc_ids}}, {"_id": 0, "id": 1, "filename": 1}
        ):
            filenames_by_id[d["id"]] = d["filename"]

    out = []
    for s in sessions_list:
        link = by_token.get(s.get("share_token"))
        if not link:
            continue
        c = counts.get(s["id"], {})
        doc_ids = link.get("document_ids") or []
        out.append(
            {
                "session_id": s["id"],
                "title": s.get("title"),
                "created_at": s.get("created_at"),
                "updated_at": s.get("updated_at"),
                "last_activity": c.get("last_activity") or s.get("last_active_at") or s.get("updated_at"),
                "message_count": c.get("msg_count", s.get("message_count", 0)),
                # Visitor / device / network metadata
                "ip_masked": s.get("ip_masked"),
                "geo_country": s.get("geo_country"),
                "geo_city": s.get("geo_city"),
                "browser": s.get("browser"),
                "browser_version": s.get("browser_version"),
                "os": s.get("os"),
                "os_version": s.get("os_version"),
                "device_type": s.get("device_type") or "desktop",
                "fingerprint": s.get("fingerprint"),
                # Link & creator
                "share_token": link["token"],
                "link_title": link.get("title"),
                "link_mode": link.get("mode"),
                "link_revoked": link.get("revoked", False),
                "link_expires_at": link.get("expires_at"),
                "creator_id": link.get("creator_id") or link.get("owner_id"),
                "creator_name": link.get("creator_name"),
                "creator_email": link.get("creator_email"),
                "creator_role": link.get("creator_role"),
                "document_ids": s.get("scope_doc_ids") or doc_ids,
                "document_filenames": [
                    filenames_by_id[i] for i in (s.get("scope_doc_ids") or doc_ids) if i in filenames_by_id
                ],
            }
        )
    return out


@router.get("/history/sessions/{session_id}")
async def get_share_history_session(
    session_id: str,
    user: dict = Depends(require_role(ROLE_EDITOR)),
):
    """Return all messages for a single guest session, scoped by caller's
    share-link visibility (owner: any; editor: only own links)."""
    sess = await sessions_coll.find_one({"id": session_id, "is_guest": True}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    link = await share_links.find_one(
        {"token": sess.get("share_token")},
        {"_id": 0, "password_hash": 0},
    )
    if not link:
        raise HTTPException(status_code=404, detail="Linked share link not found")
    if user["role"] != ROLE_OWNER and link.get("creator_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    msgs = (
        await messages.find({"session_id": session_id}, {"_id": 0})
        .sort("created_at", 1)
        .to_list(2000)
    )
    return {"session": sess, "link": _public_link(link), "messages": msgs}



@router.get("/history/summary")
async def share_history_summary(user: dict = Depends(require_role(ROLE_EDITOR))):
    """Top-of-page rollup: total links, total guest sessions, total messages,
    and most-active link (by message count). Owner sees all; editors only own.
    """
    link_query: dict = {}
    if user["role"] != ROLE_OWNER:
        link_query["creator_id"] = user["id"]
    visible_links = await share_links.find(
        link_query, {"_id": 0, "password_hash": 0}
    ).to_list(2000)
    if not visible_links:
        return {
            "total_links": 0,
            "total_sessions": 0,
            "total_messages": 0,
            "most_active_link": None,
        }
    by_token = {link["token"]: link for link in visible_links}

    sess_cursor = sessions_coll.find(
        {"is_guest": True, "share_token": {"$in": list(by_token.keys())}},
        {"_id": 0, "id": 1, "share_token": 1},
    )
    sess_list = await sess_cursor.to_list(5000)
    sess_ids = [s["id"] for s in sess_list]

    msg_total = 0
    per_link_msg: dict = {}
    if sess_ids:
        sess_to_link = {s["id"]: s.get("share_token") for s in sess_list}
        async for row in messages.aggregate([
            {"$match": {"session_id": {"$in": sess_ids}}},
            {"$group": {"_id": "$session_id", "n": {"$sum": 1}}},
        ]):
            msg_total += row["n"]
            tok = sess_to_link.get(row["_id"])
            if tok:
                per_link_msg[tok] = per_link_msg.get(tok, 0) + row["n"]

    most_active = None
    if per_link_msg:
        top_token = max(per_link_msg.items(), key=lambda kv: kv[1])[0]
        link = by_token.get(top_token)
        if link:
            most_active = {
                "share_token": top_token,
                "title": link.get("title"),
                "messages": per_link_msg[top_token],
            }
    return {
        "total_links": len(visible_links),
        "total_sessions": len(sess_list),
        "total_messages": msg_total,
        "most_active_link": most_active,
    }
