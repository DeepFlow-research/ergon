from collections.abc import AsyncGenerator
from typing import ClassVar
from uuid import UUID, uuid4
from unittest.mock import MagicMock

import pytest
from ergon_core.api import EmptyTaskPayload, Sandbox, Task, Worker, WorkerContext, WorkerOutput
from ergon_core.api.worker import WorkerStreamItem
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
from ergon_core.core.application.tasks import execution as task_execution_module
from ergon_core.core.application.graph.models import MutationMeta
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.application.workflows.orchestration import (
    InitializeWorkflowCommand,
    PrepareTaskExecutionCommand,
)
from ergon_core.core.application.tasks.models import AddSubtaskCommand
from ergon_core.core.application.tasks.management import TaskManagementService
from ergon_core.core.application.tasks.execution import TaskExecutionService
from ergon_core.core.application.workflows.service import WorkflowService
from pydantic import BaseModel
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


class _Sandbox(Sandbox):
    async def provision(self) -> None:
        return None


class _Worker(Worker):
    type_slug: ClassVar[str] = "identity-test-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(output=f"{task.task_slug}:{sandbox.env}", success=True)


class _Payload(BaseModel):
    pass


def _task_json(
    *,
    task_slug: str = "root",
    instance_key: str = "sample-1",
    description: str = "Root task",
    worker_name: str = "primary",
) -> dict:
    return Task(
        task_slug=task_slug,
        instance_key=instance_key,
        description=description,
        worker=_Worker(name=worker_name, model="stub:constant"),
        sandbox=_Sandbox(env={"ROLE": worker_name}),
        task_payload=EmptyTaskPayload(),
    ).model_dump(mode="json")


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
                task_json=_task_json(),
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


def test_graph_initialization_copies_definition_task_json_as_task_identity() -> None:
    session = _session()
    definition_id = _definition_with_worker(session, worker_type="minif2f-react")
    run_id = _run(session, definition_id=definition_id)
    definition_task = session.exec(
        select(ExperimentDefinitionTask).where(
            ExperimentDefinitionTask.experiment_definition_id == definition_id
        )
    ).one()

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
    assert node.task_id == definition_task.id
    assert node.task_json == definition_task.task_json
    assert node.parent_task_id is None


def test_graph_node_view_inflates_task_with_runtime_task_id() -> None:
    session = _session()
    run_id = uuid4()
    task_id = uuid4()
    task_json = _task_json(task_slug="dynamic-leaf", worker_name="dynamic")
    session.add(
        RunGraphNode(
            run_id=run_id,
            task_id=task_id,
            task_json=task_json,
            parent_task_id=None,
            instance_key="sample-1",
            task_slug="dynamic-leaf",
            description="Dynamic task",
            status=TaskExecutionStatus.PENDING,
        )
    )
    session.commit()

    node = WorkflowGraphRepository().node(session, run_id=run_id, task_id=task_id)

    assert node.task_id == task_id
    assert node.task.task_id == task_id
    assert node.task.task_slug == "dynamic-leaf"
    assert isinstance(node.task.worker, _Worker)
    assert node.task.worker.name == "dynamic"


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

    from ergon_core.api.registry import registry

    monkeypatch.setitem(
        registry.benchmarks,
        benchmark_type,
        _Benchmark,
    )
    monkeypatch.setattr(
        "ergon_core.core.application.workflows.service.get_session",
        lambda: _session_context(session),
    )

    initialized = await WorkflowService().initialize(
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
async def test_add_subtask_inserts_full_task_json_and_dispatches_task_id_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    definition_id = _definition_with_worker(session, worker_type="minif2f-react")
    run_id = _run(session, definition_id=definition_id)
    parent_task_id = uuid4()
    parent = RunGraphNode(
        run_id=run_id,
        task_id=parent_task_id,
        task_json=_task_json(task_slug="parent"),
        instance_key="sample-1",
        task_slug="parent",
        description="Parent task",
        status=TaskExecutionStatus.RUNNING,
        assigned_worker_slug="minif2f-react",
        level=0,
    )
    session.add(parent)
    session.commit()

    dashboard_emitter = MagicMock()
    sent_events = []

    async def _send(event) -> None:
        sent_events.append(event)

    monkeypatch.setattr(
        "ergon_core.core.application.tasks.management.inngest_client.send",
        _send,
    )
    task = Task(
        task_slug="child",
        instance_key="sample-1",
        description="Dynamic child task",
        worker=_Worker(name="child-worker", model="stub:constant"),
        sandbox=_Sandbox(env={"ROLE": "child"}),
        task_payload=EmptyTaskPayload(),
    )

    result = await TaskManagementService(dashboard_emitter=dashboard_emitter).add_subtask(
        session,
        AddSubtaskCommand(
            run_id=run_id,
            parent_task_id=parent_task_id,
            task=task,
        ),
    )

    inserted = session.exec(
        select(RunGraphNode).where(RunGraphNode.task_id == result.task_id)
    ).one()
    assert inserted.task_json == task.model_dump(mode="json")
    assert inserted.parent_task_id == parent_task_id
    assert inserted.assigned_worker_slug == "child-worker"
    assert result.task_id == inserted.task_id
    assert sent_events
    assert sent_events[0].data["task_id"] == str(result.task_id)
    assert "node_id" not in sent_events[0].data


class _session_context:
    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args) -> None:
        return None
