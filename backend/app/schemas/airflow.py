from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.airflow_instance import AirflowInstanceStatus


class AirflowInstanceResponse(BaseModel):
    id: str
    project_id: str
    internal_url: str
    external_url: str | None
    db_name: str
    status: AirflowInstanceStatus
    created_at: datetime
    updated_at: datetime


class AirflowProvisionResponse(BaseModel):
    instance: AirflowInstanceResponse
    admin_user: str
    dev_user: str
    viewer_user: str


class AirflowStatsResponse(BaseModel):
    active_dags: int
    paused_dags: int
    running: int
    queued: int
    runs_today: int
    failed_24h: int