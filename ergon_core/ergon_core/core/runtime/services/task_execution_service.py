"""Task execution lifecycle: prepare, finalize success, finalize failure."""

from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.runtime.errors.inngest_errors import ConfigurationError
from ergon_core.core.runtime.execution.propagation import (
    mark_task_failed,
    mark_task_running,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_lookup import GraphNodeLookup
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.orchestration_dto import (
    FailTaskExecutionCommand,
    FinalizeTaskExecutionCommand,
    PreparedTaskExecution,
    PrepareTaskExecutionCommand,
)
from ergon_core.core.utils import require_not_none, utcnow


class TaskExecutionService:

    def __init__(self) -> None:
        self._graph_repo = WorkflowGraphRepository()

    def prepare(self, command: PrepareTaskExecutionCommand) -> PreparedTaskExecution:
        if command.node_id is not None:
            return self._prepare_graph_native(command)
        return self._prepare_definition(command)

    # -- Graph-native path (dynamic tasks) ---

    def _prepare_graph_native(
        self, command: PrepareTaskExecutionCommand
    ) -> PreparedTaskExecution:
        with get_session() as session:
            node = session.get(RunGraphNode, command.node_id)
            if node is None:
                raise ConfigurationError(
                    f"RunGraphNode {command.node_id} not found",
                    run_id=command.run_id,
                    task_id=command.task_id,
                )
            if node.run_id != command.run_id:
                raise ConfigurationError(
                    f"RunGraphNode {command.node_id} belongs to run "
                    f"{node.run_id}, not {command.run_id}",
                    run_id=command.run_id,
                    task_id=command.task_id,
                )

            worker_binding_key = node.assigned_worker_key
            if worker_binding_key is None:
                raise ConfigurationError(
                    f"RunGraphNode {command.node_id} has no assigned_worker_key",
                    run_id=command.run_id,
                    task_id=command.task_id,
                )

            worker_row = session.exec(
                select(ExperimentDefinitionWorker).where(
                    ExperimentDefinitionWorker.experiment_definition_id
                    == command.definition_id,
                    ExperimentDefinitionWorker.binding_key == worker_binding_key,
                )
            ).first()
            if worker_row is None:
                raise ConfigurationError(
                    f"No ExperimentDefinitionWorker with binding_key="
                    f"'{worker_binding_key}' for definition {command.definition_id}",
                    run_id=command.run_id,
                    task_id=command.task_id,
                )

            definition = require_not_none(
                session.get(ExperimentDefinition, command.definition_id),
                f"Definition {command.definition_id} not found",
            )

            execution = RunTaskExecution(
                run_id=command.run_id,
                node_id=command.node_id,
                definition_worker_id=worker_row.id,
                attempt_number=self._next_attempt_number(
                    session, command.run_id, command.node_id
                ),
                status=TaskExecutionStatus.RUNNING,
                started_at=utcnow(),
            )
            session.add(execution)
            session.flush()

            self._graph_repo.update_node_status(
                session,
                command.run_id,
                command.node_id,
                TaskExecutionStatus.RUNNING,
                meta=MutationMeta(
                    actor="task-execution-service",
                    reason=f"prepare: execution {execution.id}",
                ),
            )
            session.commit()

            return PreparedTaskExecution(
                run_id=command.run_id,
                definition_id=command.definition_id,
                task_id=command.task_id,
                task_key=node.task_key,
                task_description=node.description,
                benchmark_type=definition.benchmark_type,
                worker_binding_key=worker_binding_key,
                worker_type=worker_row.worker_type,
                model_target=worker_row.model_target,
                execution_id=execution.id,
                node_id=command.node_id,
            )

    # -- Definition path (static tasks) ---

    def _prepare_definition(
        self, command: PrepareTaskExecutionCommand
    ) -> PreparedTaskExecution:
        with get_session() as session:
            task = require_not_none(
                session.get(ExperimentDefinitionTask, command.task_id),
                f"Task {command.task_id} not found",
            )

            definition = require_not_none(
                session.get(ExperimentDefinition, command.definition_id),
                f"Definition {command.definition_id} not found",
            )

            assignment_stmt = select(ExperimentDefinitionTaskAssignment).where(
                ExperimentDefinitionTaskAssignment.experiment_definition_id
                == command.definition_id,
                ExperimentDefinitionTaskAssignment.task_id == command.task_id,
            )
            assignment = session.exec(assignment_stmt).first()

            worker_binding_key: str | None = None
            worker_type: str | None = None
            model_target: str | None = None
            definition_worker_id: UUID | None = None

            if assignment is not None:
                worker_binding_key = assignment.worker_binding_key

                worker_stmt = select(ExperimentDefinitionWorker).where(
                    ExperimentDefinitionWorker.experiment_definition_id
                    == command.definition_id,
                    ExperimentDefinitionWorker.binding_key
                    == assignment.worker_binding_key,
                )
                worker = session.exec(worker_stmt).first()
                if worker is not None:
                    worker_type = worker.worker_type
                    model_target = worker.model_target
                    definition_worker_id = worker.id

            graph_lookup = GraphNodeLookup(session, command.run_id)
            resolved_node_id = graph_lookup.node_id(command.task_id)

            execution = RunTaskExecution(
                run_id=command.run_id,
                definition_task_id=command.task_id,
                definition_worker_id=definition_worker_id,
                node_id=resolved_node_id,
                attempt_number=self._next_attempt_number_by_task(
                    session, command.run_id, command.task_id
                ),
                status=TaskExecutionStatus.RUNNING,
                started_at=utcnow(),
            )
            session.add(execution)
            session.flush()

            mark_task_running(
                session,
                command.run_id,
                command.task_id,
                execution.id,
                graph_repo=self._graph_repo,
                graph_lookup=graph_lookup,
            )
            session.commit()

            return PreparedTaskExecution(
                run_id=command.run_id,
                definition_id=command.definition_id,
                task_id=command.task_id,
                task_key=task.task_key,
                task_description=task.description,
                benchmark_type=definition.benchmark_type,
                worker_binding_key=worker_binding_key,
                worker_type=worker_type,
                model_target=model_target,
                execution_id=execution.id,
                node_id=resolved_node_id,
            )

    # -- Finalization (unchanged) ---

    def finalize_success(self, command: FinalizeTaskExecutionCommand) -> None:
        with get_session() as session:
            execution = require_not_none(
                session.get(RunTaskExecution, command.execution_id),
                f"RunTaskExecution {command.execution_id} not found",
            )
            execution.status = TaskExecutionStatus.COMPLETED
            execution.completed_at = utcnow()
            execution.output_text = command.output_text
            if command.output_resource_ids:
                execution.output_json = {
                    "resource_ids": [str(rid) for rid in command.output_resource_ids],
                }
            session.add(execution)
            session.commit()

    def finalize_failure(self, command: FailTaskExecutionCommand) -> None:
        with get_session() as session:
            execution = require_not_none(
                session.get(RunTaskExecution, command.execution_id),
                f"RunTaskExecution {command.execution_id} not found",
            )
            execution.status = TaskExecutionStatus.FAILED
            execution.completed_at = utcnow()
            execution.error_json = {"message": command.error_message}
            session.add(execution)

            graph_repo = WorkflowGraphRepository()
            graph_lookup = GraphNodeLookup(session, command.run_id)
            mark_task_failed(
                session,
                command.run_id,
                command.task_id,
                command.error_message,
                execution_id=command.execution_id,
                graph_repo=graph_repo,
                graph_lookup=graph_lookup,
            )
            session.commit()

    # -- Helpers ---

    def _next_attempt_number(
        self, session: Session, run_id: UUID, node_id: UUID
    ) -> int:
        count = session.exec(
            select(func.count(RunTaskExecution.id)).where(
                RunTaskExecution.run_id == run_id,
                RunTaskExecution.node_id == node_id,
            )
        ).one()
        return count + 1

    def _next_attempt_number_by_task(
        self, session: Session, run_id: UUID, task_id: UUID
    ) -> int:
        count = session.exec(
            select(func.count(RunTaskExecution.id)).where(
                RunTaskExecution.run_id == run_id,
                RunTaskExecution.definition_task_id == task_id,
            )
        ).one()
        return count + 1
