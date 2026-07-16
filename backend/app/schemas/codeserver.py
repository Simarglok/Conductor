from __future__ import annotations

from pydantic import BaseModel


class WorkspaceInfoResponse(BaseModel):
    branch: str
    ahead: int
    behind: int
    files: list[str]