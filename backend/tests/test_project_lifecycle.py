from __future__ import annotations

from dataclasses import FrozenInstanceError
import math
from typing import Any

import pytest

from app.models.project import ProjectLifecycleStatus
from app.services.lifecycle_errors import (
    ErrorDisposition,
    ForeignResourceConflictError,
    InvalidComposeError,
    InvalidLifecycleTransitionError,
    InvalidParametersError,
    InvalidTemplateError,
    LifecycleError,
    PermanentLifecycleError,
    TransientLifecycleError,
    classify_lifecycle_error,
    retry_delay,
)
from app.services.project_lifecycle import (
    RuntimeIdentity,
    assert_transition,
    derive_runtime_identity,
    validate_runtime_parameters,
)


PROJECT_ID = "0123456789abcdef0123456789abcdef"


def test_runtime_identity_is_derived_from_immutable_project_id() -> None:
    identity = derive_runtime_identity(PROJECT_ID, "analytics", "example.com")

    assert identity.compose_project_name == f"conductor-p-{PROJECT_ID}"
    assert identity.network_name == f"conductor-p-{PROJECT_ID}_default"
    assert identity.airflow_db_name == f"conductor_airflow_{PROJECT_ID}"
    assert identity.airflow_db_role == f"conductor_airflow_{PROJECT_ID}"
    assert identity.airflow_external_url == "https://analytics.airflow.example.com"


@pytest.mark.parametrize(
    "project_id",
    [
        "short",
        "g" * 32,
        "A" * 32,
        "0" * 31 + "-",
        "0" * 33,
    ],
)
def test_runtime_identity_rejects_noncanonical_project_ids(project_id: str) -> None:
    with pytest.raises(ValueError, match="32 lowercase hexadecimal"):
        derive_runtime_identity(project_id, "analytics", "example.com")


def test_runtime_identity_is_stable_across_retries_and_slug_changes() -> None:
    first = derive_runtime_identity(PROJECT_ID, "old-slug", "example.com")
    retry = derive_runtime_identity(PROJECT_ID, "new-slug", "example.com")

    assert first.compose_project_name == retry.compose_project_name
    assert first.network_name == retry.network_name
    assert first.airflow_db_name == retry.airflow_db_name
    assert first.airflow_db_role == retry.airflow_db_role
    assert "old-slug" not in " ".join(
        (
            first.compose_project_name,
            first.network_name,
            first.airflow_db_name,
            first.airflow_db_role,
        )
    )
    assert retry.airflow_external_url == "https://new-slug.airflow.example.com"


def test_runtime_database_identifiers_fit_postgresql_limit() -> None:
    identity = derive_runtime_identity("f" * 32, "analytics", "example.com")

    assert len(identity.airflow_db_name.encode("utf-8")) <= 63
    assert len(identity.airflow_db_role.encode("utf-8")) <= 63


def test_runtime_identity_is_frozen() -> None:
    identity = derive_runtime_identity(PROJECT_ID, "analytics", "example.com")

    with pytest.raises(FrozenInstanceError):
        identity.compose_project_name = "changed"  # type: ignore[misc]

    assert isinstance(identity, RuntimeIdentity)


ALLOWED_TRANSITIONS = {
    (ProjectLifecycleStatus.PROVISIONING, ProjectLifecycleStatus.READY),
    (ProjectLifecycleStatus.PROVISIONING, ProjectLifecycleStatus.PROVISION_FAILED),
    (ProjectLifecycleStatus.PROVISION_FAILED, ProjectLifecycleStatus.PROVISIONING),
    (ProjectLifecycleStatus.READY, ProjectLifecycleStatus.DELETING),
    (ProjectLifecycleStatus.PROVISION_FAILED, ProjectLifecycleStatus.DELETING),
    (ProjectLifecycleStatus.DELETING, ProjectLifecycleStatus.DELETION_FAILED),
    (ProjectLifecycleStatus.DELETION_FAILED, ProjectLifecycleStatus.DELETING),
}


@pytest.mark.parametrize(("current", "target"), sorted(ALLOWED_TRANSITIONS))
def test_assert_transition_accepts_exact_design_transitions(
    current: ProjectLifecycleStatus,
    target: ProjectLifecycleStatus,
) -> None:
    assert_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (current, target)
        for current in ProjectLifecycleStatus
        for target in ProjectLifecycleStatus
        if (current, target) not in ALLOWED_TRANSITIONS
    ],
)
def test_assert_transition_rejects_every_other_transition(
    current: ProjectLifecycleStatus,
    target: ProjectLifecycleStatus,
) -> None:
    with pytest.raises(
        InvalidLifecycleTransitionError,
        match=rf"{current.value}.*{target.value}",
    ):
        assert_transition(current, target)


def test_runtime_parameters_accept_only_an_exact_empty_dict() -> None:
    assert validate_runtime_parameters({}) == {}


@pytest.mark.parametrize(
    "parameters",
    [
        {"ENV": {"PASSWORD": "secret"}},
        {"mounts": ["/host:/container"]},
        {"command": ["sh", "-c", "whoami"]},
        {"unknown": None},
        [],
        None,
        "{}",
    ],
)
def test_runtime_parameters_reject_unknown_keys_and_non_dict_values_permanently(
    parameters: object,
) -> None:
    with pytest.raises(InvalidParametersError, match="must be an empty object") as caught:
        validate_runtime_parameters(parameters)  # type: ignore[arg-type]

    assert isinstance(caught.value, PermanentLifecycleError)


@pytest.mark.parametrize(
    ("error_type", "code"),
    [
        (InvalidTemplateError, "INVALID_TEMPLATE"),
        (InvalidParametersError, "INVALID_PARAMETERS"),
        (ForeignResourceConflictError, "FOREIGN_RESOURCE_CONFLICT"),
        (InvalidComposeError, "INVALID_COMPOSE"),
        (InvalidLifecycleTransitionError, "INVALID_LIFECYCLE_TRANSITION"),
    ],
)
def test_permanent_lifecycle_errors_have_stable_codes_and_classification(
    error_type: type[PermanentLifecycleError],
    code: str,
) -> None:
    error = error_type("safe failure")

    assert isinstance(error, LifecycleError)
    assert error.code == code
    assert classify_lifecycle_error(error) is ErrorDisposition.PERMANENT


@pytest.mark.parametrize(
    "error",
    [
        TransientLifecycleError("temporary lifecycle failure"),
        TimeoutError("temporary timeout"),
        ConnectionError("temporary connection failure"),
        RuntimeError("unclassified failure"),
    ],
)
def test_transient_and_unknown_errors_are_retryable(error: Exception) -> None:
    assert classify_lifecycle_error(error) is ErrorDisposition.TRANSIENT


def test_retry_delay_uses_injected_jitter_and_is_capped() -> None:
    assert retry_delay(0, base=2.0, cap=10.0, jitter=0.25) == 2.25
    assert retry_delay(1, base=2.0, cap=10.0, jitter=0.25) == 4.25
    assert retry_delay(2, base=2.0, cap=10.0, jitter=0.25) == 8.25
    assert retry_delay(3, base=2.0, cap=10.0, jitter=0.25) == 10.0
    assert retry_delay(10_000, base=2.0, cap=10.0, jitter=0.25) == 10.0


def test_retry_delay_handles_full_finite_float_range_without_overflow() -> None:
    minimum_subnormal = float.fromhex("0x0.0000000000001p-1022")
    cap = 1e308

    assert retry_delay(0, base=minimum_subnormal, cap=cap, jitter=0.0) == minimum_subnormal
    assert retry_delay(2_000, base=minimum_subnormal, cap=cap, jitter=0.0) == math.ldexp(
        minimum_subnormal, 2_000
    )
    assert retry_delay(10_000, base=minimum_subnormal, cap=cap, jitter=0.0) == cap
    assert retry_delay(10**10_000, base=minimum_subnormal, cap=cap, jitter=0.0) == cap


@pytest.mark.parametrize("field", ["base", "cap", "jitter"])
def test_retry_delay_rejects_integer_components_too_large_for_finite_float(
    field: str,
) -> None:
    values: dict[str, Any] = {"base": 1.0, "cap": 10.0, "jitter": 0.0}
    values[field] = 10**10_000

    with pytest.raises(ValueError):
        retry_delay(
            0,
            base=values["base"],
            cap=values["cap"],
            jitter=values["jitter"],
        )


@pytest.mark.parametrize(
    ("attempt", "base", "cap", "jitter"),
    [
        (-1, 1.0, 10.0, 0.0),
        (0, 0.0, 10.0, 0.0),
        (0, -1.0, 10.0, 0.0),
        (0, 1.0, 0.0, 0.0),
        (0, 1.0, -1.0, 0.0),
        (0, 1.0, 10.0, -0.1),
    ],
)
def test_retry_delay_rejects_invalid_inputs(
    attempt: int,
    base: float,
    cap: float,
    jitter: float,
) -> None:
    with pytest.raises(ValueError):
        retry_delay(attempt, base=base, cap=cap, jitter=jitter)


@pytest.mark.parametrize("field", ["base", "cap", "jitter"])
@pytest.mark.parametrize("invalid_value", [True, False, "1.0", None, object()])
def test_retry_delay_rejects_boolean_and_non_number_components_with_value_error(
    field: str,
    invalid_value: object,
) -> None:
    values: dict[str, Any] = {"base": 1.0, "cap": 10.0, "jitter": 0.0}
    values[field] = invalid_value

    with pytest.raises(ValueError):
        retry_delay(  # type: ignore[arg-type]
            0,
            base=values["base"],
            cap=values["cap"],
            jitter=values["jitter"],
        )
