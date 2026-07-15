from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DAGSummary(BaseModel):
    dag_id: str
    description: str | None
    is_paused: bool
    latest_run_state: str | None
    latest_run_start: datetime | None
    latest_run_end: datetime | None
    next_dagrun: datetime | None


class DAGRunInfo(BaseModel):
    run_id: str
    state: str
    execution_date: datetime
    start_date: datetime | None
    end_date: datetime | None
    duration: float | None