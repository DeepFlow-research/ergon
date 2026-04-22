"""Database query methods organized by entity.

Provides the ``queries`` singleton — a namespace that exposes typed,
session-managed query helpers for every table in the schema.  Each method
opens a session, performs the query, and closes the session; no complex
transaction management is needed at this layer.
"""

from typing import Any, Generic, Type, TypeVar
from uuid import UUID

from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionEvaluator,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionTaskDependency,
    ExperimentDefinitionTaskEvaluator,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
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

    def list_children_of(self, parent_id: UUID) -> list[RunTaskExecution]:
        """Return direct child task executions of the given parent execution.

        Uses RunGraphNode.parent_node_id for containment lookup instead
        of edge traversal. The parent execution's node_id is looked up,
        then all child nodes with that parent_node_id are found, and
        their executions returned.
        """
        with get_session() as session:
            parent = session.get(RunTaskExecution, parent_id)
            if parent is None or parent.node_id is None:
                return []
            child_node_ids_stmt = select(RunGraphNode.id).where(
                RunGraphNode.parent_node_id == parent.node_id
            )
            stmt = select(RunTaskExecution).where(
                RunTaskExecution.node_id.in_(child_node_ids_stmt)  # type: ignore[union-attr]
            )
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

    def get_task_payload(
        self,
        task_execution_id: UUID,
    ) -> dict[str, Any] | None:  # slopcop: ignore[no-typing-any]
        """Return the immutable task_payload for a task execution.

        Joins ``run_task_executions`` → ``experiment_definition_tasks``.
        Returns ``None`` if the execution row does not exist or its
        ``definition_task_id`` points at nothing (run-scoped tasks that
        weren't tied to a definition — should not happen in normal
        benchmark flow).
        """
        with get_session() as session:
            stmt = (
                select(ExperimentDefinitionTask.task_payload)
                .join(
                    RunTaskExecution,
                    RunTaskExecution.definition_task_id == ExperimentDefinitionTask.id,
                )
                .where(RunTaskExecution.id == task_execution_id)
            )
            return session.exec(stmt).first()


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

    # --- append-only-log reads -------------------------------------------

    def latest_by_path(
        self,
        *,
        task_execution_id: UUID,
        file_path: str,
    ) -> RunResource | None:
        """Most-recently-inserted row for (task_execution_id, file_path)."""
        with get_session() as session:
            stmt = (
                select(RunResource)
                .where(
                    RunResource.task_execution_id == task_execution_id,
                    RunResource.file_path == file_path,
                )
                .order_by(RunResource.created_at.desc(), RunResource.id.desc())
                .limit(1)
            )
            return session.exec(stmt).first()

    def find_by_hash(
        self,
        *,
        task_execution_id: UUID,
        content_hash: str,
    ) -> RunResource | None:
        """Any row in this task execution whose content_hash matches."""
        with get_session() as session:
            stmt = (
                select(RunResource)
                .where(
                    RunResource.task_execution_id == task_execution_id,
                    RunResource.content_hash == content_hash,
                )
                .limit(1)
            )
            return session.exec(stmt).first()

    def list_latest_for_execution(
        self,
        task_execution_id: UUID,
    ) -> list[RunResource]:
        """One row per file_path -- the most-recently-inserted row wins.

        Uses a subquery to find the max (created_at, id) per file_path,
        compatible with both Postgres and SQLite.
        """
        with get_session() as session:
            all_rows = list(
                session.exec(
                    select(RunResource)
                    .where(RunResource.task_execution_id == task_execution_id)
                    .order_by(
                        RunResource.file_path,
                        RunResource.created_at.desc(),
                        RunResource.id.desc(),
                    )
                ).all()
            )
            seen: dict[str, RunResource] = {}
            for row in all_rows:
                if row.file_path not in seen:
                    seen[row.file_path] = row
            return list(seen.values())

    # --- append ----------------------------------------------------------

    def append(  # slopcop: ignore[max-function-params]
        self,
        *,
        run_id: UUID,
        task_execution_id: UUID,
        kind: str,
        name: str,
        mime_type: str,
        file_path: str,
        size_bytes: int,
        error: str | None,
        content_hash: str | None,
        metadata: dict[str, object] | None = None,
    ) -> RunResource:
        """Append one row to the log. Never updates."""
        with get_session() as session:
            row = RunResource(
                run_id=run_id,
                task_execution_id=task_execution_id,
                kind=kind,
                name=name,
                mime_type=mime_type,
                file_path=file_path,
                size_bytes=size_bytes,
                error=error,
                content_hash=content_hash,
                metadata_json=metadata or {},
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row


# ---------------------------------------------------------------------------
# Namespace Singleton
# ---------------------------------------------------------------------------


class Queries:
    """Namespace singleton providing typed query methods for all tables."""

    runs: RunsQueries
    definitions: DefinitionsQueries
    task_executions: TaskExecutionsQueries
    evaluations: EvaluationsQueries
    resources: ResourcesQueries

    def __init__(self) -> None:
        self.runs = RunsQueries()
        self.definitions = DefinitionsQueries()
        self.task_executions = TaskExecutionsQueries()
        self.evaluations = EvaluationsQueries()
        self.resources = ResourcesQueries()


queries = Queries()
