from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GitConfigResponse(BaseModel):
    repo_url: str
    auth_type: str
    default_branch: str
    dbt_path: str
    dags_path: str
    has_credentials: bool = False  # True if a token is configured (never exposed)
    created_at: datetime
    updated_at: datetime


class GitConfigUpdateRequest(BaseModel):
    repo_url: str | None = None
    auth_type: str | None = None
    credentials: str | None = None
    default_branch: str | None = None
    dbt_path: str | None = None
    dags_path: str | None = None
    webhook_secret: str | None = None


class EnvironmentResponse(BaseModel):
    id: str
    name: str
    branch_name: str
    is_protected: bool
    is_active: bool
    created_at: datetime


class EnvironmentCreateRequest(BaseModel):
    name: str
    branch_name: str
    is_protected: bool = False


class EnvironmentUpdateRequest(BaseModel):
    name: str | None = None
    branch_name: str | None = None
    is_protected: bool | None = None
    is_active: bool | None = None


class ProjectSettingsResponse(BaseModel):
    self_approve_enabled: bool


class ProjectSettingsUpdateRequest(BaseModel):
    self_approve_enabled: bool | None = None