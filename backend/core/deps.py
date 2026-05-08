"""Auth dependencies: authenticated user extraction + RBAC helpers."""
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from .db import users
from .security import decode_token, decode_guest_token

ROLE_OWNER = "owner"
ROLE_EDITOR = "editor"
ROLE_GUEST = "guest"

# Viewer role removed (Feb 2026). Kept ROLE_VIEWER constant for backward
# compatibility with any legacy seed data; rank-1 slot is unused at runtime.
ROLE_VIEWER = "viewer"

ROLE_RANK = {ROLE_VIEWER: 1, ROLE_EDITOR: 2, ROLE_OWNER: 3}


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = await users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    try:
        return await get_current_user(authorization=authorization)
    except HTTPException:
        return None


def require_role(min_role: str):
    """Dependency factory enforcing minimum role."""
    min_rank = ROLE_RANK[min_role]

    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        rank = ROLE_RANK.get(user.get("role"), 0)
        if rank < min_rank:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return _dep


async def get_guest_context(x_guest_token: Optional[str] = Header(None)) -> dict:
    """Extract and validate a scoped guest token."""
    if not x_guest_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing guest token")
    payload = decode_guest_token(x_guest_token)
    if not payload or payload.get("type") != "guest":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid guest token")
    return payload
