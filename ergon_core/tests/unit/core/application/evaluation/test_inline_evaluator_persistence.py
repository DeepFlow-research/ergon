from uuid import uuid4

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from ergon_core.api.rubric.results import TaskEvaluationResult
from ergon_core.core.application.evaluation.service import (
    EvaluationService,
    EvaluationServiceResult,
)
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionEvaluator,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
)
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunTaskEvaluation,
    RunTaskExecution,
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
    definition_id = uuid4()
    instance_id = uuid4()
    task_id = uuid4()
    evaluator_id = uuid4()
    run_id = uuid4()
    execution_id = uuid4()
    session.add_all(
        [
            ExperimentDefinition(
                id=definition_id,
                benchmark_type="bench",
                name="bench",
                metadata_json={},
            ),
            ExperimentDefinitionInstance(
                id=instance_id,
                experiment_definition_id=definition_id,
                instance_key="sample-1",
            ),
            ExperimentDefinitionTask(
                id=task_id,
                experiment_definition_id=definition_id,
                instance_id=instance_id,
                task_slug="root",
                description="root task",
                task_payload_json={},
                task_json={},
            ),
            ExperimentDefinitionEvaluator(
                id=evaluator_id,
                experiment_definition_id=definition_id,
                binding_key="judge",
                evaluator_type="rubric",
                snapshot_json={"name": "judge"},
            ),
            RunRecord(
                id=run_id,
                definition_id=definition_id,
                benchmark_type="bench",
                instance_key="sample-1",
                worker_team_json={},
                status=RunStatus.EXECUTING,
            ),
            RunGraphNode(
                run_id=run_id,
                task_id=task_id,
                instance_key="sample-1",
                task_slug="root",
                description="root task",
                status="running",
            ),
            RunTaskExecution(
                id=execution_id,
                run_id=run_id,
                task_id=task_id,
                status=TaskExecutionStatus.RUNNING,
            ),
        ]
    )
    session.commit()
    return run_id, task_id, evaluator_id, execution_id


@pytest.mark.asyncio
async def test_persist_success_links_inline_evaluator_definition_row(monkeypatch) -> None:
    from ergon_core.core.application.evaluation import service as module

    session = _session()
    monkeypatch.setattr(module, "get_session", lambda: session)
    monkeypatch.setattr(session, "close", lambda: None)
    run_id, task_id, evaluator_id, execution_id = _seed_inline_evaluator_run(session)
    service = EvaluationService()

    await service.persist_success(
        run_id=run_id,
        task_execution_id=execution_id,
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

    rows = session.exec(select(RunTaskEvaluation)).all()
    assert len(rows) == 1
    assert rows[0].definition_evaluator_id == evaluator_id


@pytest.mark.asyncio
async def test_persist_failure_links_inline_evaluator_definition_row(monkeypatch) -> None:
    from ergon_core.core.application.evaluation import service as module

    session = _session()
    monkeypatch.setattr(module, "get_session", lambda: session)
    monkeypatch.setattr(session, "close", lambda: None)
    run_id, task_id, evaluator_id, execution_id = _seed_inline_evaluator_run(session)
    service = EvaluationService()

    await service.persist_failure(
        run_id=run_id,
        task_execution_id=execution_id,
        task_id=task_id,
        binding_key="judge",
        exc=RuntimeError("boom"),
    )

    rows = session.exec(select(RunTaskEvaluation)).all()
    assert len(rows) == 1
    assert rows[0].definition_evaluator_id == evaluator_id


@pytest.mark.asyncio
async def test_persist_success_creates_dynamic_inline_evaluator_definition_row(
    monkeypatch,
) -> None:
    from ergon_core.core.application.evaluation import service as module

    session = _session()
    monkeypatch.setattr(module, "get_session", lambda: session)
    monkeypatch.setattr(session, "close", lambda: None)
    run_id, task_id, _evaluator_id, execution_id = _seed_inline_evaluator_run(session)
    service = EvaluationService()

    await service.persist_success(
        run_id=run_id,
        task_execution_id=execution_id,
        task_id=task_id,
        binding_key="dynamic-judge",
        service_result=EvaluationServiceResult(
            result=TaskEvaluationResult(
                task_slug="root",
                score=1.0,
                passed=True,
                evaluator_name="dynamic-judge",
                criterion_results=[],
            ),
            specs=[],
        ),
    )

    evaluator_row = session.exec(
        select(ExperimentDefinitionEvaluator).where(
            ExperimentDefinitionEvaluator.binding_key == "dynamic-judge"
        )
    ).one()
    rows = session.exec(select(RunTaskEvaluation)).all()
    assert rows[-1].definition_evaluator_id == evaluator_row.id
