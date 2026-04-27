from uuid import UUID, uuid4

import pytest
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    ExperimentRecord,
    RunRecord,
    RunTaskExecution,
)
from ergon_core.core.runtime.services import task_execution_service as task_execution_module
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.orchestration_dto import (
    InitializeWorkflowCommand,
    PrepareTaskExecutionCommand,
)
from ergon_core.core.runtime.services.task_management_dto import AddSubtaskCommand
from ergon_core.core.runtime.services.task_management_service import TaskManagementService
from ergon_core.core.runtime.services.task_execution_service import TaskExecutionService
from ergon_core.core.runtime.services.workflow_initialization_service import (
    WorkflowInitializationService,
)
from pydantic import BaseModel
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


class _Payload(BaseModel):
    pass


def _session() -> Session:
    _ = ExperimentRecord
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
    run_id: UUID | None = None,
    model_target: str = "stub:constant",
) -> UUID:
    experiment_id = uuid4()
    resolved_run_id = run_id or uuid4()
    session.add(
        ExperimentRecord(
            id=experiment_id,
            name="worker identity",
            benchmark_type="minif2f",
            sample_count=1,
            sample_selection_json={"instance_keys": ["sample-1"]},
            default_worker_team_json={"primary": "minif2f-react"},
            default_model_target=model_target,
            design_json={},
            metadata_json={},
            status="running",
        )
    )
    session.add(
        RunRecord(
            id=resolved_run_id,
            experiment_id=experiment_id,
            workflow_definition_id=definition_id,
            benchmark_type="minif2f",
            instance_key="sample-1",
            worker_team_json={"primary": "minif2f-react"},
            model_target=model_target,
            status=RunStatus.EXECUTING,
        )
    )
    session.commit()
    return resolved_run_id


def test_graph_initialization_writes_concrete_worker_slug_from_definition_binding() -> None:
    session = _session()
    definition_id = _definition_with_worker(session, worker_type="minif2f-react")
    run_id = _run(session, definition_id=definition_id)

    WorkflowGraphRepository().initialize_from_definition(
        session,
        run_id,
        definition_id,
        initial_node_status=TaskExecutionStatus.PENDING,
        initial_edge_status="pending",
        task_payload_model=_Payload,
        meta=MutationMeta(actor="test"),
    )

    node = session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).one()
    assert node.assigned_worker_slug == "minif2f-react"


@pytest.mark.asyncio
async def test_workflow_initialization_returns_node_ids_for_initial_ready_static_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    benchmark_type = "ci-worker-identity"
    definition_id = _definition_with_worker(
        session,
        worker_type="minif2f-react",
        benchmark_type=benchmark_type,
    )
    run_id = _run(session, definition_id=definition_id)

    class _Benchmark:
        task_payload_model = _Payload

    monkeypatch.setitem(
        __import__(
            "ergon_core.core.runtime.services.workflow_initialization_service",
            fromlist=["BENCHMARKS"],
        ).BENCHMARKS,
        benchmark_type,
        _Benchmark,
    )
    monkeypatch.setattr(
        "ergon_core.core.runtime.services.workflow_initialization_service.get_session",
        lambda: _session_context(session),
    )

    initialized = await WorkflowInitializationService().initialize(
        InitializeWorkflowCommand(run_id=run_id, definition_id=definition_id)
    )

    assert len(initialized.initial_ready_tasks) == 1
    ready_task = initialized.initial_ready_tasks[0]
    node = session.exec(
        select(RunGraphNode).where(RunGraphNode.definition_task_id == ready_task.task_id)
    ).one()
    assert ready_task.node_id == node.id
    assert node.assigned_worker_slug == "minif2f-react"


@pytest.mark.asyncio
async def test_dynamic_prepare_uses_node_worker_slug_and_run_model_without_definition_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    definition_id = _definition_with_worker(session, worker_type="minif2f-react")
    run_id = _run(session, definition_id=definition_id, model_target="stub:constant")
    node = RunGraphNode(
        run_id=run_id,
        instance_key="sample-1",
        task_slug="dynamic-leaf",
        description="Dynamic specialist task",
        status=TaskExecutionStatus.PENDING,
        assigned_worker_slug="swebench-react",
        parent_node_id=None,
        level=1,
    )
    session.add(node)
    session.commit()

    monkeypatch.setattr(task_execution_module, "get_session", lambda: _session_context(session))

    prepared = await TaskExecutionService().prepare(
        PrepareTaskExecutionCommand(
            run_id=run_id,
            definition_id=definition_id,
            task_id=None,
            node_id=node.id,
        )
    )

    execution = session.exec(
        select(RunTaskExecution).where(RunTaskExecution.id == prepared.execution_id)
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


@pytest.mark.asyncio
async def test_add_subtask_rejects_unknown_worker_slug_before_creating_node() -> None:
    session = _session()
    definition_id = _definition_with_worker(session, worker_type="minif2f-react")
    run_id = _run(session, definition_id=definition_id)
    parent = RunGraphNode(
        run_id=run_id,
        instance_key="sample-1",
        task_slug="parent",
        description="Parent task",
        status=TaskExecutionStatus.RUNNING,
        assigned_worker_slug="minif2f-react",
        level=0,
    )
    session.add(parent)
    session.commit()

    with pytest.raises(ValueError, match="Unknown worker slug"):
        await TaskManagementService().add_subtask(
            session,
            AddSubtaskCommand(
                run_id=run_id,
                parent_node_id=parent.id,
                task_slug="bad-worker",
                description="Should not be inserted",
                assigned_worker_slug="not-a-real-worker",
            ),
        )

    inserted = session.exec(
        select(RunGraphNode).where(
            RunGraphNode.run_id == run_id,
            RunGraphNode.task_slug == "bad-worker",
        )
    ).first()
    assert inserted is None


class _session_context:
    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args) -> None:
        return None
