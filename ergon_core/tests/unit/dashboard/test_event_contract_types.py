"""Guards for typed dashboard event payload contracts."""

import inspect
import json
from pathlib import Path
from uuid import uuid4

import pytest
from ergon_core.core.application.communication.models import (
    RunCommunicationMessageDto,
    RunCommunicationThreadDto,
)
from ergon_core.core.application.events.base import InngestEventContract
from ergon_core.core.infrastructure.dashboard import emitter as dashboard_emitter_module
from ergon_core.core.infrastructure.dashboard import event_contracts
from ergon_core.core.infrastructure.dashboard.emitter import DashboardEmitter
from ergon_core.core.infrastructure.dashboard.event_contracts import (
    CohortUpdatedEvent,
    DashboardThreadMessageCreatedEvent,
)
from ergon_core.core.application.read_models.cohorts import CohortSummaryDto


REPO_ROOT = Path(__file__).resolve().parents[4]
EVENT_SCHEMA_MANIFEST = (
    REPO_ROOT / "ergon-dashboard" / "src" / "generated" / "events" / "schemas" / "manifest.json"
)


def test_every_dashboard_event_contract_is_in_generated_schema_manifest() -> None:
    manifest = json.loads(EVENT_SCHEMA_MANIFEST.read_text())
    manifest_events = {entry["eventName"]: entry["modelName"] for entry in manifest}
    contract_events = {
        cls.name: name
        for name, cls in inspect.getmembers(event_contracts, inspect.isclass)
        if issubclass(cls, InngestEventContract) and cls is not InngestEventContract
    }

    assert manifest_events == contract_events


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
async def test_task_status_emitter_uses_assigned_worker_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
