from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, field_validator, model_validator


class GitConfigResponse(BaseModel):
    repo_url: str
    auth_type: str
    default_branch: str
    dbt_path: str
    dags_path: str
    has_credentials: bool = False  # Backward-compatible generic secret indicator
    has_token: bool = False
    created_at: datetime
    updated_at: datetime


class GitConfigUpdateRequest(BaseModel):
    repo_url: str | None = None
    auth_type: Literal["https", "token", "ssh"] | None = None
    token: str | None = None
    credentials: str | None = None  # Backward compatibility for older clients/SSH
    default_branch: str | None = None
    dbt_path: str | None = None
    dags_path: str | None = None
    webhook_secret: str | None = None

    @field_validator("repo_url")
    @classmethod
    def reject_credentials_in_repo_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parsed = urlsplit(value)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Repository URL must not contain embedded credentials")
        return value

    @field_validator("token", "credentials")
    @classmethod
    def reject_blank_credentials(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Credential must not be blank")
        return value

    @model_validator(mode="after")
    def reject_ambiguous_credentials(self):
        if self.token is not None and self.credentials is not None:
            raise ValueError("Provide either token or credentials, not both")
        return self


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