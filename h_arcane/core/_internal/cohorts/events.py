"""Event contracts and helpers for cohort-facing live updates."""

from __future__ import annotations

from typing import ClassVar
from uuid import UUID

from h_arcane.core._internal.cohorts.schemas import CohortSummaryDto
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.events.base import InngestEventContract


class CohortUpdatedEvent(InngestEventContract):
    """Frontend-facing event emitted whenever cohort aggregate state changes."""

    name: ClassVar[str] = "dashboard/cohort.updated"

    cohort_id: UUID
    summary: CohortSummaryDto


async def emit_cohort_updated_for_run(run_id: UUID) -> CohortSummaryDto | None:
    """Refresh and emit the current cohort summary for a run, if it has a cohort."""
    run = queries.runs.get(run_id)
    if run is None or run.cohort_id is None:
        return None

    from h_arcane.core._internal.cohorts.service import experiment_cohort_service
    from h_arcane.core._internal.cohorts.stats_service import experiment_cohort_stats_service
    from h_arcane.core.dashboard import dashboard_emitter

    experiment_cohort_stats_service.recompute(run.cohort_id)
    summary = experiment_cohort_service.get_summary(run.cohort_id)
    if summary is None:
        return None
    await dashboard_emitter.cohort_updated(summary)
    return summary
