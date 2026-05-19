"""Deprecated cohort dashboard event projections."""

from ergon_core.core.application.read_models.cohorts import CohortSummaryDto
from ergon_core.core.views.dashboard_events.contracts import CohortUpdatedEvent


def cohort_updated_event_from_summary(summary: CohortSummaryDto) -> CohortUpdatedEvent:
    return CohortUpdatedEvent(
        cohort_id=summary.cohort_id,
        summary=summary,
    )
