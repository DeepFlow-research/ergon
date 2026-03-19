"""Database query methods organized by entity."""

from __future__ import annotations

from uuid import UUID
from typing import TYPE_CHECKING, TypeVar, Generic, Type
from sqlalchemy import func
from sqlmodel import SQLModel, select, desc, and_
from datetime import datetime
from h_arcane.core._internal.db.connection import get_session
from h_arcane.core._internal.utils import utcnow
from h_arcane.core._internal.db.models import (
    AgentConfig,
    Experiment,
    Run,
    RunStatus,
    Message,
    Action,
    ResourceRecord,
    Evaluation,
    CriterionResult,
    TaskEvaluationResult,
    TaskExecution,
    TaskStateEvent,
    TaskEvaluator,
    TaskStatus,
    TaskTrigger,
    Thread,
    ThreadMessage,
)
from h_arcane.benchmarks.enums import BenchmarkName

if TYPE_CHECKING:
    from h_arcane.core._internal.task.services.dto import RunCompletionData


T = TypeVar("T", bound=SQLModel)


class BaseQueries(Generic[T]):
    """Base query class with common CRUD operations."""

    def __init__(self, model: Type[T]):
        self.model = model

    def get(self, id: UUID) -> T | None:
        """Get entity by ID."""
        with next(get_session()) as session:
            return session.get(self.model, id)

    def create(self, entity: T) -> T:
        """Create a new entity from a typed object."""
        # Validate and create new instance without id (will be auto-generated)
        entity_data = entity.model_dump(exclude={"id"}, exclude_none=False)
        new_entity = self.model.model_validate(entity_data)
        with next(get_session()) as session:
            session.add(new_entity)
            session.commit()
            session.refresh(new_entity)
            return new_entity

    def update(self, entity: T) -> T:
        """Update entity fields from a typed object."""
        # Check if entity has id attribute (all SQLModel tables should have it)
        entity_id = getattr(entity, "id", None)
        if entity_id is None:
            raise ValueError(f"{self.model.__name__} id must be set for update")
        with next(get_session()) as session:
            existing = session.get(self.model, entity_id)
            if existing is None:
                raise ValueError(f"{self.model.__name__} {entity_id} not found")
            # Merge updates: preserve unset fields, update set fields
            update_data = entity.model_dump(exclude_none=False)
            # Copy updated fields back to existing entity for SQLAlchemy tracking
            for key, value in update_data.items():
                setattr(existing, key, value)
            session.commit()
            session.refresh(existing)
            return existing


class RunsQueries(BaseQueries[Run]):
    """Query methods for Run model."""

    def __init__(self):
        super().__init__(Run)

    @staticmethod
    def get_by_status(status: RunStatus) -> list[Run]:
        """Get all runs with given status."""
        with next(get_session()) as session:
            statement = select(Run).where(Run.status == status)
            return list(session.exec(statement).all())

    @staticmethod
    def get_stats() -> dict:
        """Get run statistics."""
        with next(get_session()) as session:
            total = session.exec(select(Run)).all()
            return {
                "total": len(total),
                "pending": sum(1 for r in total if r.status == RunStatus.PENDING),
                "running": sum(
                    1 for r in total if r.status in [RunStatus.EXECUTING, RunStatus.EVALUATING]
                ),
                "completed": sum(1 for r in total if r.status == RunStatus.COMPLETED),
                "failed": sum(1 for r in total if r.status == RunStatus.FAILED),
            }

    def reset_for_retry(self, run_id: UUID) -> Run:
        """Reset run for retry."""
        existing = self.get(run_id)
        if existing is None:
            raise ValueError(f"Run {run_id} not found")
        updated = existing.model_copy(
            update={
                "status": RunStatus.PENDING,
                "error_message": None,
                "started_at": None,
                "completed_at": None,
            }
        )
        return self.update(updated)

    @staticmethod
    def get_recent(limit: int = 10) -> list[Run]:
        """Get most recent runs, ordered by created_at descending."""
        with next(get_session()) as session:
            statement = select(Run).order_by(desc(Run.created_at)).limit(limit)
            return list(session.exec(statement).all())

    def complete(self, run_id: UUID, data: RunCompletionData) -> Run:
        """Mark run as completed with all completion data.

        This is a single atomic operation that sets all completion fields,
        ensuring nothing is forgotten and making the completion explicit.

        Args:
            run_id: The run to complete
            data: RunCompletionData with all required completion fields

        Returns:
            Updated Run

        Raises:
            ValueError: If run not found
        """
        existing = self.get(run_id)
        if existing is None:
            raise ValueError(f"Run {run_id} not found")

        updated = existing.model_copy(
            update={
                "status": RunStatus.COMPLETED,
                "completed_at": data.completed_at,
                "final_score": data.final_score,
                "normalized_score": data.normalized_score,
                "total_cost_usd": data.total_cost_usd,
                "output_text": data.output_text,
                "execution_result": data.execution_result,
            }
        )
        return self.update(updated)


class ExperimentsQueries(BaseQueries[Experiment]):
    """Query methods for Experiment model."""

    def __init__(self):
        super().__init__(Experiment)

    @staticmethod
    def get_by_task_id(task_id: str, benchmark_name: BenchmarkName) -> Experiment:
        """Get experiment by task ID and benchmark."""
        with next(get_session()) as session:
            statement = select(Experiment).where(
                Experiment.benchmark_name == benchmark_name, Experiment.task_id == task_id
            )
            result = session.exec(statement).first()
            if result is None:
                raise ValueError(f"Experiment not found: {benchmark_name.value}/{task_id}")
            return result


class ResourcesQueries(BaseQueries[ResourceRecord]):
    """Query methods for ResourceRecord model."""

    def __init__(self):
        super().__init__(ResourceRecord)

    @staticmethod
    def get_by_experiment(experiment_id: UUID) -> list[ResourceRecord]:
        """Get all input resources for an experiment."""
        with next(get_session()) as session:
            statement = select(ResourceRecord).where(ResourceRecord.experiment_id == experiment_id)
            return list(session.exec(statement).all())

    @staticmethod
    def get_by_run(run_id: UUID) -> list[ResourceRecord]:
        """Get all output resources for a run."""
        with next(get_session()) as session:
            statement = select(ResourceRecord).where(ResourceRecord.run_id == run_id)
            return list(session.exec(statement).all())

    @staticmethod
    def get_all(
        run_id: UUID | None = None, experiment_id: UUID | None = None
    ) -> list[ResourceRecord]:
        """Get all resources, optionally filtered by run_id or experiment_id."""
        with next(get_session()) as session:
            statement = select(ResourceRecord)
            if run_id:
                statement = statement.where(ResourceRecord.run_id == run_id)
            if experiment_id:
                statement = statement.where(ResourceRecord.experiment_id == experiment_id)
            return list(session.exec(statement).all())

    # === NEW: Task-level resource queries ===

    @staticmethod
    def get_inputs_for_task(experiment_id: UUID, task_id: UUID) -> list[ResourceRecord]:
        """Get all input resources for a specific task."""
        with next(get_session()) as session:
            statement = select(ResourceRecord).where(
                ResourceRecord.experiment_id == experiment_id,
                ResourceRecord.task_id == task_id,
                ResourceRecord.is_input == True,  # noqa: E712
            )
            return list(session.exec(statement).all())

    @staticmethod
    def get_outputs_for_execution(task_execution_id: UUID) -> list[ResourceRecord]:
        """Get all output resources produced by a task execution."""
        with next(get_session()) as session:
            statement = select(ResourceRecord).where(
                ResourceRecord.task_execution_id == task_execution_id,
                ResourceRecord.is_input == False,  # noqa: E712
            )
            return list(session.exec(statement).all())

    @staticmethod
    def get_by_task(task_id: UUID) -> list[ResourceRecord]:
        """Get all resources (inputs and outputs) for a task."""
        with next(get_session()) as session:
            statement = select(ResourceRecord).where(ResourceRecord.task_id == task_id)
            return list(session.exec(statement).all())

    def create_input(
        self,
        experiment_id: UUID,
        task_id: UUID,
        name: str,
        mime_type: str,
        file_path: str,
        size_bytes: int,
        preview_text: str | None = None,
    ) -> ResourceRecord:
        """Create an input resource for a task."""
        resource = ResourceRecord(
            experiment_id=experiment_id,
            task_id=task_id,
            is_input=True,
            name=name,
            mime_type=mime_type,
            file_path=file_path,
            size_bytes=size_bytes,
            preview_text=preview_text,
        )
        return self.create(resource)

    def create_output(
        self,
        run_id: UUID,
        task_id: UUID,
        task_execution_id: UUID,
        name: str,
        mime_type: str,
        file_path: str,
        size_bytes: int,
        preview_text: str | None = None,
    ) -> ResourceRecord:
        """Create an output resource from a task execution."""
        resource = ResourceRecord(
            run_id=run_id,
            task_id=task_id,
            task_execution_id=task_execution_id,
            is_input=False,
            name=name,
            mime_type=mime_type,
            file_path=file_path,
            size_bytes=size_bytes,
            preview_text=preview_text,
        )
        return self.create(resource)


class MessagesQueries(BaseQueries[Message]):
    """Query methods for Message model."""

    def __init__(self):
        super().__init__(Message)

    @staticmethod
    def get_all(run_id: UUID, order_by: str = "sequence_num") -> list[Message]:
        """Get all messages for a run, ordered by sequence_num."""
        with next(get_session()) as session:
            statement = select(Message).where(Message.run_id == run_id)
            if order_by == "sequence_num":
                statement = statement.order_by("sequence_num")
            return list(session.exec(statement).all())


class ActionsQueries(BaseQueries[Action]):
    """Query methods for Action model."""

    def __init__(self):
        super().__init__(Action)

    @staticmethod
    def get_all(run_id: UUID, order_by: str = "action_num") -> list[Action]:
        """Get all actions for a run, ordered by action_num."""
        with next(get_session()) as session:
            statement = select(Action).where(Action.run_id == run_id)
            if order_by == "action_num":
                statement = statement.order_by("action_num")
            return list(session.exec(statement).all())


class EvaluationsQueries(BaseQueries[Evaluation]):
    """Query methods for Evaluation model."""

    def __init__(self):
        super().__init__(Evaluation)

    @staticmethod
    def get_by_run(run_id: UUID) -> Evaluation | None:
        """Get evaluation for a run."""
        with next(get_session()) as session:
            statement = select(Evaluation).where(Evaluation.run_id == run_id)
            return session.exec(statement).first()

    def create_from_eval(
        self,
        run_id: UUID,
        eval_result: Evaluation,
    ) -> Evaluation:
        """Create or update Evaluation from evaluation model (idempotent)."""
        # Check if evaluation already exists for this run_id
        existing = self.get_by_run(run_id)

        if existing:
            # Update existing evaluation - merge updates excluding id and run_id
            update_data = eval_result.model_dump(exclude={"id", "run_id"}, exclude_none=True)
            updated = existing.model_copy(update=update_data)
            updated.id = existing.id  # Preserve existing id
            updated.run_id = existing.run_id  # Preserve existing run_id
            return self.update(updated)
        else:
            # Create new evaluation - validate and exclude id
            entity_data = eval_result.model_dump(exclude={"id"}, exclude_none=False)
            new_eval = self.model.model_validate(entity_data)
            return self.create(new_eval)


class CriterionResultsQueries(BaseQueries[CriterionResult]):
    """Query methods for CriterionResult model."""

    def __init__(self):
        super().__init__(CriterionResult)

    @staticmethod
    def get_all(
        run_id: UUID,
        order_by: list[str] | None = None,
    ) -> list[CriterionResult]:
        """Get all criterion results for a run."""
        with next(get_session()) as session:
            statement = select(CriterionResult).where(CriterionResult.run_id == run_id)
            if order_by:
                for field in order_by:
                    field_attr = getattr(CriterionResult, field, None)
                    if field_attr is not None:
                        statement = statement.order_by(field_attr)
            return list(session.exec(statement).all())

    def create_from_eval(
        self,
        run_id: UUID,
        eval_result: CriterionResult,
    ) -> CriterionResult:
        """Create CriterionResult from evaluation model."""
        # Validate and exclude id - eval_result already has run_id set
        entity_data = eval_result.model_dump(exclude={"id"}, exclude_none=False)
        new_criterion = self.model.model_validate(entity_data)
        return self.create(new_criterion)


class TaskEvaluationResultsQueries(BaseQueries[TaskEvaluationResult]):
    """Query methods for TaskEvaluationResult model."""

    def __init__(self):
        super().__init__(TaskEvaluationResult)

    @staticmethod
    def get_by_run(run_id: UUID) -> TaskEvaluationResult | None:
        """Get task evaluation result for a run."""
        with next(get_session()) as session:
            statement = select(TaskEvaluationResult).where(TaskEvaluationResult.run_id == run_id)
            return session.exec(statement).first()


class AgentConfigsQueries(BaseQueries[AgentConfig]):
    """Query methods for AgentConfig model."""

    def __init__(self):
        super().__init__(AgentConfig)

    @staticmethod
    def get_by_run(run_id: UUID) -> list[AgentConfig]:
        """Get all agent configs for a run."""
        with next(get_session()) as session:
            statement = select(AgentConfig).where(AgentConfig.run_id == run_id)
            return list(session.exec(statement).all())

    def get_or_create(
        self,
        run_id: UUID,
        worker_id: UUID,
        defaults: AgentConfig,
    ) -> tuple[AgentConfig, bool]:
        """Get existing config by worker_id or create new one.

        This prevents duplicate agent configs for the same worker in a run.

        Args:
            run_id: The run this agent belongs to
            worker_id: Unique identifier for the worker instance
            defaults: AgentConfig to create if not found (run_id and worker_id will be set)

        Returns:
            (config, created) - created=True if new record was created
        """
        with next(get_session()) as session:
            # Look for existing config with same run_id and worker_id
            existing = session.exec(
                select(AgentConfig)
                .where(AgentConfig.run_id == run_id)
                .where(AgentConfig.worker_id == worker_id)
            ).first()

            if existing:
                return existing, False

            # Create new config with provided defaults
            defaults.run_id = run_id
            defaults.worker_id = worker_id
            session.add(defaults)
            session.commit()
            session.refresh(defaults)
            return defaults, True


# =============================================================================
# Task Execution Queries (for DAG-based workflows)
# =============================================================================


class TaskExecutionQueries(BaseQueries[TaskExecution]):
    """Query methods for TaskExecution model."""

    def __init__(self):
        super().__init__(TaskExecution)

    def create_execution(
        self,
        run_id: UUID,
        task_id: UUID,
        agent_id: UUID | None = None,
    ) -> TaskExecution:
        """Create a new task execution record."""
        # Get the attempt number (count existing executions + 1)
        existing = self.get_by_task(run_id, task_id)
        attempt_number = len(existing) + 1

        execution = TaskExecution(
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            attempt_number=attempt_number,
            status=TaskStatus.PENDING,
        )
        return self.create(execution)

    def get_by_task(self, run_id: UUID, task_id: UUID) -> list[TaskExecution]:
        """Get all executions for a specific task in a run."""
        with next(get_session()) as session:
            statement = (
                select(TaskExecution)
                .where(TaskExecution.run_id == run_id, TaskExecution.task_id == task_id)
                .order_by(desc(TaskExecution.attempt_number))
            )
            return list(session.exec(statement).all())

    def get_latest_by_task(self, run_id: UUID, task_id: UUID) -> TaskExecution | None:
        """Get the most recent execution for a task."""
        with next(get_session()) as session:
            statement = (
                select(TaskExecution)
                .where(TaskExecution.run_id == run_id, TaskExecution.task_id == task_id)
                .order_by(desc(TaskExecution.attempt_number))
            )
            return session.exec(statement).first()

    def get_by_run(self, run_id: UUID) -> list[TaskExecution]:
        """Get all task executions for a run."""
        with next(get_session()) as session:
            statement = select(TaskExecution).where(TaskExecution.run_id == run_id)
            return list(session.exec(statement).all())

    def get_running(self) -> list[TaskExecution]:
        """Get all currently running task executions."""
        with next(get_session()) as session:
            statement = select(TaskExecution).where(TaskExecution.status == TaskStatus.RUNNING)
            return list(session.exec(statement).all())

    def get_by_status(self, status: TaskStatus) -> list[TaskExecution]:
        """Get all task executions with a given status."""
        with next(get_session()) as session:
            statement = select(TaskExecution).where(TaskExecution.status == status)
            return list(session.exec(statement).all())

    def update_status(
        self,
        execution_id: UUID,
        status: TaskStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        output_text: str | None = None,
        output_resource_ids: list[str] | None = None,
        error_message: str | None = None,
        score: float | None = None,
        evaluation_details: dict | None = None,
    ) -> TaskExecution:
        """Update the status and related fields of a task execution."""
        existing = self.get(execution_id)
        if existing is None:
            raise ValueError(f"TaskExecution {execution_id} not found")

        update_data: dict = {"status": status}

        if started_at is not None:
            update_data["started_at"] = started_at
        if completed_at is not None:
            update_data["completed_at"] = completed_at
        if output_text is not None:
            update_data["output_text"] = output_text
        if output_resource_ids is not None:
            update_data["output_resource_ids"] = output_resource_ids
        if error_message is not None:
            update_data["error_message"] = error_message
        if score is not None:
            update_data["score"] = score
        if evaluation_details is not None:
            update_data["evaluation_details"] = evaluation_details

        updated = existing.model_copy(update=update_data)
        return self.update(updated)

    def set_agent(self, execution_id: UUID, agent_id: UUID) -> TaskExecution:
        """Set the agent_id on a task execution.

        Used to link an execution to the agent that performed it.

        Args:
            execution_id: The execution to update
            agent_id: The agent config ID to link

        Returns:
            Updated TaskExecution

        Raises:
            ValueError: If execution not found
        """
        existing = self.get(execution_id)
        if existing is None:
            raise ValueError(f"TaskExecution {execution_id} not found")

        updated = existing.model_copy(update={"agent_id": agent_id})
        return self.update(updated)


class TaskStateEventQueries(BaseQueries[TaskStateEvent]):
    """Query methods for TaskStateEvent model (append-only event log).

    This is the source of truth for task state. Use get_current_states() to
    compute the current state of all tasks from the event log.
    """

    def __init__(self):
        super().__init__(TaskStateEvent)

    def get_current_states(self, run_id: UUID) -> dict[UUID, TaskStatus]:
        """
        Compute current task states from event log.

        Returns a dict mapping task_id (UUID) -> current status (TaskStatus).
        This replaces the old Run.task_states denormalized column.
        """
        with next(get_session()) as session:
            # Subquery to get max timestamp per task
            subquery = (
                select(TaskStateEvent.task_id, func.max(TaskStateEvent.timestamp).label("max_ts"))
                .where(TaskStateEvent.run_id == run_id)
                .group_by(TaskStateEvent.task_id)
                .subquery()
            )

            # Join to get the status at that max timestamp
            statement = select(TaskStateEvent.task_id, TaskStateEvent.new_status).join(
                subquery,
                and_(
                    TaskStateEvent.task_id == subquery.c.task_id,
                    TaskStateEvent.timestamp == subquery.c.max_ts,
                    TaskStateEvent.run_id == run_id,
                ),
            )

            results = session.exec(statement).all()
            return {row.task_id: row.new_status for row in results}

    def get_task_state(self, run_id: UUID, task_id: UUID) -> TaskStatus | None:
        """Get the current state of a single task."""
        events = self.get_history(run_id, task_id)
        if not events:
            return None
        return events[-1].new_status

    def get_history(self, run_id: UUID, task_id: UUID) -> list[TaskStateEvent]:
        """Get all state events for a task, ordered by timestamp."""
        with next(get_session()) as session:
            statement = (
                select(TaskStateEvent)
                .where(TaskStateEvent.run_id == run_id, TaskStateEvent.task_id == task_id)
                .order_by("timestamp")
            )
            return list(session.exec(statement).all())

    def get_by_run(self, run_id: UUID) -> list[TaskStateEvent]:
        """Get all state events for a run, ordered by timestamp."""
        with next(get_session()) as session:
            statement = (
                select(TaskStateEvent).where(TaskStateEvent.run_id == run_id).order_by("timestamp")
            )
            return list(session.exec(statement).all())

    def get_by_event_type(self, run_id: UUID, event_type: str) -> list[TaskStateEvent]:
        """Get all events of a specific type for a run."""
        with next(get_session()) as session:
            statement = (
                select(TaskStateEvent)
                .where(TaskStateEvent.run_id == run_id, TaskStateEvent.event_type == event_type)
                .order_by("timestamp")
            )
            return list(session.exec(statement).all())

    def record_state_change(
        self,
        run_id: UUID,
        task_id: UUID,
        new_status: TaskStatus,
        old_status: TaskStatus | None = None,
        execution_id: UUID | None = None,
        triggered_by: TaskTrigger | None = None,
        metadata: dict | None = None,
    ) -> TaskStateEvent:
        """
        Record a task state change event.

        This is the primary way to update task state. The current state is
        derived from the event log via get_current_states().

        If old_status is not provided, it will be looked up from the event history.
        """
        # Look up old_status if not provided
        if old_status is None:
            old_status = self.get_task_state(run_id, task_id)

        event = TaskStateEvent(
            run_id=run_id,
            task_id=task_id,
            task_execution_id=execution_id,
            event_type="status_change",
            old_status=old_status,
            new_status=new_status,
            triggered_by=triggered_by,
            event_metadata=metadata or {},
        )
        return self.create(event)


class TaskEvaluatorQueries(BaseQueries[TaskEvaluator]):
    """Query methods for TaskEvaluator model (evaluators bound to tasks)."""

    def __init__(self):
        super().__init__(TaskEvaluator)

    def create_evaluator(
        self,
        run_id: UUID,
        task_id: UUID,
        evaluator_type: str,
        evaluator_config: dict,
    ) -> TaskEvaluator:
        """Create an evaluator binding for a task."""
        evaluator = TaskEvaluator(
            run_id=run_id,
            task_id=task_id,
            evaluator_type=evaluator_type,
            evaluator_config=evaluator_config,
            status=TaskStatus.PENDING,
        )
        return self.create(evaluator)

    def get_by_task(self, run_id: UUID, task_id: UUID) -> list[TaskEvaluator]:
        """Get all evaluators bound to a task."""
        with next(get_session()) as session:
            statement = select(TaskEvaluator).where(
                TaskEvaluator.run_id == run_id, TaskEvaluator.task_id == task_id
            )
            return list(session.exec(statement).all())

    def get_pending(self) -> list[TaskEvaluator]:
        """Get all evaluators with pending status."""
        with next(get_session()) as session:
            statement = select(TaskEvaluator).where(TaskEvaluator.status == TaskStatus.PENDING)
            return list(session.exec(statement).all())

    def get_by_run(self, run_id: UUID) -> list[TaskEvaluator]:
        """Get all evaluators for a run."""
        with next(get_session()) as session:
            statement = select(TaskEvaluator).where(TaskEvaluator.run_id == run_id)
            return list(session.exec(statement).all())

    def mark_running(self, evaluator_id: UUID) -> TaskEvaluator:
        """Mark an evaluator as currently running."""
        existing = self.get(evaluator_id)
        if existing is None:
            raise ValueError(f"TaskEvaluator {evaluator_id} not found")
        updated = existing.model_copy(update={"status": TaskStatus.RUNNING})
        return self.update(updated)

    def mark_completed(
        self,
        evaluator_id: UUID,
        score: float,
        evaluation_id: UUID | None = None,
    ) -> TaskEvaluator:
        """Mark an evaluator as completed with results."""
        existing = self.get(evaluator_id)
        if existing is None:
            raise ValueError(f"TaskEvaluator {evaluator_id} not found")
        updated = existing.model_copy(
            update={
                "status": TaskStatus.COMPLETED,
                "score": score,
                "evaluation_id": evaluation_id,
                "evaluated_at": utcnow(),
            }
        )
        return self.update(updated)

    def mark_failed(self, evaluator_id: UUID) -> TaskEvaluator:
        """Mark an evaluator as failed."""
        existing = self.get(evaluator_id)
        if existing is None:
            raise ValueError(f"TaskEvaluator {evaluator_id} not found")
        updated = existing.model_copy(
            update={
                "status": TaskStatus.FAILED,
                "evaluated_at": utcnow(),
            }
        )
        return self.update(updated)


# =============================================================================
# Communication Service Queries
# =============================================================================


class ThreadsQueries(BaseQueries[Thread]):
    """Query methods for Thread model."""

    def __init__(self):
        super().__init__(Thread)

    @staticmethod
    def _normalize_agent_ids(agent_a_id: str, agent_b_id: str) -> tuple[str, str]:
        """Normalize agent IDs to consistent order (smaller, larger)."""
        if agent_a_id < agent_b_id:
            return agent_a_id, agent_b_id
        return agent_b_id, agent_a_id

    def get_or_create_thread(
        self,
        run_id: UUID,
        experiment_id: UUID,
        agent_a_id: str,
        agent_b_id: str,
        topic: str,
    ) -> Thread:
        """Get existing thread or create new one."""
        normalized_a, normalized_b = self._normalize_agent_ids(agent_a_id, agent_b_id)

        with next(get_session()) as session:
            statement = select(Thread).where(
                Thread.run_id == run_id,
                Thread.agent_a_id == normalized_a,
                Thread.agent_b_id == normalized_b,
                Thread.topic == topic,
            )
            existing = session.exec(statement).first()

            if existing:
                return existing

            # Create new thread
            new_thread = Thread(
                run_id=run_id,
                experiment_id=experiment_id,
                agent_a_id=normalized_a,
                agent_b_id=normalized_b,
                topic=topic,
            )
            session.add(new_thread)
            session.commit()
            session.refresh(new_thread)
            return new_thread

    def get_threads_between_agents(
        self,
        agent_a_id: str,
        agent_b_id: str,
    ) -> list[Thread]:
        """Get all threads between two agents."""
        normalized_a, normalized_b = self._normalize_agent_ids(agent_a_id, agent_b_id)

        with next(get_session()) as session:
            statement = (
                select(Thread)
                .where(
                    Thread.agent_a_id == normalized_a,
                    Thread.agent_b_id == normalized_b,
                )
                .order_by(desc(Thread.updated_at))
            )
            return list(session.exec(statement).all())

    def update_timestamp(self, thread_id: UUID) -> Thread:
        """Update the updated_at timestamp of a thread."""
        with next(get_session()) as session:
            thread = session.get(Thread, thread_id)
            if thread is None:
                raise ValueError(f"Thread {thread_id} not found")
            thread.updated_at = utcnow()
            session.commit()
            session.refresh(thread)
            return thread


class ThreadMessagesQueries(BaseQueries[ThreadMessage]):
    """Query methods for ThreadMessage model."""

    def __init__(self):
        super().__init__(ThreadMessage)

    def get_by_thread(
        self,
        thread_id: UUID,
        order_by: str = "sequence_num",
    ) -> list[ThreadMessage]:
        """Get all messages in a thread, ordered by sequence."""
        with next(get_session()) as session:
            statement = select(ThreadMessage).where(ThreadMessage.thread_id == thread_id)
            if order_by == "sequence_num":
                statement = statement.order_by("sequence_num")
            return list(session.exec(statement).all())

    def get_next_sequence_num(self, thread_id: UUID) -> int:
        """Get the next sequence number for a thread."""
        with next(get_session()) as session:
            statement = (
                select(ThreadMessage)
                .where(ThreadMessage.thread_id == thread_id)
                .order_by(desc(ThreadMessage.sequence_num))
            )
            last_message = session.exec(statement).first()
            return (last_message.sequence_num + 1) if last_message else 0

    def create_message(
        self,
        thread_id: UUID,
        run_id: UUID,
        experiment_id: UUID,
        from_agent_id: str,
        to_agent_id: str,
        content: str,
    ) -> ThreadMessage:
        """Create a new message in a thread."""
        sequence_num = self.get_next_sequence_num(thread_id)

        new_message = ThreadMessage(
            thread_id=thread_id,
            run_id=run_id,
            experiment_id=experiment_id,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            content=content,
            sequence_num=sequence_num,
        )
        return self.create(new_message)

    def count_by_thread(self, thread_id: UUID) -> int:
        """Count the number of messages in a thread."""
        with next(get_session()) as session:
            statement = select(ThreadMessage).where(ThreadMessage.thread_id == thread_id)
            return len(session.exec(statement).all())


# Create query objects
class Queries:
    """Namespace for all query methods."""

    runs: RunsQueries
    experiments: ExperimentsQueries
    resources: ResourcesQueries
    messages: MessagesQueries
    actions: ActionsQueries
    evaluations: EvaluationsQueries
    criterion_results: CriterionResultsQueries
    task_evaluation_results: TaskEvaluationResultsQueries
    agent_configs: AgentConfigsQueries
    task_executions: TaskExecutionQueries
    task_state_events: TaskStateEventQueries
    task_evaluators: TaskEvaluatorQueries
    threads: ThreadsQueries
    thread_messages: ThreadMessagesQueries

    def __init__(self):
        self.runs = RunsQueries()
        self.experiments = ExperimentsQueries()
        self.resources = ResourcesQueries()
        self.messages = MessagesQueries()
        self.actions = ActionsQueries()
        self.evaluations = EvaluationsQueries()
        self.criterion_results = CriterionResultsQueries()
        self.task_evaluation_results = TaskEvaluationResultsQueries()
        self.agent_configs = AgentConfigsQueries()
        self.task_executions = TaskExecutionQueries()
        self.task_state_events = TaskStateEventQueries()
        self.task_evaluators = TaskEvaluatorQueries()
        self.threads = ThreadsQueries()
        self.thread_messages = ThreadMessagesQueries()


# Global queries instance
queries = Queries()
