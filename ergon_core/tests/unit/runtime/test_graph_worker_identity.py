from uuid import UUID, uuid4

import pytest
from ergon_core.api import Sample
from ergon_core.core.application.samples.materialization import materialize_sample
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.enums import SampleStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    SampleRecord,
    SampleTaskAttempt,
)
from ergon_core.core.application.runtime import execution as task_execution_module
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


def _materialized_sample_with_worker(
    session: Session,
    *,
    worker_type: str = "minif2f-react",
    benchmark_type: str = "minif2f",
) -> UUID:
    sample_id = uuid4()
    task = task_with_id(
        uuid4(),
        task_slug="root",
        instance_key="sample-1",
        description="Root task",
    )
    original_type_slug = task.worker.__class__.type_slug
    task.worker.__class__.type_slug = worker_type
    task.worker.model = "stub:constant"
    sample_row = SampleRecord(
        id=sample_id,
        benchmark_type=benchmark_type,
        instance_key="sample-1",
        worker_team_json={"primary": worker_type},
        model_target="stub:constant",
        status=SampleStatus.EXECUTING,
    )
    session.add(sample_row)
    session.flush()
    try:
        materialize_sample(
            session=session,
            sample=Sample.from_tasks(
                name="sample-1",
                sample_key="sample-1",
                environment_name=benchmark_type,
                tasks=[task],
            ),
            sample_row=sample_row,
        )
    finally:
        task.worker.__class__.type_slug = original_type_slug
    session.commit()
    return sample_id


def test_materialization_writes_concrete_worker_slug_from_task_snapshot() -> None:
    session = _session()
    sample_id = _materialized_sample_with_worker(session, worker_type="minif2f-react")

    node = session.exec(select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)).one()
    assert node.assigned_worker_slug == "minif2f-react"


@pytest.mark.asyncio
async def test_workflow_initialization_returns_task_ids_for_initial_ready_static_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    benchmark_type = "ci-worker-identity"
    sample_id = _materialized_sample_with_worker(
        session,
        worker_type="minif2f-react",
        benchmark_type=benchmark_type,
    )

    monkeypatch.setattr(
        "ergon_core.core.application.runtime.sample_lifecycle.get_session",
        lambda: _session_context(session),
    )

    initialized = await WorkflowService().initialize(InitializeWorkflowCommand(sample_id=sample_id))

    assert len(initialized.initial_ready_tasks) == 1
    ready_task = initialized.initial_ready_tasks[0]
    node = session.exec(
        select(SampleGraphNode).where(SampleGraphNode.task_id == ready_task.task_id)
    ).one()
    assert ready_task.task_id == node.task_id
    assert node.assigned_worker_slug == "minif2f-react"


@pytest.mark.asyncio
async def test_dynamic_prepare_uses_node_worker_slug_and_task_model_without_definition_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    sample_id = _materialized_sample_with_worker(session, worker_type="minif2f-react")
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
            task_id=node.task_id,
        )
    )

    execution = session.exec(
        select(SampleTaskAttempt).where(SampleTaskAttempt.id == prepared.execution_id)
    ).one()

    assert prepared.assigned_worker_slug == "swebench-react"
    assert prepared.worker_type == "swebench-react"
    assert prepared.model_target == "test:none"
    assert execution.task_id == task_id
    assert "experiment_definition_workers" not in SQLModel.metadata.tables


class _session_context:
    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args) -> None:
        return None
