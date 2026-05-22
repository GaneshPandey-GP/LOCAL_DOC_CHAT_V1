"""Conversation sessions: list, get messages, rename, delete."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import messages, sessions
from core.deps import get_current_user

router = APIRouter(prefix="/v2/sessions", tags=["sessions"])


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class RenameBody(BaseModel):
    title: str


@router.get("", response_model=List[SessionOut])
async def list_sessions(user: dict = Depends(get_current_user)):
    cursor = sessions.find({"user_id": user["id"]}, {"_id": 0}).sort("updated_at", -1)
    return await cursor.to_list(200)


@router.get("/{session_id}/messages")
async def get_messages(session_id: str, user: dict = Depends(get_current_user)):
    session = await sessions.find_one({"id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    msgs = (
        await messages.find({"session_id": session_id}, {"_id": 0})
        .sort("created_at", 1)
        .to_list(1000)
    )
    return {"session": session, "messages": msgs}


@router.patch("/{session_id}")
async def rename_session(session_id: str, body: RenameBody, user: dict = Depends(get_current_user)):
    res = await sessions.update_one(
        {"id": session_id, "user_id": user["id"]}, {"$set": {"title": body.title}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@router.delete("/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    session = await sessions.find_one({"id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await messages.delete_many({"session_id": session_id})
    await sessions.delete_one({"id": session_id})
    return {"ok": True}
