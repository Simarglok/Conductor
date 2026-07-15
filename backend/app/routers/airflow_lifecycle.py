from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.auth.permissions import require_super_admin
from app.database import get_db_session
from app.models.airflow_instance import AirflowInstance, AirflowInstanceStatus
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.role import Role
from app.models.user import User
from app.schemas.airflow import (
    AirflowInstanceResponse,
    AirflowProvisionResponse,
)

router = APIRouter()


def _gen_password() -> str:
    return uuid4().hex[:24]


@router.post(
    "/projects/{slug}/airflow/provision",
    response_model=AirflowProvisionResponse,
    status_code=201,
)
async def provision_airflow(
    slug: str,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Project).where(Project.slug == slug))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if already exists
    existing = await db.execute(
        select(AirflowInstance).where(AirflowInstance.project_id == project.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="Airflow instance already exists for this project"
        )

    slug_str = project.slug.replace("-", "_")
    admin_pass = _gen_password()
    dev_pass = _gen_password()
    viewer_pass = _gen_password()

    instance = AirflowInstance(
        project_id=project.id,
        internal_url=f"http://airflow-{project.slug}:8080",
        db_name=f"airflow_{slug_str}",
        status=AirflowInstanceStatus.creating,
        admin_user=f"{slug_str}_admin",
        admin_password_encrypted=admin_pass,
        dev_user=f"{slug_str}_dev",
        dev_password_encrypted=dev_pass,
        viewer_user=f"{slug_str}_viewer",
        viewer_password_encrypted=viewer_pass,
    )
    db.add(instance)
    await db.commit()
    await db.refresh(instance)

    # TODO: In production, trigger actual Docker provisioning here
    instance.status = AirflowInstanceStatus.running
    await db.commit()

    return AirflowProvisionResponse(
        instance=AirflowInstanceResponse(
            id=instance.id,
            project_id=instance.project_id,
            internal_url=instance.internal_url,
            external_url=instance.external_url,
            db_name=instance.db_name,
            status=instance.status,
            created_at=instance.created_at,
            updated_at=instance.updated_at,
        ),
        admin_user=instance.admin_user,
        dev_user=instance.dev_user,
        viewer_user=instance.viewer_user,
    )


@router.get(
    "/projects/{slug}/airflow/status",
    response_model=AirflowInstanceResponse,
)
async def get_airflow_status(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Project).where(Project.slug == slug))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check access
    if not user.is_admin:
        result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user.id,
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Access denied")

    inst_result = await db.execute(
        select(AirflowInstance).where(AirflowInstance.project_id == project.id)
    )
    instance = inst_result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Airflow instance not found")

    return AirflowInstanceResponse(
        id=instance.id,
        project_id=instance.project_id,
        internal_url=instance.internal_url,
        external_url=instance.external_url,
        db_name=instance.db_name,
        status=instance.status,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
    )


@router.post("/projects/{slug}/airflow/restart", response_model=AirflowInstanceResponse)
async def restart_airflow(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Project).where(Project.slug == slug))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check project admin
    if not user.is_admin:
        result = await db.execute(
            select(ProjectMember)
            .where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user.id,
            )
            .options(selectinload(ProjectMember.role))
        )
        member = result.scalar_one_or_none()
        if not member or member.role.name != "project_admin":
            raise HTTPException(status_code=403, detail="Project admin access required")

    inst_result = await db.execute(
        select(AirflowInstance).where(AirflowInstance.project_id == project.id)
    )
    instance = inst_result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Airflow instance not found")

    # TODO: Trigger actual restart
    instance.status = AirflowInstanceStatus.running
    await db.commit()

    return AirflowInstanceResponse(
        id=instance.id,
        project_id=instance.project_id,
        internal_url=instance.internal_url,
        external_url=instance.external_url,
        db_name=instance.db_name,
        status=instance.status,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
    )


@router.delete("/projects/{slug}/airflow", status_code=204)
async def delete_airflow(
    slug: str,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Project).where(Project.slug == slug))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    inst_result = await db.execute(
        select(AirflowInstance).where(AirflowInstance.project_id == project.id)
    )
    instance = inst_result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Airflow instance not found")

    await db.delete(instance)
    await db.commit()