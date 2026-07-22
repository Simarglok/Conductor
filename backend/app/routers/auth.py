from __future__ import annotations

from datetime import timedelta
from ipaddress import ip_address, ip_network

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user, security
from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.password import hash_password, verify_password
from app.cache import get_redis
from app.config import settings
from app.database import get_db_session
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    ReauthRequest,
    ReauthResponse,
    RegisterRequest,
    TokenRefreshRequest,
    TokenResponse,
    UserMeResponse,
    UserProjectInfo,
)
from app.services.reauth import ReauthError, create_reauth_grant

router = APIRouter()

_LOOPBACK_PROXY_CIDRS = "127.0.0.0/8,::1/128"
_MAX_FORWARDED_HOPS = 32


def _trusted_proxy_networks():
    try:
        values = [value.strip() for value in settings.trusted_proxy_cidrs.split(",")]
        if not values or any(not value for value in values):
            raise ValueError("empty trusted proxy CIDR")
        return tuple(ip_network(value, strict=False) for value in values)
    except ValueError:
        return tuple(
            ip_network(value) for value in _LOOPBACK_PROXY_CIDRS.split(",")
        )


def _source_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    try:
        peer = ip_address(request.client.host)
    except ValueError:
        return "unknown"

    trusted_networks = _trusted_proxy_networks()
    if not any(peer in network for network in trusted_networks):
        return str(peer)

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for is None:
        return str(peer)
    raw_hops = [value.strip() for value in forwarded_for.split(",")]
    if (
        not raw_hops
        or len(raw_hops) > _MAX_FORWARDED_HOPS
        or any(not value for value in raw_hops)
    ):
        return str(peer)
    try:
        hops = [ip_address(value) for value in raw_hops]
    except ValueError:
        return str(peer)

    for hop in reversed(hops):
        if not any(hop in network for network in trusted_networks):
            return str(hop)
    return str(peer)


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
):
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
    await redis.setex(
        f"{settings.redis_refresh_prefix}{jti}",
        int(timedelta(days=settings.refresh_token_expire_days).total_seconds()),
        user.id,
    )

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="User account is disabled")

    access = create_access_token(user.id, user.email, user.is_admin)
    refresh, jti = create_refresh_token(user.id)
    await redis.setex(
        f"{settings.redis_refresh_prefix}{jti}",
        int(timedelta(days=settings.refresh_token_expire_days).total_seconds()),
        user.id,
    )

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(
    body: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    jti = payload["jti"]
    user_id = payload["sub"]
    stored = await redis.get(f"{settings.redis_refresh_prefix}{jti}")
    if stored is None or stored != user_id:
        raise HTTPException(status_code=401, detail="Refresh token expired or revoked")

    await redis.delete(f"{settings.redis_refresh_prefix}{jti}")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access = create_access_token(user.id, user.email, user.is_admin)
    new_refresh, new_jti = create_refresh_token(user.id)
    await redis.setex(
        f"{settings.redis_refresh_prefix}{new_jti}",
        int(timedelta(days=settings.refresh_token_expire_days).total_seconds()),
        user.id,
    )

    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/auth/reauth", response_model=ReauthResponse)
async def reauthenticate(
    request: Request,
    body: ReauthRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    source_ip = _source_ip(request)
    try:
        token = await create_reauth_grant(
            db,
            redis=redis,
            access_token=credentials.credentials,
            password=body.password,
            action=body.action,
            project_id=body.project_id,
            source_ip=source_ip,
        )
    except ReauthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_detail) from None
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Re-authentication request failed",
        ) from None
    return ReauthResponse(token=token, expires_in=settings.reauth_grant_ttl_seconds)


@router.get("/auth/me", response_model=UserMeResponse)
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
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
            project_id=membership.project.id,
            slug=membership.project.slug,
            name=membership.project.name,
            role=membership.role.name,
        )
        for membership in memberships
    ]

    return UserMeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        projects=projects,
    )
