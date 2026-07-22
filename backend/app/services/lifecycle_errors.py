"""Lifecycle exception types, retry classification, and backoff primitives."""

from __future__ import annotations

from enum import StrEnum
import math


class ErrorDisposition(StrEnum):
    """Whether a failed lifecycle step should be retried automatically."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"


class LifecycleError(Exception):
    """Base class for stable lifecycle-domain failures."""

    code = "LIFECYCLE_ERROR"


class TransientLifecycleError(LifecycleError):
    """A lifecycle failure that may succeed without changed desired state."""

    code = "TRANSIENT_LIFECYCLE_ERROR"


class PermanentLifecycleError(LifecycleError):
    """A lifecycle failure that cannot succeed without changed input or state."""

    code = "PERMANENT_LIFECYCLE_ERROR"


class InvalidLifecycleTransitionError(PermanentLifecycleError):
    """Raised when a requested project state transition is not allowed."""

    code = "INVALID_LIFECYCLE_TRANSITION"


class InvalidParametersError(PermanentLifecycleError):
    """Raised when deployment parameters violate the trusted-template schema."""

    code = "INVALID_PARAMETERS"


class InvalidTemplateError(PermanentLifecycleError):
    """Raised when a trusted runtime template is missing or invalid."""

    code = "INVALID_TEMPLATE"


class ForeignResourceConflictError(PermanentLifecycleError):
    """Raised when a deterministic name belongs to an unverified foreign resource."""

    code = "FOREIGN_RESOURCE_CONFLICT"


class InvalidComposeError(PermanentLifecycleError):
    """Raised when rendered Docker Compose output does not validate."""

    code = "INVALID_COMPOSE"


# Descriptive aliases keep callers aligned on one stable disposition/code.
OwnershipConflictError = ForeignResourceConflictError
ResourceOwnershipConflictError = ForeignResourceConflictError
InvalidComposeOutputError = InvalidComposeError
InvalidTemplateParametersError = InvalidParametersError
InvalidLifecycleTransition = InvalidLifecycleTransitionError


def classify_lifecycle_error(exc: Exception) -> ErrorDisposition:
    """Classify known permanent failures; unknown operational failures are retryable."""

    if isinstance(exc, PermanentLifecycleError):
        return ErrorDisposition.PERMANENT
    return ErrorDisposition.TRANSIENT


def _normalize_retry_component(
    value: object,
    *,
    name: str,
    allow_zero: bool,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be a {qualifier} finite number")
    try:
        normalized = float(value)
    except (OverflowError, ValueError) as exc:
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be a {qualifier} finite number") from exc

    invalid_range = normalized < 0 if allow_zero else normalized <= 0
    if not math.isfinite(normalized) or invalid_range:
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be a {qualifier} finite number")
    return normalized


def retry_delay(attempt: int, *, base: float, cap: float, jitter: float) -> float:
    """Return capped exponential delay plus a caller-injected non-negative jitter sample.

    ``attempt`` is zero-based. Randomness is sampled by the caller, keeping this
    domain primitive deterministic and straightforward to test.
    """

    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
        raise ValueError("attempt must be a non-negative integer")

    normalized_base = _normalize_retry_component(base, name="base", allow_zero=False)
    normalized_cap = _normalize_retry_component(cap, name="cap", allow_zero=False)
    normalized_jitter = _normalize_retry_component(jitter, name="jitter", allow_zero=True)

    if normalized_base >= normalized_cap:
        exponential = normalized_cap
    else:
        cap_threshold = math.log2(normalized_cap) - math.log2(normalized_base)
        if attempt >= cap_threshold:
            exponential = normalized_cap
        else:
            exponential = min(
                normalized_cap,
                math.ldexp(normalized_base, attempt),
            )

    if normalized_jitter >= normalized_cap - exponential:
        return normalized_cap
    return exponential + normalized_jitter
