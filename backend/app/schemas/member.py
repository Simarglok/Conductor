from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AddMemberRequest(BaseModel):
    email: str
    role_name: str = "developer"


class ChangeRoleRequest(BaseModel):
    role_name: str


class MemberResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    role_name: str
    role_id: str
    joined_at: datetime