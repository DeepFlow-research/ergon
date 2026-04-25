"""Guards for typed dashboard event payload contracts."""

from ergon_core.core.api.schemas import (
    RunCommunicationMessageDto,
    RunCommunicationThreadDto,
)
from ergon_core.core.dashboard.event_contracts import (
    CohortUpdatedEvent,
    DashboardThreadMessageCreatedEvent,
)
from ergon_core.core.runtime.services.cohort_schemas import CohortSummaryDto


def test_thread_message_event_uses_dashboard_dtos() -> None:
    assert DashboardThreadMessageCreatedEvent.model_fields["thread"].annotation is (
        RunCommunicationThreadDto
    )
    assert DashboardThreadMessageCreatedEvent.model_fields["message"].annotation is (
        RunCommunicationMessageDto
    )


def test_cohort_updated_event_uses_cohort_summary_dto() -> None:
    assert CohortUpdatedEvent.model_fields["summary"].annotation is CohortSummaryDto
