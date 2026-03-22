"""Contract tests for dashboard communication and evaluation workspace events."""

from __future__ import annotations

from uuid import uuid4

from h_arcane.core._internal.communication.schemas import CreateMessageRequest
from h_arcane.core._internal.communication.service import communication_service
from h_arcane.core.dashboard import dashboard_emitter
from h_arcane.core.dashboard.events import (
    DashboardAgentActionCompletedEvent,
    DashboardEvaluationCriterion,
    DashboardTaskEvaluation,
    DashboardTaskEvaluationUpdatedEvent,
)
from tests.utils.cohort_helpers import create_experiment, create_run


def test_save_message_emits_frontend_usable_thread_update(clean_db, monkeypatch):
    experiment = create_experiment("smoke_test", "dashboard-workspace")
    run = create_run(experiment.id)

    emitted = []

    async def record(run_id, thread, message):
        emitted.append((run_id, thread, message))

    monkeypatch.setattr(dashboard_emitter, "thread_message_created", record)

    response = communication_service.save_message(
        CreateMessageRequest(
            run_id=run.id,
            experiment_id=experiment.id,
            from_agent_id=f"{run.id}:worker",
            to_agent_id=f"{run.id}:stakeholder",
            thread_topic="task_clarification",
            content="Can you confirm the intended invariant?",
        )
    )

    assert response.run_id == run.id
    assert len(emitted) == 1
    emitted_run_id, thread, message = emitted[0]
    assert emitted_run_id == run.id
    assert thread.topic == "task_clarification"
    assert thread.messages[0].content == "Can you confirm the intended invariant?"
    assert message.sequence_num == 0


def test_task_evaluation_event_payload_is_frontend_usable():
    run_id = uuid4()
    task_id = uuid4()
    criterion_id = uuid4()
    evaluation_id = uuid4()

    event = DashboardTaskEvaluationUpdatedEvent(
        run_id=run_id,
        task_id=task_id,
        evaluation=DashboardTaskEvaluation(
            id=evaluation_id,
            run_id=run_id,
            task_id=task_id,
            total_score=0.8,
            max_score=1.0,
            normalized_score=0.8,
            stages_evaluated=1,
            stages_passed=1,
            failed_gate=None,
            created_at="2026-03-18T12:00:00Z",
            criterion_results=[
                DashboardEvaluationCriterion(
                    id=criterion_id,
                    stage_num=0,
                    stage_name="proof_validation",
                    criterion_num=0,
                    criterion_type="code_rule",
                    criterion_description="Proof compiles",
                    score=0.8,
                    max_score=1.0,
                    feedback="Compiled successfully with one stylistic warning.",
                    evaluation_input="lake env lean proof.lean",
                    error=None,
                    evaluated_action_ids=["action-1"],
                    evaluated_resource_ids=["resource-1"],
                )
            ],
        ),
    )

    payload = event.model_dump(mode="json")

    assert payload["run_id"] == str(run_id)
    assert payload["task_id"] == str(task_id)
    assert payload["evaluation"]["normalized_score"] == 0.8
    assert payload["evaluation"]["criterion_results"][0]["criterion_description"] == "Proof compiles"


def test_agent_action_completed_event_allows_missing_duration():
    event = DashboardAgentActionCompletedEvent(
        run_id=uuid4(),
        task_id=uuid4(),
        action_id=uuid4(),
        worker_id=uuid4(),
        action_type="reasoning",
        action_output="thinking...",
        duration_ms=None,
        success=True,
        error=None,
        timestamp="2026-03-19T18:48:23Z",
    )

    payload = event.model_dump(mode="json")

    assert payload["duration_ms"] is None
