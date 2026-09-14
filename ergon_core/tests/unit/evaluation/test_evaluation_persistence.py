from uuid import uuid4
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from ergon_core.api.rubric.results import TaskEvaluationResult
from ergon_core.api import Rubric
from ergon_core.api.criterion import CriterionContext, CriterionOutcome
from ergon_core.api.worker import WorkerOutput
from ergon_core.core.application.evaluation.models import CriterionSpec
from ergon_core.core.jobs.task.evaluate import job as evaluation_job
from ergon_core.core.infrastructure.dashboard.emitter import DashboardEmitter
from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.test_support.task_factory import task_with_id
from tests.fixtures.mag_preport import PreportCriterion
from ergon_core.core.application.evaluation.service import (
    EvaluationService,
    EvaluationServiceResult,
)
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.enums import SampleStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    SampleRecord,
    SampleTaskEvaluation,
    SampleTaskAttempt,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_run(session: Session) -> tuple:
    task_id = uuid4()
    sample_id = uuid4()
    execution_id = uuid4()
    session.add_all(
        [
            SampleRecord(
                id=sample_id,
                benchmark_type="bench",
                instance_key="sample-1",
                worker_team_json={},
                status=SampleStatus.EXECUTING,
            ),
            SampleGraphNode(
                sample_id=sample_id,
                task_id=task_id,
                instance_key="sample-1",
                task_slug="root",
                description="root task",
                status="running",
            ),
            SampleTaskAttempt(
                id=execution_id,
                sample_id=sample_id,
                task_id=task_id,
                status=TaskExecutionStatus.RUNNING,
            ),
        ]
    )
    session.commit()
    return sample_id, task_id, execution_id


@pytest.mark.asyncio
async def test_persist_success_writes_evaluation_row_with_service_summary(monkeypatch) -> None:
    from ergon_core.core.application.evaluation import service as service_module

    session = _session()
    monkeypatch.setattr(service_module, "get_session", lambda: session)
    monkeypatch.setattr(session, "close", lambda: None)
    sample_id, task_id, execution_id = _seed_run(session)

    persisted = await EvaluationService().persist_success(
        sample_id=sample_id,
        task_attempt_id=execution_id,
        task_id=task_id,
        binding_key="judge",
        service_result=EvaluationServiceResult(
            result=TaskEvaluationResult(
                task_slug="root",
                score=0.75,
                passed=True,
                evaluator_name="judge",
                criterion_results=[],
            ),
            specs=[],
        ),
    )

    row = session.exec(select(SampleTaskEvaluation)).one()
    assert row.summary_json == persisted.summary.model_dump(mode="json")
    assert row.score == 0.75
    assert row.passed is True
    assert row.task_attempt_id == execution_id
    assert row.task_id == task_id
    assert row.evaluator_slug == "judge"


@pytest.mark.asyncio
async def test_large_evaluation_is_persisted_before_a_bounded_dashboard_notification(monkeypatch):
    from ergon_core.core.application.evaluation import service as service_module

    session = _session()
    monkeypatch.setattr(service_module, "get_session", lambda: session)
    monkeypatch.setattr(session, "close", lambda: None)
    sample_id, task_id, execution_id = _seed_run(session)
    criterion = PreportCriterion(slug="large-input")
    large_input = "retained judge evidence " * 200_000
    result = EvaluationServiceResult(
        result=TaskEvaluationResult(
            task_slug="root",
            score=0.75,
            passed=True,
            evaluator_name="judge",
            criterion_results=[
                CriterionOutcome(
                    slug=criterion.slug,
                    score=0.75,
                    passed=True,
                    evaluation_input=large_input,
                )
            ],
        ),
        specs=[CriterionSpec(criterion=criterion)],
    )
    monkeypatch.setattr(EvaluationService, "evaluate", AsyncMock(return_value=result))
    send = AsyncMock()
    monkeypatch.setattr(inngest_client, "send", send)
    monkeypatch.setattr(evaluation_job, "get_dashboard_event_publisher", DashboardEmitter)
    monkeypatch.setattr(
        evaluation_job, "get_trace_sink", lambda: SimpleNamespace(emit_span=lambda span: None)
    )
    task = task_with_id(task_id, task_slug="root", instance_key="sample-1", description="root")

    completed = await evaluation_job._run_evaluation(
        evaluator=Rubric(name="judge", criteria=(criterion,)),
        context=CriterionContext(
            sample_id=sample_id,
            task_id=task_id,
            execution_id=execution_id,
            task=task,
            worker_result=WorkerOutput(output="done"),
        ),
        binding_key="judge",
        evaluator_index=0,
        view=SimpleNamespace(task_id=task_id),
        sample_id=sample_id,
        task_id=task_id,
        execution_id=execution_id,
        span_start=datetime.now(UTC),
    )

    row = session.exec(select(SampleTaskEvaluation)).one()
    assert row.summary_json["criterion_results"][0]["evaluation_input"] == large_input
    assert len(json.dumps(row.summary_json)) > 3 * 1024 * 1024
    assert row.score == completed.score == 0.75
    send.assert_awaited_once()
    event = send.call_args.args[0]
    assert event.name == "dashboard/task.evaluation_updated"
    assert event.data == {"sample_id": str(sample_id), "task_id": str(task_id)}
    assert len(json.dumps(event.data)) < 256
