"""Thumbs up/down feedback on individual messages."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.audit import log_analytics, log_event
from core.db import feedback, messages
from core.deps import get_current_user

router = APIRouter(prefix="/v2/feedback", tags=["feedback"])


class FeedbackBody(BaseModel):
    message_id: str
    rating: int = Field(ge=-1, le=1)  # 1=thumbs up, -1=thumbs down
    comment: Optional[str] = None


@router.post("")
async def submit_feedback(body: FeedbackBody, request: Request, user: dict = Depends(get_current_user)):
    msg = await messages.find_one({"id": body.message_id}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    doc = {
        "id": str(uuid.uuid4()),
        "message_id": body.message_id,
        "session_id": msg.get("session_id"),
        "user_id": user["id"],
        "rating": body.rating,
        "comment": body.comment,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # upsert by (user, message)
    await feedback.update_one(
        {"user_id": user["id"], "message_id": body.message_id},
        {"$set": doc},
        upsert=True,
    )
    await log_analytics("chat.feedback", {"rating": body.rating, "message_id": body.message_id})
    return {"ok": True}
