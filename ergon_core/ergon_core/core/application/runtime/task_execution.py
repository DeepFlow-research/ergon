"""Task execution lifecycle: prepare, finalize success, finalize failure."""

import logging
from uuid import UUID

from ergon_core.api.task import Task
from ergon_core.core.application.events.service import get_dashboard_event_publisher
from ergon_core.core.application.runtime import status as graph_status
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord, SampleTaskAttempt
from ergon_core.core.infrastructure.inngest.errors import ConfigurationError
from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.application.runtime.models import MutationMeta, SampleGraphNodeView
from ergon_core.core.application.runtime.graph_repository import RuntimeGraphRepository
from ergon_core.core.application.runtime.orchestration import (
    FailTaskExecutionCommand,
    FinalizeTaskExecutionCommand,
    PreparedTaskExecution,
    PrepareTaskExecutionCommand,
)
from ergon_core.core.application.runtime.lifecycle import (
    mark_task_failed_by_node,
)
from ergon_core.core.application.runtime.task_execution_repository import (
    TaskExecutionRepository,
    WorkerOutputRepository,
)
from ergon_core.core.shared.utils import require_not_none, utcnow
from ergon_core.core.views.dashboard_events.contracts import DashboardTaskStatusChangedEvent
from sqlmodel import Session

logger = logging.getLogger(__name__)


async def _emit_task_status(
    sample_id: UUID,
    task_id: UUID | None,
    task_slug: str,
    new_status: str,
    old_status: str | None = None,
    worker_id: UUID | None = None,
    worker_slug: str | None = None,
) -> None:
    """Emit dashboard/task.status_changed. All arguments are plain primitives."""
    if task_id is None:
        return
    try:
        await get_dashboard_event_publisher().publish(
            DashboardTaskStatusChangedEvent(
                sample_id=sample_id,
                task_id=task_id,
                task_name=task_slug,
                new_status=new_status,
                old_status=old_status,
                timestamp=utcnow(),
                assigned_worker_id=worker_id,
                assigned_worker_slug=worker_slug,
            )
        )
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.warning("Failed to emit task_status_changed", exc_info=True)


class TaskExecutionService:
    """Public facade for task execution reads and execution-row writes.

    Jobs use this boundary for task view hydration, worker output persistence,
    and sandbox identity stamping instead of importing runtime repositories.
    """

    def __init__(
        self,
        *,
        graph_repo: RuntimeGraphRepository | None = None,
        task_execution_repo: TaskExecutionRepository | None = None,
        worker_output_repo: WorkerOutputRepository | None = None,
    ) -> None:
        self._graph_repo = graph_repo or RuntimeGraphRepository()
        self._task_execution_repo = task_execution_repo or TaskExecutionRepository()
        self._worker_output_repo = worker_output_repo or WorkerOutputRepository()

    async def load_task_view(
        self,
        session: Session,
        *,
        sample_id: UUID,
        task_id: UUID,
        sandbox_id: str | None = None,
    ) -> SampleGraphNodeView:
        """Load the object-bound runtime task view by public task_id."""
        return await self._graph_repo.node(
            session,
            sample_id=sample_id,
            task_id=task_id,
            sandbox_id=sandbox_id,
        )

    async def persist_worker_output(
        self,
        session: Session,
        *,
        execution_id: UUID,
        output: WorkerOutput,
    ) -> None:
        """Persist terminal worker output for evaluator fanout."""
        await self._worker_output_repo.persist(
            session,
            execution_id=execution_id,
            output=output,
        )

    async def load_worker_output(
        self,
        session: Session,
        *,
        execution_id: UUID,
    ) -> WorkerOutput:
        """Load worker output persisted for an execution."""
        return await self._worker_output_repo.load(session, execution_id=execution_id)

    async def attach_sandbox_to_execution(
        self,
        session: Session,
        *,
        execution_id: UUID,
        sandbox_id: str,
    ) -> None:
        """Stamp the live sandbox id on an execution row."""
        await self._task_execution_repo.set_sandbox_id(
            session,
            execution_id=execution_id,
            sandbox_id=sandbox_id,
        )

    async def prepare(self, command: PrepareTaskExecutionCommand) -> PreparedTaskExecution:
        return await self._prepare_run_node(command)

    async def _prepare_run_node(
        self, command: PrepareTaskExecutionCommand
    ) -> PreparedTaskExecution:
        lookup_id = command.task_id
        with get_session() as session:
            view = await self._graph_repo.node(
                session, sample_id=command.sample_id, task_id=lookup_id
            )
            node = session.get(SampleGraphNode, (command.sample_id, view.task_id))
            if node is None:
                raise ConfigurationError(
                    f"SampleGraphNode {view.task_id} not found",
                    sample_id=command.sample_id,
                    task_id=lookup_id,
                )
            assigned_worker_slug = node.assigned_worker_slug
            run_record = require_not_none(
                session.get(SampleRecord, command.sample_id),
                f"SampleRecord {command.sample_id} not found",
            )
            worker_type, model_target = await _resolve_sample_worker_config(
                node.task_json,
                task_id=view.task_id,
                assigned_worker_slug=assigned_worker_slug,
            )
            benchmark_type = run_record.benchmark_type

            execution = SampleTaskAttempt(
                sample_id=command.sample_id,
                task_id=view.task_id,
                status=TaskExecutionStatus.RUNNING,
                started_at=utcnow(),
            )
            session.add(execution)
            session.flush()
            # Snapshot ORM-derived scalars before commit. SQLAlchemy's
            # `expire_on_commit=True` default expires every loaded
            # instance on commit, and `with get_session() as session:`
            # closes the session immediately after.
            execution_id = execution.id
            await self._graph_repo.update_node_status(
                session,
                sample_id=command.sample_id,
                task_id=view.task_id,
                new_status=graph_status.RUNNING,
                meta=MutationMeta(
                    actor="task-execution-service",
                    reason=f"prepare: execution {execution_id}",
                ),
            )
            session.commit()

        await _emit_task_status(
            sample_id=command.sample_id,
            task_id=view.task_id,
            task_slug=view.task.task_slug,
            new_status=graph_status.RUNNING,
            old_status=None,
            worker_slug=assigned_worker_slug,
        )
        return PreparedTaskExecution(
            sample_id=command.sample_id,
            task_id=view.task_id,
            task_slug=view.task.task_slug,
            task_description=view.task.description,
            benchmark_type=benchmark_type,
            assigned_worker_slug=assigned_worker_slug,
            worker_type=worker_type,
            model_target=model_target,
            execution_id=execution_id,
        )

    async def finalize_success(self, command: FinalizeTaskExecutionCommand) -> None:
        with get_session() as session:
            execution = require_not_none(
                session.get(SampleTaskAttempt, command.execution_id),
                f"SampleTaskAttempt {command.execution_id} not found",
            )
            execution.status = TaskExecutionStatus.COMPLETED
            execution.completed_at = utcnow()
            execution.final_assistant_message = command.final_assistant_message
            if command.output_resource_ids:
                execution.output_json = {
                    "resource_ids": [str(rid) for rid in command.output_resource_ids],
                }
            session.add(execution)
            session.commit()

            await _emit_task_status(
                sample_id=execution.sample_id,
                task_id=execution.task_id,
                task_slug=str(execution.task_id or ""),
                new_status=graph_status.COMPLETED,
                old_status=graph_status.RUNNING,
            )

    async def finalize_failure(self, command: FailTaskExecutionCommand) -> None:
        with get_session() as session:
            execution = require_not_none(
                session.get(SampleTaskAttempt, command.execution_id),
                f"SampleTaskAttempt {command.execution_id} not found",
            )
            execution.status = TaskExecutionStatus.FAILED
            execution.completed_at = utcnow()
            execution.error_json = command.error_json or {"message": command.error_message}
            session.add(execution)

            graph_repo = RuntimeGraphRepository()
            if execution.task_id is not None:
                await mark_task_failed_by_node(
                    session,
                    command.sample_id,
                    execution.task_id,
                    command.error_message,
                    execution_id=command.execution_id,
                    graph_repo=graph_repo,
                )
            session.commit()

            await _emit_task_status(
                sample_id=command.sample_id,
                task_id=execution.task_id,
                task_slug=str(execution.task_id or ""),
                new_status=graph_status.FAILED,
                old_status=graph_status.RUNNING,
            )


async def _resolve_sample_worker_config(
    task_json: dict,
    *,
    task_id: UUID,
    assigned_worker_slug: str | None,
) -> tuple[str, str]:
    task = await Task.from_definition(task_json, task_id=task_id)
    return assigned_worker_slug or task.worker.type_slug, task.worker.model
