from uuid import UUID, uuid4

import pytest
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.enums import SampleStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    SampleRecord,
    SampleTaskAttempt,
)
from ergon_core.core.application.runtime import execution as task_execution_module
from ergon_core.core.application.runtime.models import MutationMeta
from ergon_core.core.application.runtime.graph_repository import RuntimeGraphRepository
from ergon_core.core.application.runtime.orchestration import (
    InitializeWorkflowCommand,
    PrepareTaskExecutionCommand,
)
from ergon_core.core.application.runtime.task_execution import TaskExecutionService
from ergon_core.core.application.runtime.sample_lifecycle import WorkflowService
from ergon_core.test_support.task_factory import task_with_id
from pydantic import BaseModel
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


class _Payload(BaseModel):
    pass


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _definition_with_worker(
    session: Session,
    *,
    worker_type: str = "minif2f-react",
    benchmark_type: str = "minif2f",
) -> UUID:
    definition_id = uuid4()
    instance_id = uuid4()
    task_id = uuid4()
    session.add_all(
        [
            ExperimentDefinition(
                id=definition_id,
                benchmark_type=benchmark_type,
                name=benchmark_type,
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
                description="Root task",
                task_payload_json={},
            ),
            ExperimentDefinitionWorker(
                experiment_definition_id=definition_id,
                binding_key="primary",
                worker_type=worker_type,
                model_target="stub:constant",
                snapshot_json={},
            ),
            ExperimentDefinitionTaskAssignment(
                experiment_definition_id=definition_id,
                task_id=task_id,
                worker_binding_key="primary",
            ),
        ]
    )
    session.commit()
    return definition_id


def _run(
    session: Session,
    *,
    definition_id: UUID,
    sample_id: UUID | None = None,
    model_target: str = "stub:constant",
) -> UUID:
    resolved_run_id = sample_id or uuid4()
    session.add(
        SampleRecord(
            id=resolved_run_id,
            definition_id=definition_id,
            benchmark_type="minif2f",
            instance_key="sample-1",
            worker_team_json={"primary": "minif2f-react"},
            model_target=model_target,
            status=SampleStatus.EXECUTING,
        )
    )
    session.commit()
    return resolved_run_id


def test_graph_initialization_writes_concrete_worker_slug_from_definition_binding() -> None:
    session = _session()
    definition_id = _definition_with_worker(session, worker_type="minif2f-react")
    sample_id = _run(session, definition_id=definition_id)

    RuntimeGraphRepository().initialize_from_definition(
        session,
        sample_id,
        definition_id,
        initial_node_status=TaskExecutionStatus.PENDING,
        initial_edge_status="pending",
        meta=MutationMeta(actor="test"),
    )

    node = session.exec(select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)).one()
    assert node.assigned_worker_slug == "minif2f-react"


@pytest.mark.asyncio
async def test_workflow_initialization_returns_task_ids_for_initial_ready_static_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    benchmark_type = "ci-worker-identity"
    definition_id = _definition_with_worker(
        session,
        worker_type="minif2f-react",
        benchmark_type=benchmark_type,
    )
    sample_id = _run(session, definition_id=definition_id)

    monkeypatch.setattr(
        "ergon_core.core.application.runtime.sample_lifecycle.get_session",
        lambda: _session_context(session),
    )

    initialized = await WorkflowService().initialize(
        InitializeWorkflowCommand(sample_id=sample_id, definition_id=definition_id)
    )

    assert len(initialized.initial_ready_tasks) == 1
    ready_task = initialized.initial_ready_tasks[0]
    node = session.exec(
        select(SampleGraphNode).where(SampleGraphNode.task_id == ready_task.task_id)
    ).one()
    assert ready_task.task_id == node.task_id
    assert node.assigned_worker_slug == "minif2f-react"


@pytest.mark.asyncio
async def test_dynamic_prepare_uses_node_worker_slug_and_run_model_without_definition_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    definition_id = _definition_with_worker(session, worker_type="minif2f-react")
    sample_id = _run(session, definition_id=definition_id, model_target="stub:constant")
    task_id = uuid4()
    task = task_with_id(
        task_id,
        task_slug="dynamic-leaf",
        instance_key="sample-1",
        description="Dynamic specialist task",
    )
    node = SampleGraphNode(
        task_id=task_id,
        sample_id=sample_id,
        instance_key="sample-1",
        task_slug="dynamic-leaf",
        description="Dynamic specialist task",
        task_json=task.model_dump(mode="json"),
        is_dynamic=True,
        status=TaskExecutionStatus.PENDING,
        assigned_worker_slug="swebench-react",
        parent_task_id=None,
        level=1,
    )
    session.add(node)
    session.commit()

    monkeypatch.setattr(task_execution_module, "get_session", lambda: _session_context(session))

    prepared = await TaskExecutionService().prepare(
        PrepareTaskExecutionCommand(
            sample_id=sample_id,
            definition_id=definition_id,
            task_id=node.task_id,
        )
    )

    execution = session.exec(
        select(SampleTaskAttempt).where(SampleTaskAttempt.id == prepared.execution_id)
    ).one()
    dynamic_worker = session.exec(
        select(ExperimentDefinitionWorker).where(
            ExperimentDefinitionWorker.experiment_definition_id == definition_id,
            ExperimentDefinitionWorker.binding_key == "swebench-react",
        )
    ).first()

    assert prepared.assigned_worker_slug == "swebench-react"
    assert prepared.worker_type == "swebench-react"
    assert prepared.model_target == "stub:constant"
    assert execution.definition_worker_id is None
    assert dynamic_worker is None


class _session_context:
    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args) -> None:
        return None
