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
    SampleTaskAttempt,
    SampleTaskEvaluation,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_inline_evaluator_run(session: Session) -> tuple:
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
async def test_persist_success_records_inline_evaluator_binding_key(monkeypatch) -> None:
    from ergon_core.core.application.evaluation import service as module

    session = _session()
    monkeypatch.setattr(module, "get_session", lambda: session)
    monkeypatch.setattr(session, "close", lambda: None)
    sample_id, task_id, execution_id = _seed_inline_evaluator_run(session)
    service = EvaluationService()

    await service.persist_success(
        sample_id=sample_id,
        task_attempt_id=execution_id,
        task_id=task_id,
        binding_key="judge",
        service_result=EvaluationServiceResult(
            result=TaskEvaluationResult(
                task_slug="root",
                score=1.0,
                passed=True,
                evaluator_name="judge",
                criterion_results=[],
            ),
            specs=[],
        ),
    )

    rows = session.exec(select(SampleTaskEvaluation)).all()
    assert len(rows) == 1
    assert rows[0].evaluator_slug == "judge"


@pytest.mark.asyncio
async def test_persist_failure_records_inline_evaluator_binding_key(monkeypatch) -> None:
    from ergon_core.core.application.evaluation import service as module

    session = _session()
    monkeypatch.setattr(module, "get_session", lambda: session)
    monkeypatch.setattr(session, "close", lambda: None)
    sample_id, task_id, execution_id = _seed_inline_evaluator_run(session)
    service = EvaluationService()

    await service.persist_failure(
        sample_id=sample_id,
        task_attempt_id=execution_id,
        task_id=task_id,
        binding_key="judge",
        exc=RuntimeError("boom"),
    )

    rows = session.exec(select(SampleTaskEvaluation)).all()
    assert len(rows) == 1
    assert rows[0].evaluator_slug == "judge"
    assert rows[0].feedback == "RuntimeError: boom"
