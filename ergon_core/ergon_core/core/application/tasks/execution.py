"""Task execution lifecycle: prepare, finalize success, finalize failure."""

import logging
from uuid import UUID

from ergon_core.core.infrastructure.dashboard.provider import get_dashboard_emitter
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.graph import status_conventions as graph_status
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution
from ergon_core.core.infrastructure.inngest.errors import ConfigurationError
from ergon_core.core.application.graph.models import MutationMeta
from ergon_core.core.application.graph.lookup import GraphNodeLookup
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.application.workflows.orchestration import (
    FailTaskExecutionCommand,
    FinalizeTaskExecutionCommand,
    PreparedTaskExecution,
    PrepareTaskExecutionCommand,
)
from ergon_core.core.application.graph.propagation import (
    mark_task_failed,
    mark_task_failed_by_node,
    mark_task_running,
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
    # instead of branching on static vs dynamic. The view's OR
    # predicate handles both: `command.node_id` (graph-native dynamic)
    # OR `command.task_id` (definition FK) resolves to the same
    # RunGraphNode row.
    #
    # TODO(PR 5): `worker_type` / `model_target` come from
    # `task.worker` once Worker is Pydantic-serializable; drop the
    # ExperimentDefinitionWorker lookup below.
    # TODO(PR 11): drop `_prepare_legacy_graph_native` /
    # `_prepare_legacy_definition` along with the legacy DTO fields.

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
            node = session.get(RunGraphNode, view.node_id)
            if node is None:
                raise ConfigurationError(
                    f"RunGraphNode {view.node_id} not found",
                    run_id=command.run_id,
                    task_id=lookup_id,
                )
            definition = require_not_none(
                session.get(ExperimentDefinition, command.definition_id),
                f"Definition {command.definition_id} not found",
            )

            # TODO(PR 5): `worker_type` / `model_target` come from
            # `task.worker` once Worker is Pydantic-serializable.
            assigned_worker_slug = node.assigned_worker_slug
            worker_type, model_target, definition_worker_id = self._resolve_worker_config(
                session,
                definition_id=command.definition_id,
                run_id=command.run_id,
                assigned_worker_slug=assigned_worker_slug,
            )

            execution = RunTaskExecution(
                run_id=command.run_id,
                node_id=view.node_id,
                definition_task_id=view.definition_task_id,
                definition_worker_id=definition_worker_id,
                attempt_number=self._task_execution_repo.next_attempt_for_node(
                    session, command.run_id, view.node_id
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
                node_id=view.node_id,
                new_status=graph_status.RUNNING,
                meta=MutationMeta(
                    actor="task-execution-service",
                    reason=f"prepare: execution {execution_id}",
                ),
            )
            session.commit()

        await _emit_task_status(
            run_id=command.run_id,
            node_id=view.node_id,
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
            node_id=view.node_id,
            definition_task_id=view.definition_task_id,
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

        TODO(PR 5): obsoleted by `task.worker` carrying the config
        directly; this whole helper goes away with the legacy DTO
        fields.
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

    # -- Legacy graph-native path (PR 3 — kept for rollback, unused) ---
    # TODO(PR 11): delete `_prepare_legacy_graph_native`.

    async def _prepare_legacy_graph_native(
        self, command: PrepareTaskExecutionCommand
    ) -> PreparedTaskExecution:
        node_id = command.node_id
        if node_id is None:
            raise ConfigurationError(
                "Graph-native preparation requires node_id",
                run_id=command.run_id,
                task_id=command.task_id,
            )
        with get_session() as session:
            node = session.get(RunGraphNode, node_id)
            if node is None:
                raise ConfigurationError(
                    f"RunGraphNode {node_id} not found",
                    run_id=command.run_id,
                    task_id=command.task_id,
                )
            if node.run_id != command.run_id:
                raise ConfigurationError(
                    f"RunGraphNode {node_id} belongs to run {node.run_id}, not {command.run_id}",
                    run_id=command.run_id,
                    task_id=command.task_id,
                )

            assigned_worker_slug = node.assigned_worker_slug
            if assigned_worker_slug is None:
                raise ConfigurationError(
                    f"RunGraphNode {node_id} has no assigned_worker_slug",
                    run_id=command.run_id,
                    task_id=command.task_id,
                )

            worker_row = session.exec(
                select(ExperimentDefinitionWorker).where(
                    ExperimentDefinitionWorker.experiment_definition_id == command.definition_id,
                    ExperimentDefinitionWorker.binding_key == assigned_worker_slug,
                )
            ).first()
            run = session.get(RunRecord, command.run_id)
            if worker_row is None:
                if run is None:
                    raise ConfigurationError(
                        f"RunRecord {command.run_id} not found",
                        run_id=command.run_id,
                        task_id=command.task_id,
                    )
                definition_worker_id = None
                worker_type = assigned_worker_slug
                model_target = run.model_target
            else:
                definition_worker_id = worker_row.id
                worker_type = worker_row.worker_type
                model_target = worker_row.model_target

            definition = require_not_none(
                session.get(ExperimentDefinition, command.definition_id),
                f"Definition {command.definition_id} not found",
            )

            execution = RunTaskExecution(
                run_id=command.run_id,
                node_id=node_id,
                definition_worker_id=definition_worker_id,
                attempt_number=self._task_execution_repo.next_attempt_for_node(
                    session, command.run_id, node_id
                ),
                status=TaskExecutionStatus.RUNNING,
                started_at=utcnow(),
            )
            session.add(execution)
            session.flush()

            await self._graph_repo.update_node_status(
                session,
                run_id=command.run_id,
                node_id=node_id,
                new_status=graph_status.RUNNING,
                meta=MutationMeta(
                    actor="task-execution-service",
                    reason=f"prepare: execution {execution.id}",
                ),
            )
            session.commit()

            await _emit_task_status(
                run_id=command.run_id,
                node_id=node_id,
                task_slug=node.task_slug,
                new_status=graph_status.RUNNING,
                old_status=None,
                worker_id=definition_worker_id,
                worker_slug=assigned_worker_slug,
            )

            # Graph-native path: ``command.node_id`` is guaranteed non-null
            # by the branch guard in ``prepare`` above.  ``command.task_id``
            # is the legacy definition FK — may be ``None`` for
            # dynamically-spawned subtasks that have no definition row.
            return PreparedTaskExecution(
                run_id=command.run_id,
                definition_id=command.definition_id,
                task_id=command.task_id or node_id,
                node_id=node_id,
                definition_task_id=command.task_id,
                task_slug=node.task_slug,
                task_description=node.description,
                benchmark_type=definition.benchmark_type,
                assigned_worker_slug=assigned_worker_slug,
                worker_type=worker_type,
                model_target=model_target,
                execution_id=execution.id,
            )

    # -- Legacy definition path (PR 3 — renamed, kept for rollback) ---
    # TODO(PR 11): delete `_prepare_legacy_definition`.

    async def _prepare_legacy_definition(
        self, command: PrepareTaskExecutionCommand
    ) -> PreparedTaskExecution:
        task_id = command.task_id
        if task_id is None:
            raise ConfigurationError(
                "Definition preparation requires task_id",
                run_id=command.run_id,
                task_id=None,
            )
        with get_session() as session:
            task = require_not_none(
                session.get(ExperimentDefinitionTask, task_id),
                f"Task {task_id} not found",
            )

            definition = require_not_none(
                session.get(ExperimentDefinition, command.definition_id),
                f"Definition {command.definition_id} not found",
            )

            assignment_stmt = select(ExperimentDefinitionTaskAssignment).where(
                ExperimentDefinitionTaskAssignment.experiment_definition_id
                == command.definition_id,
                ExperimentDefinitionTaskAssignment.task_id == task_id,
            )
            assignment = session.exec(assignment_stmt).first()

            definition_worker_id: UUID | None = None

            if assignment is None:
                raise ConfigurationError(
                    f"Definition task {task_id} has no worker assignment",
                    run_id=command.run_id,
                    task_id=task_id,
                )

            assigned_worker_slug = assignment.worker_binding_key
            worker_stmt = select(ExperimentDefinitionWorker).where(
                ExperimentDefinitionWorker.experiment_definition_id == command.definition_id,
                ExperimentDefinitionWorker.binding_key == assignment.worker_binding_key,
            )
            worker = session.exec(worker_stmt).first()
            if worker is None:
                raise ConfigurationError(
                    f"No ExperimentDefinitionWorker with binding_key="
                    f"'{assigned_worker_slug}' for definition {command.definition_id}",
                    run_id=command.run_id,
                    task_id=task_id,
                )
            worker_type = worker.worker_type
            model_target = worker.model_target
            definition_worker_id = worker.id

            graph_lookup = GraphNodeLookup(session, command.run_id)
            resolved_node_id = graph_lookup.node_id(task_id)
            # Workflow initialization creates a RunGraphNode per static
            # definition task; a missing node here means the graph was
            # never initialised or the static FK is stale.  Fail loud
            # rather than propagate a ``None`` through PreparedTaskExecution.
            if resolved_node_id is None:
                raise ConfigurationError(
                    f"No RunGraphNode resolved for definition task_id="
                    f"{task_id} in run {command.run_id}",
                    run_id=command.run_id,
                    task_id=task_id,
                )

            execution = RunTaskExecution(
                run_id=command.run_id,
                definition_task_id=task_id,
                definition_worker_id=definition_worker_id,
                node_id=resolved_node_id,
                attempt_number=self._task_execution_repo.next_attempt_for_definition_task(
                    session, command.run_id, task_id
                ),
                status=TaskExecutionStatus.RUNNING,
                started_at=utcnow(),
            )
            session.add(execution)
            session.flush()

            await mark_task_running(
                session,
                command.run_id,
                task_id,
                execution.id,
                graph_repo=self._graph_repo,
                graph_lookup=graph_lookup,
            )
            session.commit()

            await _emit_task_status(
                run_id=command.run_id,
                node_id=resolved_node_id,
                task_slug=task.task_slug,
                new_status=graph_status.RUNNING,
                old_status=None,
                worker_id=definition_worker_id,
                worker_slug=assigned_worker_slug,
            )

            # Definition path: ``command.task_id`` is the static FK (known
            # non-null by the branch guard in ``prepare``) and doubles as
            # the runtime identity since, for static tasks, ``node_id``
            # resolves 1:1 from the FK via ``graph_lookup.node_id()``.
            return PreparedTaskExecution(
                run_id=command.run_id,
                definition_id=command.definition_id,
                task_id=task_id,
                node_id=resolved_node_id,
                definition_task_id=task_id,
                task_slug=task.task_slug,
                task_description=task.description,
                benchmark_type=definition.benchmark_type,
                assigned_worker_slug=assigned_worker_slug,
                worker_type=worker_type,
                model_target=model_target,
                execution_id=execution.id,
            )

    # -- Finalization (unchanged) ---

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
                node_id=execution.node_id,
                task_slug=str(execution.definition_task_id or execution.node_id or ""),
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
            if command.task_id is not None:
                graph_lookup = GraphNodeLookup(session, command.run_id)
                await mark_task_failed(
                    session,
                    command.run_id,
                    command.task_id,
                    command.error_message,
                    execution_id=command.execution_id,
                    graph_repo=graph_repo,
                    graph_lookup=graph_lookup,
                )
            elif execution.node_id is not None:
                await mark_task_failed_by_node(
                    session,
                    command.run_id,
                    execution.node_id,
                    command.error_message,
                    execution_id=command.execution_id,
                    graph_repo=graph_repo,
                )
            session.commit()

            await _emit_task_status(
                run_id=command.run_id,
                node_id=execution.node_id,
                task_slug=str(execution.definition_task_id or execution.node_id or ""),
                new_status=graph_status.FAILED,
                old_status=graph_status.RUNNING,
            )
