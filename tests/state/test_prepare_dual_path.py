"""Tests for the dual-path TaskExecutionService.prepare() refactor.

Covers:
- Graph-native path: node_id present → resolves worker from graph node
- Definition path: node_id absent → resolves worker from definition tables
- Error cases for the graph-native path
- Attempt numbering across retries
"""

from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.runtime.errors.inngest_errors import ConfigurationError
from ergon_core.core.runtime.services.orchestration_dto import (
    PrepareTaskExecutionCommand,
)
from ergon_core.core.runtime.services.task_execution_service import (
    TaskExecutionService,
)
from sqlmodel import Session

from tests.state.factories import seed_flat_tasks, seed_run

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_worker(
    session: Session,
    definition_id: UUID,
    binding_key: str = "researcher",
    worker_type: str = "cloud-llm",
    model_target: str = "gpt-4o",
) -> ExperimentDefinitionWorker:
    worker = ExperimentDefinitionWorker(
        experiment_definition_id=definition_id,
        binding_key=binding_key,
        worker_type=worker_type,
        model_target=model_target,
    )
    session.add(worker)
    session.flush()
    return worker


def _seed_graph_node(
    session: Session,
    run_id: UUID,
    *,
    task_slug: str = "dynamic-task-1",
    description: str = "A dynamic task",
    status: str = "pending",
    assigned_worker_slug: str | None = "researcher",
    instance_key: str = "inst-0",
    definition_task_id: UUID | None = None,
) -> RunGraphNode:
    node = RunGraphNode(
        run_id=run_id,
        definition_task_id=definition_task_id,
        instance_key=instance_key,
        task_slug=task_slug,
        description=description,
        status=status,
        assigned_worker_slug=assigned_worker_slug,
    )
    session.add(node)
    session.flush()
    return node


def _patch_get_session(monkeypatch: pytest.MonkeyPatch, session: Session) -> None:
    """Monkeypatch get_session so the service uses the test transaction."""

    @contextmanager
    def _test_session():
        yield session

    monkeypatch.setattr(
        "ergon_core.core.runtime.services.task_execution_service.get_session",
        _test_session,
    )


# ---------------------------------------------------------------------------
# Graph-native path: happy path
# ---------------------------------------------------------------------------


class TestPrepareGraphNative:
    async def test_returns_correct_prepared_execution(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def_id, _, task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        _seed_worker(session, def_id, binding_key="researcher")
        node = _seed_graph_node(
            session,
            run_id,
            task_slug="research-topic",
            description="Research quantum computing",
            assigned_worker_slug="researcher",
        )

        _patch_get_session(monkeypatch, session)
        svc = TaskExecutionService()

        command = PrepareTaskExecutionCommand(
            run_id=run_id,
            definition_id=def_id,
            task_id=task_ids[0],
            node_id=node.id,
        )
        result = await svc.prepare(command)

        assert result.node_id == node.id
        assert result.task_slug == "research-topic"
        assert result.task_description == "Research quantum computing"
        assert result.worker_type == "cloud-llm"
        assert result.model_target == "gpt-4o"
        assert result.assigned_worker_slug == "researcher"
        assert result.execution_id is not None

    async def test_creates_execution_row_without_definition_task_id(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def_id, _, task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        _seed_worker(session, def_id)
        node = _seed_graph_node(session, run_id)

        _patch_get_session(monkeypatch, session)
        svc = TaskExecutionService()

        result = await svc.prepare(
            PrepareTaskExecutionCommand(
                run_id=run_id,
                definition_id=def_id,
                task_id=task_ids[0],
                node_id=node.id,
            )
        )

        execution = session.get(RunTaskExecution, result.execution_id)
        assert execution is not None
        assert execution.definition_task_id is None
        assert execution.node_id == node.id
        assert execution.status == TaskExecutionStatus.RUNNING

    async def test_marks_graph_node_running(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def_id, _, task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        _seed_worker(session, def_id)
        node = _seed_graph_node(session, run_id, status="pending")

        _patch_get_session(monkeypatch, session)
        svc = TaskExecutionService()

        await svc.prepare(
            PrepareTaskExecutionCommand(
                run_id=run_id,
                definition_id=def_id,
                task_id=task_ids[0],
                node_id=node.id,
            )
        )

        session.refresh(node)
        assert node.status == TaskExecutionStatus.RUNNING


# ---------------------------------------------------------------------------
# Graph-native path: error cases
# ---------------------------------------------------------------------------


class TestPrepareGraphNativeErrors:
    async def test_nonexistent_node_raises(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def_id, _, task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)

        _patch_get_session(monkeypatch, session)
        svc = TaskExecutionService()

        with pytest.raises(ConfigurationError, match="not found"):
            await svc.prepare(
                PrepareTaskExecutionCommand(
                    run_id=run_id,
                    definition_id=def_id,
                    task_id=task_ids[0],
                    node_id=uuid4(),
                )
            )

    async def test_no_assigned_worker_slug_raises(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def_id, _, task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        node = _seed_graph_node(session, run_id, assigned_worker_slug=None)

        _patch_get_session(monkeypatch, session)
        svc = TaskExecutionService()

        with pytest.raises(ConfigurationError, match="no assigned_worker_slug"):
            await svc.prepare(
                PrepareTaskExecutionCommand(
                    run_id=run_id,
                    definition_id=def_id,
                    task_id=task_ids[0],
                    node_id=node.id,
                )
            )

    async def test_no_matching_worker_raises(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def_id, _, task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        _seed_worker(session, def_id, binding_key="other-worker")
        node = _seed_graph_node(session, run_id, assigned_worker_slug="researcher")

        _patch_get_session(monkeypatch, session)
        svc = TaskExecutionService()

        with pytest.raises(ConfigurationError, match="No ExperimentDefinitionWorker"):
            await svc.prepare(
                PrepareTaskExecutionCommand(
                    run_id=run_id,
                    definition_id=def_id,
                    task_id=task_ids[0],
                    node_id=node.id,
                )
            )


# ---------------------------------------------------------------------------
# Definition path: happy path
# ---------------------------------------------------------------------------


class TestPrepareDefinition:
    async def test_returns_correct_prepared_execution(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def_id, inst_id, task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        _seed_worker(session, def_id, binding_key="researcher")

        session.add(
            ExperimentDefinitionTaskAssignment(
                experiment_definition_id=def_id,
                task_id=task_ids[0],
                worker_binding_key="researcher",
            )
        )

        # Create graph node so GraphNodeLookup can resolve
        node = _seed_graph_node(
            session,
            run_id,
            definition_task_id=task_ids[0],
            task_slug="task-0",
            assigned_worker_slug="researcher",
        )
        session.flush()

        _patch_get_session(monkeypatch, session)
        svc = TaskExecutionService()

        result = await svc.prepare(
            PrepareTaskExecutionCommand(
                run_id=run_id,
                definition_id=def_id,
                task_id=task_ids[0],
            )
        )

        assert result.task_slug == "task-0"
        assert result.task_description == "Test task 0"
        assert result.assigned_worker_slug == "researcher"
        assert result.worker_type == "cloud-llm"
        assert result.node_id == node.id
        assert result.execution_id is not None

    async def test_creates_execution_with_definition_task_id(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def_id, inst_id, task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        _seed_worker(session, def_id)

        session.add(
            ExperimentDefinitionTaskAssignment(
                experiment_definition_id=def_id,
                task_id=task_ids[0],
                worker_binding_key="researcher",
            )
        )
        _seed_graph_node(session, run_id, definition_task_id=task_ids[0], task_slug="task-0")
        session.flush()

        _patch_get_session(monkeypatch, session)
        svc = TaskExecutionService()

        result = await svc.prepare(
            PrepareTaskExecutionCommand(
                run_id=run_id,
                definition_id=def_id,
                task_id=task_ids[0],
            )
        )

        execution = session.get(RunTaskExecution, result.execution_id)
        assert execution is not None
        assert execution.definition_task_id == task_ids[0]
        assert execution.node_id is not None


# ---------------------------------------------------------------------------
# Attempt numbering
# ---------------------------------------------------------------------------


class TestAttemptNumbering:
    async def test_graph_native_increments_attempt(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def_id, _, task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        _seed_worker(session, def_id)
        node = _seed_graph_node(session, run_id)

        _patch_get_session(monkeypatch, session)
        svc = TaskExecutionService()

        command = PrepareTaskExecutionCommand(
            run_id=run_id,
            definition_id=def_id,
            task_id=task_ids[0],
            node_id=node.id,
        )

        r1 = await svc.prepare(command)
        exec1 = session.get(RunTaskExecution, r1.execution_id)
        assert exec1 is not None
        assert exec1.attempt_number == 1

        # Reset node status to allow a second prepare
        node.status = "pending"
        session.add(node)
        session.flush()

        r2 = await svc.prepare(command)
        exec2 = session.get(RunTaskExecution, r2.execution_id)
        assert exec2 is not None
        assert exec2.attempt_number == 2
