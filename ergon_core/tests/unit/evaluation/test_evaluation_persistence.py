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
    BenchmarkDefinitionRecord,
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


def _seed_run(session: Session) -> tuple:
    definition_id = uuid4()
    instance_id = uuid4()
    task_id = uuid4()
    evaluator_id = uuid4()
    run_id = uuid4()
    execution_id = uuid4()
    session.add_all(
        [
            BenchmarkDefinitionRecord(
                id=definition_id,
                name="bench",
                benchmark_type="bench",
                sample_count=1,
            ),
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
async def test_persist_success_writes_evaluation_row_with_service_summary(monkeypatch) -> None:
    from ergon_core.core.application.evaluation import service as service_module

    session = _session()
    monkeypatch.setattr(service_module, "get_session", lambda: session)
    monkeypatch.setattr(session, "close", lambda: None)
    run_id, task_id, evaluator_id, execution_id = _seed_run(session)

    persisted = await EvaluationService().persist_success(
        run_id=run_id,
        task_execution_id=execution_id,
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

    row = session.exec(select(RunTaskEvaluation)).one()
    assert row.summary_json == persisted.summary.model_dump(mode="json")
    assert row.score == 0.75
    assert row.passed is True
    assert row.task_execution_id == execution_id
    assert row.task_id == task_id
    assert row.definition_evaluator_id == evaluator_id
