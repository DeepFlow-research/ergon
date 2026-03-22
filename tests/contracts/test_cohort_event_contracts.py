"""Contract tests for cohort update live events."""

from __future__ import annotations

import asyncio

from h_arcane.core._internal.cohorts import experiment_cohort_service
from h_arcane.core._internal.cohorts.events import CohortUpdatedEvent, emit_cohort_updated_for_run
from h_arcane.core._internal.cohorts.stats_service import experiment_cohort_stats_service
from h_arcane.core._internal.db.models import RunStatus
from h_arcane.core.dashboard import dashboard_emitter
from tests.utils.cohort_helpers import create_experiment, create_run, resolve_cohort


def test_cohort_updated_event_payload_is_frontend_usable(clean_db):
    cohort = resolve_cohort("event-cohort")
    experiment = create_experiment("smoke_test", "Event Workflow")
    create_run(
        experiment.id,
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        status=RunStatus.COMPLETED,
        started_offset_seconds=-20,
        completed_offset_seconds=-10,
        normalized_score=0.9,
    )
    experiment_cohort_stats_service.recompute(cohort.id)
    summary = experiment_cohort_service.get_summary(cohort.id)

    assert summary is not None
    event = CohortUpdatedEvent(cohort_id=cohort.id, summary=summary)
    payload = event.model_dump(mode="json")

    assert payload["cohort_id"] == str(cohort.id)
    assert payload["summary"]["name"] == "event-cohort"
    assert payload["summary"]["status_counts"]["completed"] == 1


def test_emit_cohort_updated_for_run_refreshes_stats_and_emits_summary(clean_db, monkeypatch):
    cohort = resolve_cohort("event-hook-cohort")
    experiment = create_experiment("researchrubrics", "Hook Workflow")
    run = create_run(
        experiment.id,
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        status=RunStatus.FAILED,
        started_offset_seconds=-10,
        completed_offset_seconds=-1,
        error_message="bad run",
    )

    emitted = []

    async def record(summary):
        emitted.append(summary)

    monkeypatch.setattr(dashboard_emitter, "cohort_updated", record)

    summary = asyncio.run(emit_cohort_updated_for_run(run.id))

    assert summary is not None
    assert summary.cohort_id == cohort.id
    assert summary.status_counts.failed == 1
    assert len(emitted) == 1
    assert emitted[0].name == "event-hook-cohort"
