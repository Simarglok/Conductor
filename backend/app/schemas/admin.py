from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class UserListItem(BaseModel):
    id: str
    email: str
    display_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    is_admin: bool | None = None
    is_active: bool | None = None


class RoleCreateRequest(BaseModel):
    name: str
    description: str | None = None


class RoleUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class RoleItem(BaseModel):
    id: str
    name: str
    description: str | None
    is_system: bool
    created_at: datetime


class PermissionCreateRequest(BaseModel):
    resource: str
    action: str
    constraint: str | None = None


class PermissionItem(BaseModel):
    id: str
    resource: str
    action: str
    constraint: str | None


class AdminProjectResponse(BaseModel):
    id: str
    name: str
    slug: str
    member_count: int
    airflow_status: str
    created_at: datetime


class ProjectDeleteRequest(BaseModel):
    confirmation_slug: str


class ProjectDeleteOperationResponse(BaseModel):
    id: str
    operation: Literal["delete"]
    status: str