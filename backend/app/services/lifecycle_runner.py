"""Operation-to-runner registry for lifecycle workers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from app.models.project_lifecycle_job import LifecycleOperation
from app.services.lifecycle_errors import PermanentLifecycleError
from app.services.lifecycle_queue import ClaimedJob

LifecycleRunner = Callable[[ClaimedJob], Awaitable[None]]


class RunnerNotConfiguredError(PermanentLifecycleError):
    """No trusted runner has been registered for a lifecycle operation."""

    code = "RUNNER_NOT_CONFIGURED"


class LifecycleRunnerRegistry:
    """Explicit registry that enables only trusted operation implementations."""

    def __init__(self, runners: Mapping[LifecycleOperation, LifecycleRunner] | None = None) -> None:
        self._runners = dict(runners or {})

    def register(self, operation: LifecycleOperation, runner: LifecycleRunner) -> None:
        if operation in self._runners:
            raise ValueError(f"Runner already registered for {operation.value}")
        self._runners[operation] = runner

    def resolve(self, operation: LifecycleOperation) -> LifecycleRunner:
        try:
            return self._runners[operation]
        except KeyError as exc:
            raise RunnerNotConfiguredError(
                f"No lifecycle runner configured for operation {operation.value}"
            ) from exc


def build_default_registry() -> LifecycleRunnerRegistry:
    """Return an empty safe registry until trusted saga runners are introduced."""

    return LifecycleRunnerRegistry()
