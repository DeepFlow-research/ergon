"""Database query methods organized by entity.

Provides the ``queries`` singleton — a namespace that exposes typed,
session-managed query helpers for every table in the schema.  Each method
opens a session, performs the query, and closes the session; no complex
transaction management is needed at this layer.
"""

from typing import Any, Generic, Type, TypeVar
from uuid import UUID

from h_arcane.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionEvaluator,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionTaskDependency,
    ExperimentDefinitionTaskEvaluator,
    ExperimentDefinitionWorker,
)
from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from h_arcane.core.persistence.telemetry.models import (
    RunAction,
    RunRecord,
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
    RunTaskStateEvent,
)
from sqlmodel import SQLModel, desc, select

T = TypeVar("T", bound=SQLModel)

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class BaseQueries(Generic[T]):
    """Base query class with common CRUD operations."""

    def __init__(self, model: Type[T]):
        self.model = model

    def get(self, id: UUID) -> T | None:
        with get_session() as session:
            return session.get(self.model, id)

    def create(self, entity: T) -> T:
        entity_data = entity.model_dump(exclude={"id"}, exclude_none=False)
        new_entity = self.model.model_validate(entity_data)
        with get_session() as session:
            session.add(new_entity)
            session.commit()
            session.refresh(new_entity)
            return new_entity

    def update(self, entity: T) -> T:
        entity_id: UUID | None = entity.model_dump().get("id")
        if entity_id is None:
            raise ValueError(f"{self.model.__name__} id must be set for update")
        with get_session() as session:
            existing = session.get(self.model, entity_id)
            if existing is None:
                raise ValueError(f"{self.model.__name__} {entity_id} not found")
            for key, value in entity.model_dump(exclude_none=False).items():
                setattr(existing, key, value)
            session.commit()
            session.refresh(existing)
            return existing

    def list_all(self, *, limit: int | None = None) -> list[T]:
        with get_session() as session:
            stmt = select(self.model)
            if limit is not None:
                stmt = stmt.limit(limit)
            return list(session.exec(stmt).all())


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


class RunsQueries(BaseQueries[RunRecord]):
    def __init__(self) -> None:
        super().__init__(RunRecord)

    def list_by_definition(self, definition_id: UUID) -> list[RunRecord]:
        with get_session() as session:
            stmt = (
                select(RunRecord)
                .where(RunRecord.experiment_definition_id == definition_id)
                .order_by(desc(RunRecord.created_at))
            )
            return list(session.exec(stmt).all())

    def get_by_status(self, status: RunStatus | str) -> list[RunRecord]:
        with get_session() as session:
            stmt = select(RunRecord).where(RunRecord.status == status)
            return list(session.exec(stmt).all())

    def get_recent(self, limit: int = 10) -> list[RunRecord]:
        with get_session() as session:
            stmt = select(RunRecord).order_by(desc(RunRecord.created_at)).limit(limit)
            return list(session.exec(stmt).all())


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------


class DefinitionsQueries(BaseQueries[ExperimentDefinition]):
    def __init__(self) -> None:
        super().__init__(ExperimentDefinition)

    def get_by_benchmark_type(self, benchmark_type: str) -> list[ExperimentDefinition]:
        with get_session() as session:
            stmt = select(ExperimentDefinition).where(
                ExperimentDefinition.benchmark_type == benchmark_type
            )
            return list(session.exec(stmt).all())

    def get_workers(self, definition_id: UUID) -> list[ExperimentDefinitionWorker]:
        with get_session() as session:
            stmt = select(ExperimentDefinitionWorker).where(
                ExperimentDefinitionWorker.experiment_definition_id == definition_id
            )
            return list(session.exec(stmt).all())

    def get_evaluators(self, definition_id: UUID) -> list[ExperimentDefinitionEvaluator]:
        with get_session() as session:
            stmt = select(ExperimentDefinitionEvaluator).where(
                ExperimentDefinitionEvaluator.experiment_definition_id == definition_id
            )
            return list(session.exec(stmt).all())

    def get_instances(self, definition_id: UUID) -> list[ExperimentDefinitionInstance]:
        with get_session() as session:
            stmt = select(ExperimentDefinitionInstance).where(
                ExperimentDefinitionInstance.experiment_definition_id == definition_id
            )
            return list(session.exec(stmt).all())

    def get_tasks(self, definition_id: UUID) -> list[ExperimentDefinitionTask]:
        with get_session() as session:
            stmt = select(ExperimentDefinitionTask).where(
                ExperimentDefinitionTask.experiment_definition_id == definition_id
            )
            return list(session.exec(stmt).all())

    def get_task_dependencies(
        self, definition_id: UUID
    ) -> list[ExperimentDefinitionTaskDependency]:
        with get_session() as session:
            stmt = select(ExperimentDefinitionTaskDependency).where(
                ExperimentDefinitionTaskDependency.experiment_definition_id == definition_id
            )
            return list(session.exec(stmt).all())

    def get_task_assignments(self, definition_id: UUID) -> list[ExperimentDefinitionTaskAssignment]:
        with get_session() as session:
            stmt = select(ExperimentDefinitionTaskAssignment).where(
                ExperimentDefinitionTaskAssignment.experiment_definition_id == definition_id
            )
            return list(session.exec(stmt).all())

    def get_task_evaluators(self, definition_id: UUID) -> list[ExperimentDefinitionTaskEvaluator]:
        with get_session() as session:
            stmt = select(ExperimentDefinitionTaskEvaluator).where(
                ExperimentDefinitionTaskEvaluator.experiment_definition_id == definition_id
            )
            return list(session.exec(stmt).all())


# ---------------------------------------------------------------------------
# Task Executions
# ---------------------------------------------------------------------------


class TaskExecutionsQueries(BaseQueries[RunTaskExecution]):
    def __init__(self) -> None:
        super().__init__(RunTaskExecution)

    def list_by_run(self, run_id: UUID) -> list[RunTaskExecution]:
        with get_session() as session:
            stmt = select(RunTaskExecution).where(RunTaskExecution.run_id == run_id)
            return list(session.exec(stmt).all())

    def get_by_task(self, run_id: UUID, definition_task_id: UUID) -> list[RunTaskExecution]:
        with get_session() as session:
            stmt = (
                select(RunTaskExecution)
                .where(
                    RunTaskExecution.run_id == run_id,
                    RunTaskExecution.definition_task_id == definition_task_id,
                )
                .order_by(desc(RunTaskExecution.attempt_number))
            )
            return list(session.exec(stmt).all())

    def get_latest_by_task(self, run_id: UUID, definition_task_id: UUID) -> RunTaskExecution | None:
        with get_session() as session:
            stmt = (
                select(RunTaskExecution)
                .where(
                    RunTaskExecution.run_id == run_id,
                    RunTaskExecution.definition_task_id == definition_task_id,
                )
                .order_by(desc(RunTaskExecution.attempt_number))
            )
            return session.exec(stmt).first()

    def get_by_status(self, status: TaskExecutionStatus | str) -> list[RunTaskExecution]:
        with get_session() as session:
            stmt = select(RunTaskExecution).where(RunTaskExecution.status == status)
            return list(session.exec(stmt).all())

    def update_status(
        self,
        execution_id: UUID,
        status: TaskExecutionStatus | str,
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> RunTaskExecution:
        with get_session() as session:
            existing = session.get(RunTaskExecution, execution_id)
            if existing is None:
                raise ValueError(f"RunTaskExecution {execution_id} not found")
            existing.status = status
            for key, value in kwargs.items():
                if value is not None:
                    setattr(existing, key, value)
            session.commit()
            session.refresh(existing)
            return existing


# ---------------------------------------------------------------------------
# State Events
# ---------------------------------------------------------------------------


class StateEventsQueries(BaseQueries[RunTaskStateEvent]):
    def __init__(self) -> None:
        super().__init__(RunTaskStateEvent)

    def list_by_run(self, run_id: UUID) -> list[RunTaskStateEvent]:
        with get_session() as session:
            stmt = (
                select(RunTaskStateEvent)
                .where(RunTaskStateEvent.run_id == run_id)
                .order_by(RunTaskStateEvent.created_at)
            )
            return list(session.exec(stmt).all())

    def get_by_task(self, run_id: UUID, definition_task_id: UUID) -> list[RunTaskStateEvent]:
        with get_session() as session:
            stmt = (
                select(RunTaskStateEvent)
                .where(
                    RunTaskStateEvent.run_id == run_id,
                    RunTaskStateEvent.definition_task_id == definition_task_id,
                )
                .order_by(RunTaskStateEvent.created_at)
            )
            return list(session.exec(stmt).all())

    def get_latest_status(self, run_id: UUID, definition_task_id: UUID) -> str | None:
        events = self.get_by_task(run_id, definition_task_id)
        if not events:
            return None
        return events[-1].new_status

    def get_by_event_type(self, run_id: UUID, event_type: str) -> list[RunTaskStateEvent]:
        with get_session() as session:
            stmt = (
                select(RunTaskStateEvent)
                .where(
                    RunTaskStateEvent.run_id == run_id,
                    RunTaskStateEvent.event_type == event_type,
                )
                .order_by(RunTaskStateEvent.created_at)
            )
            return list(session.exec(stmt).all())


# ---------------------------------------------------------------------------
# Evaluations
# ---------------------------------------------------------------------------


class EvaluationsQueries(BaseQueries[RunTaskEvaluation]):
    def __init__(self) -> None:
        super().__init__(RunTaskEvaluation)

    def list_by_run(self, run_id: UUID) -> list[RunTaskEvaluation]:
        with get_session() as session:
            stmt = select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
            return list(session.exec(stmt).all())

    def get_by_task(self, run_id: UUID, definition_task_id: UUID) -> list[RunTaskEvaluation]:
        with get_session() as session:
            stmt = select(RunTaskEvaluation).where(
                RunTaskEvaluation.run_id == run_id,
                RunTaskEvaluation.definition_task_id == definition_task_id,
            )
            return list(session.exec(stmt).all())

    def get_by_evaluator(
        self, run_id: UUID, definition_evaluator_id: UUID
    ) -> list[RunTaskEvaluation]:
        with get_session() as session:
            stmt = select(RunTaskEvaluation).where(
                RunTaskEvaluation.run_id == run_id,
                RunTaskEvaluation.definition_evaluator_id == definition_evaluator_id,
            )
            return list(session.exec(stmt).all())


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


class ActionsQueries(BaseQueries[RunAction]):
    def __init__(self) -> None:
        super().__init__(RunAction)

    def list_by_run(self, run_id: UUID) -> list[RunAction]:
        with get_session() as session:
            stmt = (
                select(RunAction).where(RunAction.run_id == run_id).order_by(RunAction.action_num)
            )
            return list(session.exec(stmt).all())

    def list_by_execution(self, task_execution_id: UUID) -> list[RunAction]:
        with get_session() as session:
            stmt = (
                select(RunAction)
                .where(RunAction.task_execution_id == task_execution_id)
                .order_by(RunAction.action_num)
            )
            return list(session.exec(stmt).all())


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


class ResourcesQueries(BaseQueries[RunResource]):
    def __init__(self) -> None:
        super().__init__(RunResource)

    def list_by_run(self, run_id: UUID) -> list[RunResource]:
        with get_session() as session:
            stmt = select(RunResource).where(RunResource.run_id == run_id)
            return list(session.exec(stmt).all())

    def list_by_execution(self, task_execution_id: UUID) -> list[RunResource]:
        with get_session() as session:
            stmt = select(RunResource).where(RunResource.task_execution_id == task_execution_id)
            return list(session.exec(stmt).all())


# ---------------------------------------------------------------------------
# Namespace Singleton
# ---------------------------------------------------------------------------


class Queries:
    """Namespace singleton providing typed query methods for all tables."""

    runs: RunsQueries
    definitions: DefinitionsQueries
    task_executions: TaskExecutionsQueries
    state_events: StateEventsQueries
    evaluations: EvaluationsQueries
    actions: ActionsQueries
    resources: ResourcesQueries

    def __init__(self) -> None:
        self.runs = RunsQueries()
        self.definitions = DefinitionsQueries()
        self.task_executions = TaskExecutionsQueries()
        self.state_events = StateEventsQueries()
        self.evaluations = EvaluationsQueries()
        self.actions = ActionsQueries()
        self.resources = ResourcesQueries()


queries = Queries()
