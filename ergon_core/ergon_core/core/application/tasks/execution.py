"""Task execution lifecycle: prepare, finalize success, finalize failure."""

import logging
from uuid import UUID

from ergon_core.core.infrastructure.dashboard.provider import get_dashboard_emitter
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.graph import status_conventions as graph_status
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution
from ergon_core.core.infrastructure.inngest.errors import ConfigurationError
from ergon_core.core.application.graph.models import MutationMeta
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.application.workflows.orchestration import (
    FailTaskExecutionCommand,
    FinalizeTaskExecutionCommand,
    PreparedTaskExecution,
    PrepareTaskExecutionCommand,
)
from ergon_core.core.application.graph.propagation import (
    mark_task_failed_by_node,
)
from ergon_core.core.application.tasks.repository import TaskExecutionRepository
from ergon_core.core.shared.utils import require_not_none, utcnow
from sqlmodel import Session, select

logger = logging.getLogger(__name__)


async def _emit_task_status(
    run_id: UUID,
    node_id: UUID | None,
    task_slug: str,
    new_status: str,
    old_status: str | None = None,
    worker_id: UUID | None = None,
    worker_slug: str | None = None,
) -> None:
    """Emit dashboard/task.status_changed. All arguments are plain primitives."""
    if node_id is None:
        return
    try:
        await get_dashboard_emitter().task_status_changed(
            run_id=run_id,
            task_id=node_id,
            task_name=task_slug,
            new_status=new_status,
            old_status=old_status,
            assigned_worker_id=worker_id,
            assigned_worker_slug=worker_slug,
        )
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.warning("Failed to emit task_status_changed", exc_info=True)


class TaskExecutionService:
    def __init__(self) -> None:
        self._graph_repo = WorkflowGraphRepository()
        self._task_execution_repo = TaskExecutionRepository()

    async def prepare(self, command: PrepareTaskExecutionCommand) -> PreparedTaskExecution:
        return await self._prepare_run_node(command)

    # -- Unified run-tier path (PR 3) ---
    #
    # Reads the run-tier task snapshot via `graph_repo.node(...)`
        # instead of branching on static vs dynamic. `task_id` is the
        # run graph node id after PR 11.

    async def _prepare_run_node(
        self, command: PrepareTaskExecutionCommand
    ) -> PreparedTaskExecution:
        lookup_id = command.node_id or command.task_id
        if lookup_id is None:
            raise ConfigurationError(
                "Task preparation requires node_id or task_id",
                run_id=command.run_id,
                task_id=None,
            )
        with get_session() as session:
            view = await self._graph_repo.node(session, run_id=command.run_id, task_id=lookup_id)
            node = session.get(RunGraphNode, view.task_id)
            if node is None:
                raise ConfigurationError(
                    f"RunGraphNode {view.task_id} not found",
                    run_id=command.run_id,
                    task_id=lookup_id,
                )
            definition = require_not_none(
                session.get(ExperimentDefinition, command.definition_id),
                f"Definition {command.definition_id} not found",
            )

            # TODO(PR 11): bridge metadata only; runtime worker selection
            # no longer depends on these fields for object-bound tasks.
            assigned_worker_slug = node.assigned_worker_slug
            worker_type, model_target, definition_worker_id = self._resolve_worker_config(
                session,
                definition_id=command.definition_id,
                run_id=command.run_id,
                assigned_worker_slug=assigned_worker_slug,
            )

            execution = RunTaskExecution(
                run_id=command.run_id,
                task_id=view.task_id,
                node_id=view.task_id,
                definition_worker_id=definition_worker_id,
                attempt_number=self._task_execution_repo.next_attempt_for_node(
                    session, command.run_id, view.task_id
                ),
                status=TaskExecutionStatus.RUNNING,
                started_at=utcnow(),
            )
            session.add(execution)
            session.flush()
            # Snapshot ORM-derived scalars before commit. SQLAlchemy's
            # `expire_on_commit=True` default expires every loaded
            # instance on commit, and `with get_session() as session:`
            # closes the session immediately after — so the post-commit
            # reads of `definition.benchmark_type` / `execution.id`
            # below would raise DetachedInstanceError.
            benchmark_type = definition.benchmark_type
            execution_id = execution.id
            await self._graph_repo.update_node_status(
                session,
                run_id=command.run_id,
                node_id=view.task_id,
                new_status=graph_status.RUNNING,
                meta=MutationMeta(
                    actor="task-execution-service",
                    reason=f"prepare: execution {execution_id}",
                ),
            )
            session.commit()

        await _emit_task_status(
            run_id=command.run_id,
            node_id=view.task_id,
            task_slug=view.task.task_slug,
            new_status=graph_status.RUNNING,
            old_status=None,
            worker_id=definition_worker_id,
            worker_slug=assigned_worker_slug,
        )
        return PreparedTaskExecution(
            run_id=command.run_id,
            definition_id=command.definition_id,
            task_id=view.task_id,
            task_slug=view.task.task_slug,
            task_description=view.task.description,
            benchmark_type=benchmark_type,
            assigned_worker_slug=assigned_worker_slug,
            worker_type=worker_type,
            model_target=model_target,
            execution_id=execution_id,
        )

    def _resolve_worker_config(
        self,
        session: Session,
        *,
        definition_id: UUID,
        run_id: UUID,
        assigned_worker_slug: str | None,
    ) -> tuple[str | None, str | None, UUID | None]:
        """Resolve (worker_type, model_target, definition_worker_id) for a
        given assigned_worker_slug.

        Falls back to the run's default model_target when no
        ExperimentDefinitionWorker row matches the binding key (matches
        legacy graph-native behavior for dynamically-assigned workers).

        TODO(PR 11): obsoleted by `task.worker` carrying the config
        directly for object-bound snapshots; this helper survives only
        to populate bridge metadata and legacy DTO fields.
        """

        if assigned_worker_slug is None:
            return None, None, None
        worker_row = session.exec(
            select(ExperimentDefinitionWorker).where(
                ExperimentDefinitionWorker.experiment_definition_id == definition_id,
                ExperimentDefinitionWorker.binding_key == assigned_worker_slug,
            )
        ).first()
        if worker_row is not None:
            return worker_row.worker_type, worker_row.model_target, worker_row.id
        # No matching binding — use the run-level default model_target.
        run = session.get(RunRecord, run_id)
        model_target = run.model_target if run is not None else None
        return assigned_worker_slug, model_target, None

    async def finalize_success(self, command: FinalizeTaskExecutionCommand) -> None:
        with get_session() as session:
            execution = require_not_none(
                session.get(RunTaskExecution, command.execution_id),
                f"RunTaskExecution {command.execution_id} not found",
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
                run_id=execution.run_id,
                node_id=execution.task_id,
                task_slug=str(execution.task_id or ""),
                new_status=graph_status.COMPLETED,
                old_status=graph_status.RUNNING,
            )

    async def finalize_failure(self, command: FailTaskExecutionCommand) -> None:
        with get_session() as session:
            execution = require_not_none(
                session.get(RunTaskExecution, command.execution_id),
                f"RunTaskExecution {command.execution_id} not found",
            )
            execution.status = TaskExecutionStatus.FAILED
            execution.completed_at = utcnow()
            execution.error_json = command.error_json or {"message": command.error_message}
            session.add(execution)

            graph_repo = WorkflowGraphRepository()
            if execution.task_id is not None:
                await mark_task_failed_by_node(
                    session,
                    command.run_id,
                    execution.task_id,
                    command.error_message,
                    execution_id=command.execution_id,
                    graph_repo=graph_repo,
                )
            session.commit()

            await _emit_task_status(
                run_id=command.run_id,
                node_id=execution.task_id,
                task_slug=str(execution.task_id or ""),
                new_status=graph_status.FAILED,
                old_status=graph_status.RUNNING,
            )
