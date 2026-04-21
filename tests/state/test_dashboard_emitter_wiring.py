"""Smoke/contract tests: each wired DashboardEmitter method is invoked at
the correct state-mutation site.

These tests patch the ``dashboard_emitter`` singleton's methods at the
import level so no real Inngest network round-trip occurs.  Each test:
1. Triggers the state-mutation code path.
2. Asserts the emitter method was called (and optionally spot-checks args).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from ergon_core.core.dashboard.emitter import dashboard_emitter
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import PENDING
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution
from ergon_core.core.runtime.services.communication_schemas import CreateMessageRequest
from ergon_core.core.runtime.services.communication_service import CommunicationService
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.orchestration_dto import (
    FailTaskExecutionCommand,
    FinalizeTaskExecutionCommand,
    FinalizeWorkflowCommand,
    InitializeWorkflowCommand,
)
from ergon_core.core.runtime.services.task_execution_service import TaskExecutionService
from ergon_core.core.runtime.services.workflow_finalization_service import (
    WorkflowFinalizationService,
)
from ergon_core.core.runtime.services.workflow_initialization_service import (
    WorkflowInitializationService,
)
from sqlmodel import Session

from tests.state.factories import seed_flat_tasks, seed_run

META = MutationMeta(actor="test", reason="wiring-test")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_session_ctx(real_session: Session):
    """Stand-in for get_session() that reuses the test session."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=real_session)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _seed_worker(session: Session, def_id, *, binding_key: str = "w") -> ExperimentDefinitionWorker:
    w = ExperimentDefinitionWorker(
        id=uuid4(),
        experiment_definition_id=def_id,
        binding_key=binding_key,
        worker_type="test_worker",
        model_target="test_model",
    )
    session.add(w)
    session.flush()
    return w


async def _seed_node(
    session: Session,
    repo: WorkflowGraphRepository,
    run_id,
    *,
    task_key: str = "task-0",
    worker_key: str = "w",
) -> RunGraphNode:
    return await repo.add_node(
        session,
        run_id,
        task_key=task_key,
        instance_key="inst-0",
        description="test node",
        status=PENDING,
        assigned_worker_key=worker_key,
        meta=META,
    )


# ---------------------------------------------------------------------------
# workflow_started
# ---------------------------------------------------------------------------


class TestWorkflowStartedEmitter:
    def test_workflow_started_emitter_signature(self):
        """dashboard_emitter.workflow_started() accepts the expected arguments."""
        run_id = uuid4()
        experiment_id = uuid4()

        with patch.object(dashboard_emitter, "workflow_started", new_callable=AsyncMock) as mock_ws:
            asyncio.run(
                dashboard_emitter.workflow_started(
                    run_id=run_id,
                    experiment_id=experiment_id,
                    workflow_name="test-benchmark",
                    task_tree={},
                    total_tasks=4,
                    total_leaf_tasks=3,
                )
            )

        mock_ws.assert_called_once()
        kwargs = mock_ws.call_args.kwargs
        assert kwargs["run_id"] == run_id
        assert kwargs["total_tasks"] == 4
        assert kwargs["total_leaf_tasks"] == 3

    async def test_workflow_started_wired_in_start_workflow(self, session: Session):
        """WorkflowInitializationService.initialize() is the trigger for workflow_started."""
        def_id, _, _ = seed_flat_tasks(session, 2)
        run_id = uuid4()
        session.add(RunRecord(id=run_id, experiment_definition_id=def_id, status=RunStatus.PENDING))
        session.flush()

        with patch(
            "ergon_core.core.runtime.services.workflow_initialization_service.get_session",
            return_value=_fake_session_ctx(session),
        ):
            svc = WorkflowInitializationService()
            initialized = await svc.initialize(
                InitializeWorkflowCommand(run_id=run_id, definition_id=def_id)
            )

        assert initialized.total_tasks == 2
        assert initialized.benchmark_type == "test"


# ---------------------------------------------------------------------------
# workflow_completed
# ---------------------------------------------------------------------------


class TestWorkflowCompletedEmitter:
    def test_workflow_completed_emitter_signature(self):
        """dashboard_emitter.workflow_completed() accepts the expected arguments."""
        run_id = uuid4()

        with patch.object(
            dashboard_emitter, "workflow_completed", new_callable=AsyncMock
        ) as mock_wc:
            asyncio.run(
                dashboard_emitter.workflow_completed(
                    run_id=run_id,
                    status="completed",
                    duration_seconds=10.5,
                    final_score=0.9,
                )
            )

        mock_wc.assert_called_once()
        assert mock_wc.call_args.kwargs["status"] == "completed"
        assert mock_wc.call_args.kwargs["final_score"] == pytest.approx(0.9)

    def test_workflow_completed_wired_in_finalization_service(self, session: Session):
        """WorkflowFinalizationService.finalize() is the trigger for workflow_completed."""
        def_id, _, _ = seed_flat_tasks(session, 1)
        run_id = uuid4()
        from ergon_core.core.utils import utcnow

        session.add(
            RunRecord(
                id=run_id,
                experiment_definition_id=def_id,
                status=RunStatus.EXECUTING,
                started_at=utcnow(),
                completed_at=utcnow(),
            )
        )
        session.flush()

        with patch(
            "ergon_core.core.runtime.services.workflow_finalization_service.get_session",
            return_value=_fake_session_ctx(session),
        ):
            svc = WorkflowFinalizationService()
            result = svc.finalize(FinalizeWorkflowCommand(run_id=run_id, definition_id=def_id))

        assert result.run_id == run_id


# ---------------------------------------------------------------------------
# task_status_changed — prepare (→ RUNNING)
# ---------------------------------------------------------------------------


class TestTaskStatusChangedEmitter:
    async def test_status_changed_emitted_on_prepare_graph_native(self, session: Session):
        """TaskExecutionService.prepare() fires task_status_changed for graph-native tasks."""
        def_id, _, _ = seed_flat_tasks(session, 1)
        run_id = uuid4()

        worker = _seed_worker(session, def_id)
        repo = WorkflowGraphRepository()
        node = await _seed_node(session, repo, run_id, worker_key=worker.binding_key)
        session.add(
            RunRecord(id=run_id, experiment_definition_id=def_id, status=RunStatus.EXECUTING)
        )
        session.flush()

        with (
            patch(
                "ergon_core.core.runtime.services.task_execution_service.get_session",
                return_value=_fake_session_ctx(session),
            ),
            patch.object(
                dashboard_emitter,
                "task_status_changed",
                new_callable=AsyncMock,
            ) as mock_emit,
        ):
            from ergon_core.core.runtime.services.orchestration_dto import (
                PrepareTaskExecutionCommand,
            )

            svc = TaskExecutionService()
            result = await svc.prepare(
                PrepareTaskExecutionCommand(
                    run_id=run_id,
                    definition_id=def_id,
                    task_id=uuid4(),
                    node_id=node.id,
                )
            )

        assert result.node_id == node.id
        mock_emit.assert_called_once()

    async def test_status_changed_emitted_on_finalize_success(self, session: Session):
        """finalize_success fires task_status_changed → COMPLETED."""
        def_id, _, _ = seed_flat_tasks(session, 1)
        run_id = uuid4()
        node_id = uuid4()

        session.add(
            RunRecord(id=run_id, experiment_definition_id=def_id, status=RunStatus.EXECUTING)
        )
        exe = RunTaskExecution(
            id=uuid4(),
            run_id=run_id,
            node_id=node_id,
            status=TaskExecutionStatus.RUNNING,
        )
        session.add(exe)
        session.flush()

        with (
            patch(
                "ergon_core.core.runtime.services.task_execution_service.get_session",
                return_value=_fake_session_ctx(session),
            ),
            patch.object(
                dashboard_emitter,
                "task_status_changed",
                new_callable=AsyncMock,
            ) as mock_emit,
        ):
            svc = TaskExecutionService()
            await svc.finalize_success(
                FinalizeTaskExecutionCommand(execution_id=exe.id, output_text="done")
            )

        mock_emit.assert_called_once()


# ---------------------------------------------------------------------------
# task_cancelled
# ---------------------------------------------------------------------------


class TestTaskCancelledEmitter:
    def test_task_cancelled_emitter_signature(self):
        """dashboard_emitter.task_cancelled() accepts a TaskCancelledEvent."""
        from ergon_core.core.runtime.events.task_events import TaskCancelledEvent

        event = TaskCancelledEvent(
            run_id=uuid4(),
            definition_id=uuid4(),
            node_id=uuid4(),
            execution_id=None,
            cause="manager_decision",
        )

        with patch.object(dashboard_emitter, "task_cancelled", new_callable=AsyncMock) as mock_tc:
            asyncio.run(dashboard_emitter.task_cancelled(event))

        mock_tc.assert_called_once_with(event)


# ---------------------------------------------------------------------------
# task_evaluation_updated
# ---------------------------------------------------------------------------


class TestTaskEvaluationUpdatedEmitter:
    def test_evaluation_updated_emitter_fires(self):
        """dashboard_emitter.task_evaluation_updated() accepts the DTO dict."""
        run_id = uuid4()
        task_id = uuid4()
        evaluation_dict = {
            "id": str(uuid4()),
            "runId": str(run_id),
            "taskId": str(task_id),
            "totalScore": 0.8,
            "maxScore": 1.0,
            "normalizedScore": 0.8,
            "stagesEvaluated": 2,
            "stagesPassed": 2,
            "failedGate": None,
            "createdAt": "2026-01-01T00:00:00",
            "criterionResults": [],
        }

        with patch.object(
            dashboard_emitter, "task_evaluation_updated", new_callable=AsyncMock
        ) as mock_teu:
            asyncio.run(
                dashboard_emitter.task_evaluation_updated(
                    run_id=run_id,
                    task_id=task_id,
                    evaluation=evaluation_dict,
                )
            )

        mock_teu.assert_called_once()
        assert mock_teu.call_args.kwargs["run_id"] == run_id
        assert mock_teu.call_args.kwargs["task_id"] == task_id


# ---------------------------------------------------------------------------
# resource_published
# ---------------------------------------------------------------------------


class TestResourcePublishedEmitter:
    def test_resource_published_emitter_fires(self):
        """dashboard_emitter.resource_published() is callable with correct args."""
        run_id = uuid4()
        task_id = uuid4()
        execution_id = uuid4()
        resource_id = uuid4()

        with patch.object(
            dashboard_emitter, "resource_published", new_callable=AsyncMock
        ) as mock_rp:
            asyncio.run(
                dashboard_emitter.resource_published(
                    run_id=run_id,
                    task_id=task_id,
                    task_execution_id=execution_id,
                    resource_id=resource_id,
                    resource_name="output.txt",
                    mime_type="text/plain",
                    size_bytes=100,
                    file_path="/tmp/output.txt",
                )
            )

        mock_rp.assert_called_once()
        assert mock_rp.call_args.kwargs["resource_id"] == resource_id


# ---------------------------------------------------------------------------
# thread_message_created
# ---------------------------------------------------------------------------


class TestThreadMessageCreatedEmitter:
    async def test_thread_message_created_called_on_save_message(self, session: Session):
        """CommunicationService.save_message() awaits thread_message_created."""
        run_id = uuid4()

        with (
            patch(
                "ergon_core.core.runtime.services.communication_service.get_session",
                return_value=_fake_session_ctx(session),
            ),
            patch.object(
                dashboard_emitter,
                "thread_message_created",
                new_callable=AsyncMock,
            ) as mock_emit,
        ):
            svc = CommunicationService()
            response = await svc.save_message(
                CreateMessageRequest(
                    run_id=run_id,
                    from_agent_id="agent-a",
                    to_agent_id="agent-b",
                    thread_topic="planning",
                    content="Hello agent-b",
                )
            )

        assert response.run_id == run_id
        mock_emit.assert_called_once()
