"""Guards for typed dashboard event payload contracts."""

from uuid import uuid4

import pytest
from ergon_core.core.dashboard import emitter as dashboard_emitter_module
from ergon_core.core.dashboard.emitter import DashboardEmitter
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


def test_thread_message_dto_exposes_execution_identity() -> None:
    assert "task_execution_id" in RunCommunicationMessageDto.model_fields


def test_thread_dto_exposes_summary_and_task_identity() -> None:
    assert "summary" in RunCommunicationThreadDto.model_fields
    assert "task_id" in RunCommunicationThreadDto.model_fields
    assert "task_id" in RunCommunicationMessageDto.model_fields


def test_cohort_updated_event_uses_cohort_summary_dto() -> None:
    assert CohortUpdatedEvent.model_fields["summary"].annotation is CohortSummaryDto


@pytest.mark.asyncio
async def test_task_status_emitter_uses_assigned_worker_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_events = []

    async def send(event) -> None:
        sent_events.append(event)

    monkeypatch.setattr(dashboard_emitter_module.inngest_client, "send", send)

    emitter = DashboardEmitter(enabled=True)
    await emitter.task_status_changed(
        run_id=uuid4(),
        task_id=uuid4(),
        task_name="task",
        new_status="running",
        assigned_worker_slug="react-worker",
    )

    assert len(sent_events) == 1
    data = sent_events[0].data
    assert data["assigned_worker_slug"] == "react-worker"
    assert "assigned_worker_name" not in data
