from __future__ import annotations

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class UserProjectInfo(BaseModel):
    project_id: str
    slug: str
    name: str
    role: str


class UserMeResponse(BaseModel):
    id: str
    email: str
    display_name: str
    is_admin: bool
    projects: list[UserProjectInfo] = []