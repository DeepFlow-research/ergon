"""Shared DB helpers for TaskCancelledEvent emission sites.

Used by SubtaskCancellationService and TaskManagementService to populate
sandbox_id and benchmark_slug on TaskCancelledEvent before sending.
"""

from uuid import UUID

from sqlmodel import Session, select


def _lookup_sandbox_id(session: Session, execution_id: UUID | None) -> str | None:
    """Return RunTaskExecution.sandbox_id for the given execution, or None."""
    if execution_id is None:
        return None
    # reason: deferred to avoid circular import at module level
    from ergon_core.core.persistence.telemetry.models import RunTaskExecution

    result = session.exec(
        select(RunTaskExecution.sandbox_id).where(RunTaskExecution.id == execution_id)
    ).first()
    return result  # type: ignore[return-value]


def _lookup_benchmark_slug(session: Session, run_id: UUID) -> str | None:
    """Return the benchmark_type (slug) for the run's experiment definition, or None."""
    # reason: deferred to avoid circular import at module level
    from ergon_core.core.persistence.definitions.models import ExperimentDefinition

    # reason: deferred to avoid circular import at module level
    from ergon_core.core.persistence.telemetry.models import RunRecord

    run = session.get(RunRecord, run_id)
    if run is None:
        return None
    defn = session.get(ExperimentDefinition, run.experiment_definition_id)
    if defn is None:
        return None
    return defn.benchmark_type
