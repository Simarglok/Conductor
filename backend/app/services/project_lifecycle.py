"""Pure domain primitives for project runtime lifecycle operations."""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.models.project import ProjectLifecycleStatus
from app.services.lifecycle_errors import (
    InvalidLifecycleTransitionError,
    InvalidParametersError,
)


_PROJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_ALLOWED_TRANSITIONS = frozenset(
    {
        (ProjectLifecycleStatus.PROVISIONING, ProjectLifecycleStatus.READY),
        (ProjectLifecycleStatus.PROVISIONING, ProjectLifecycleStatus.PROVISION_FAILED),
        (ProjectLifecycleStatus.PROVISION_FAILED, ProjectLifecycleStatus.PROVISIONING),
        (ProjectLifecycleStatus.READY, ProjectLifecycleStatus.DELETING),
        (ProjectLifecycleStatus.PROVISION_FAILED, ProjectLifecycleStatus.DELETING),
        (ProjectLifecycleStatus.DELETING, ProjectLifecycleStatus.DELETION_FAILED),
        (ProjectLifecycleStatus.DELETION_FAILED, ProjectLifecycleStatus.DELETING),
    }
)


@dataclass(frozen=True)
class RuntimeIdentity:
    compose_project_name: str
    network_name: str
    airflow_db_name: str
    airflow_db_role: str
    airflow_external_url: str


def derive_runtime_identity(project_id: str, slug: str, airflow_domain: str) -> RuntimeIdentity:
    """Derive stable runtime names from a project's immutable identifier."""

    if not _PROJECT_ID_PATTERN.fullmatch(project_id):
        raise ValueError("project_id must be exactly 32 lowercase hexadecimal characters")

    compose_project_name = f"conductor-p-{project_id}"
    airflow_database_identity = f"conductor_airflow_{project_id}"
    return RuntimeIdentity(
        compose_project_name=compose_project_name,
        network_name=f"{compose_project_name}_default",
        airflow_db_name=airflow_database_identity,
        airflow_db_role=airflow_database_identity,
        airflow_external_url=f"https://{slug}.airflow.{airflow_domain}",
    )


def assert_transition(
    current: ProjectLifecycleStatus,
    target: ProjectLifecycleStatus,
) -> None:
    """Raise unless ``current`` may transition to ``target``."""

    if (current, target) not in _ALLOWED_TRANSITIONS:
        raise InvalidLifecycleTransitionError(
            f"Lifecycle transition from {current.value} to {target.value} is not allowed"
        )


def validate_runtime_parameters(parameters: dict[str, object]) -> dict[str, object]:
    """Validate trusted-template parameters for the MVP empty schema."""

    if type(parameters) is not dict or parameters:
        raise InvalidParametersError("Runtime parameters must be an empty object")
    return parameters
