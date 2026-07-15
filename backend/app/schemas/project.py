from __future__ import annotations

from datetime import datetime
import re

from pydantic import BaseModel, field_validator


class ProjectCreateRequest(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        if v and not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", v):
            raise ValueError("slug must be lowercase alphanumeric with hyphens")
        return v


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None
    self_approve_enabled: bool
    created_at: datetime
    updated_at: datetime
    member_count: int = 0