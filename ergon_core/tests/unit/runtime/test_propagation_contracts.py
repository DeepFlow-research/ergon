from ergon_core.core.application.runtime import status as graph_status
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.application.tasks import execution as task_execution_service
from ergon_core.core.application.graph.propagation import on_task_completed_or_failed
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.application.workflows import service as workflow_service
from ergon_core.core.application.workflows.orchestration import PropagationResult
from ergon_core.core.application.graph import propagation as workflow_propagation_service
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine
from uuid import uuid4
import pytest


def _source(module: object) -> str:
    loader = getattr(module, "__loader__")
    source = loader.get_source(module.__name__)
    assert source is not None
    return source


def test_graph_writers_do_not_use_task_execution_status_for_node_status() -> None:
    modules = [
        task_execution_service,
        workflow_service,
        workflow_propagation_service,
    ]
    forbidden_snippets = (
        "new_status=TaskExecutionStatus.",
        "initial_node_status=TaskExecutionStatus.",
    )

    offenders = [
        f"{module.__name__}: {snippet}"
        for module in modules
        for snippet in forbidden_snippets
        if snippet in _source(module)
    ]

    assert offenders == []
    assert graph_status.READY == "ready"


def test_propagation_result_does_not_expose_invalidated_targets() -> None:
    assert "invalidated_targets" not in PropagationResult.model_fields


@pytest.mark.asyncio
async def test_parent_completion_readies_dependency_free_dynamic_children() -> None:
    _ = ExperimentDefinition
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    run_id = uuid4()
    parent = RunGraphNode(
        run_id=run_id,
        instance_key="sample",
        task_slug="parent",
        description="parent",
        status=graph_status.COMPLETED,
        level=0,
    )
    root_child = RunGraphNode(
        run_id=run_id,
        instance_key="sample",
        task_slug="root-child",
        description="root child",
        status=graph_status.PENDING,
        parent_task_id=parent.task_id,
        level=1,
    )
    blocked_child = RunGraphNode(
        run_id=run_id,
        instance_key="sample",
        task_slug="blocked-child",
        description="blocked child",
        status=graph_status.PENDING,
        parent_task_id=parent.task_id,
        level=1,
    )
    session.add_all([parent, root_child, blocked_child])
    session.flush()
    session.add(
        RunGraphEdge(
            run_id=run_id,
            source_task_id=root_child.task_id,
            target_task_id=blocked_child.task_id,
            status=graph_status.EDGE_PENDING,
        )
    )
    session.commit()

    ready = await on_task_completed_or_failed(
        session,
        run_id,
        parent.task_id,
        graph_status.COMPLETED,
        graph_repo=WorkflowGraphRepository(),
    )

    assert ready == [root_child.task_id]
