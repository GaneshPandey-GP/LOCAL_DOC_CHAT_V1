"""Auth routes: register, login, refresh, me."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from core.audit import log_event
from core.db import users
from core.deps import ROLE_OWNER, ROLE_EDITOR, get_current_user
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: dict


@router.post("/register", response_model=AuthResponse)
async def register(body: RegisterRequest, request: Request):
    existing = await users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Bootstrap-only: the public register endpoint creates the FIRST owner.
    # All subsequent users must be created by an owner via /admin/users.
    count = await users.count_documents({})
    if count > 0:
        raise HTTPException(
            status_code=403,
            detail="Public registration is disabled. Ask an Owner to invite you.",
        )
    role = ROLE_OWNER

    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id,
        "email": body.email.lower(),
        "name": body.name,
        "role": role,
        "password_hash": hash_password(body.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await users.insert_one(doc)

    await log_event(
        "user.register",
        actor_id=user_id,
        actor_role=role,
        resource_type="user",
        resource_id=user_id,
        ip=request.client.host if request.client else None,
    )

    safe_user = {k: v for k, v in doc.items() if k not in ("password_hash", "_id")}
    return {
        "access_token": create_access_token(user_id, role, body.email.lower()),
        "refresh_token": create_refresh_token(user_id),
        "user": safe_user,
    }


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, request: Request):
    user = await users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    await log_event(
        "user.login",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="user",
        resource_id=user["id"],
        ip=request.client.host if request.client else None,
    )

    safe_user = {k: v for k, v in user.items() if k != "password_hash"}
    return {
        "access_token": create_access_token(user["id"], user["role"], user["email"]),
        "refresh_token": create_refresh_token(user["id"]),
        "user": safe_user,
    }


@router.post("/refresh", response_model=AuthResponse)
async def refresh(body: RefreshRequest):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = await users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {
        "access_token": create_access_token(user["id"], user["role"], user["email"]),
        "refresh_token": create_refresh_token(user["id"]),
        "user": user,
    }


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user": user}
