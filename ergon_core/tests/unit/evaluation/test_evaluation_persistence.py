from uuid import uuid4

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from ergon_core.api.rubric.results import TaskEvaluationResult
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
