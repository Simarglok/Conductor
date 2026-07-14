from __future__ import annotations

from datetime import timedelta

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.password import hash_password, verify_password
from app.config import settings
from app.database import get_db_session
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenRefreshRequest,
    TokenResponse,
    UserMeResponse,
    UserProjectInfo,
)

router = APIRouter()


async def get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name,
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access = create_access_token(user.id, user.email, user.is_admin)
    refresh, jti = create_refresh_token(user.id)

    r = await get_redis()
    await r.setex(
        f"{settings.redis_refresh_prefix}{jti}",
        int(timedelta(days=settings.refresh_token_expire_days).total_seconds()),
        user.id,
    )
    await r.aclose()

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="User account is disabled")

    access = create_access_token(user.id, user.email, user.is_admin)
    refresh, jti = create_refresh_token(user.id)

    r = await get_redis()
    await r.setex(
        f"{settings.redis_refresh_prefix}{jti}",
        int(timedelta(days=settings.refresh_token_expire_days).total_seconds()),
        user.id,
    )
    await r.aclose()

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(
    body: TokenRefreshRequest, db: AsyncSession = Depends(get_db_session)
):
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    jti = payload["jti"]
    user_id = payload["sub"]

    r = await get_redis()
    stored = await r.get(f"{settings.redis_refresh_prefix}{jti}")
    if stored is None or stored != user_id:
        await r.aclose()
        raise HTTPException(status_code=401, detail="Refresh token expired or revoked")

    # Rotate: delete old, create new
    await r.delete(f"{settings.redis_refresh_prefix}{jti}")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        await r.aclose()
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access = create_access_token(user.id, user.email, user.is_admin)
    new_refresh, new_jti = create_refresh_token(user.id)
    await r.setex(
        f"{settings.redis_refresh_prefix}{new_jti}",
        int(timedelta(days=settings.refresh_token_expire_days).total_seconds()),
        user.id,
    )
    await r.aclose()

    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/auth/me", response_model=UserMeResponse)
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # Fetch project memberships with project and role info
    stmt = (
        select(ProjectMember)
        .where(ProjectMember.user_id == user.id)
        .options(
            selectinload(ProjectMember.project),
            selectinload(ProjectMember.role),
        )
    )
    result = await db.execute(stmt)
    memberships = result.scalars().all()

    projects = [
        UserProjectInfo(
            project_id=m.project.id,
            slug=m.project.slug,
            name=m.project.name,
            role=m.role.name,
        )
        for m in memberships
    ]

    return UserMeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        projects=projects,
    )