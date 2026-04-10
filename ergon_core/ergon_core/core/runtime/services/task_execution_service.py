"""Task execution lifecycle: prepare, finalize success, finalize failure."""

from uuid import UUID

from h_arcane.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionWorker,
)
from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.shared.enums import TaskExecutionStatus
from h_arcane.core.persistence.telemetry.models import RunTaskExecution
from h_arcane.core.runtime.execution.propagation import (
    mark_task_failed,
    mark_task_running,
)
from h_arcane.core.runtime.services.orchestration_dto import (
    FailTaskExecutionCommand,
    FinalizeTaskExecutionCommand,
    PreparedTaskExecution,
    PrepareTaskExecutionCommand,
)
from h_arcane.core.utils import require_not_none, utcnow
from sqlmodel import select


class TaskExecutionService:
    def prepare(self, command: PrepareTaskExecutionCommand) -> PreparedTaskExecution:
        with get_session() as session:
            task = require_not_none(
                session.get(ExperimentDefinitionTask, command.task_id),
                f"Task {command.task_id} not found",
            )

            definition = require_not_none(
                session.get(ExperimentDefinition, command.definition_id),
                f"Definition {command.definition_id} not found",
            )

            # Look up the task assignment to find the worker binding
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
                    ExperimentDefinitionWorker.experiment_definition_id == command.definition_id,
                    ExperimentDefinitionWorker.binding_key == assignment.worker_binding_key,
                )
                worker = session.exec(worker_stmt).first()
                if worker is not None:
                    worker_type = worker.worker_type
                    model_target = worker.model_target
                    definition_worker_id = worker.id

            execution = RunTaskExecution(
                run_id=command.run_id,
                definition_task_id=command.task_id,
                definition_worker_id=definition_worker_id,
                status=TaskExecutionStatus.RUNNING,
                started_at=utcnow(),
            )
            session.add(execution)
            session.flush()

            mark_task_running(session, command.run_id, command.task_id, execution.id)
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
            )

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

            mark_task_failed(
                session,
                command.run_id,
                command.task_id,
                command.error_message,
                execution_id=command.execution_id,
            )
            session.commit()
