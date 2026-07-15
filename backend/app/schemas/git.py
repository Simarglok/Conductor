from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MergeRequestCreate(BaseModel):
    source_branch: str
    target_branch: str = "main"
    title: str
    description: str | None = None


class MergeRequestResponse(BaseModel):
    id: str
    project_id: str
    author_id: str
    author_name: str
    source_branch: str
    target_branch: str
    title: str
    description: str | None
    status: str  # open / merged / closed
    merge_commit_sha: str | None
    created_at: datetime
    updated_at: datetime


class BranchResponse(BaseModel):
    name: str
    last_commit_sha: str
    last_commit_message: str
    last_commit_date: datetime | None
    ahead_of_main: int | None
    behind_main: int | None


class CommitResponse(BaseModel):
    sha: str
    message: str
    author_name: str
    author_email: str
    date: datetime


class CheckRunResponse(BaseModel):
    name: str
    status: str
    conclusion: str | None
    details_url: str | None