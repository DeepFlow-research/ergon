"""Read-side repository for experiment definitions."""

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
from sqlmodel import Session, select


class DefinitionRepository:
    """Reads for the immutable definition tables.

    Write operations live in ExperimentPersistenceService which coordinates
    multi-table inserts in a single transaction.
    """

    def get_definition(self, session: Session, definition_id: UUID) -> ExperimentDefinition | None:
        return session.get(ExperimentDefinition, definition_id)

    def get_workers(
        self, session: Session, definition_id: UUID
    ) -> list[ExperimentDefinitionWorker]:
        stmt = select(ExperimentDefinitionWorker).where(
            ExperimentDefinitionWorker.experiment_definition_id == definition_id
        )
        return list(session.exec(stmt).all())

    def get_evaluators(
        self, session: Session, definition_id: UUID
    ) -> list[ExperimentDefinitionEvaluator]:
        stmt = select(ExperimentDefinitionEvaluator).where(
            ExperimentDefinitionEvaluator.experiment_definition_id == definition_id
        )
        return list(session.exec(stmt).all())

    def get_instances(
        self, session: Session, definition_id: UUID
    ) -> list[ExperimentDefinitionInstance]:
        stmt = select(ExperimentDefinitionInstance).where(
            ExperimentDefinitionInstance.experiment_definition_id == definition_id
        )
        return list(session.exec(stmt).all())

    def get_tasks(self, session: Session, definition_id: UUID) -> list[ExperimentDefinitionTask]:
        stmt = select(ExperimentDefinitionTask).where(
            ExperimentDefinitionTask.experiment_definition_id == definition_id
        )
        return list(session.exec(stmt).all())

    def get_task_dependencies(
        self, session: Session, definition_id: UUID
    ) -> list[ExperimentDefinitionTaskDependency]:
        stmt = select(ExperimentDefinitionTaskDependency).where(
            ExperimentDefinitionTaskDependency.experiment_definition_id == definition_id
        )
        return list(session.exec(stmt).all())

    def get_task_assignments(
        self, session: Session, definition_id: UUID
    ) -> list[ExperimentDefinitionTaskAssignment]:
        stmt = select(ExperimentDefinitionTaskAssignment).where(
            ExperimentDefinitionTaskAssignment.experiment_definition_id == definition_id
        )
        return list(session.exec(stmt).all())

    def get_task_evaluators(
        self, session: Session, definition_id: UUID
    ) -> list[ExperimentDefinitionTaskEvaluator]:
        stmt = select(ExperimentDefinitionTaskEvaluator).where(
            ExperimentDefinitionTaskEvaluator.experiment_definition_id == definition_id
        )
        return list(session.exec(stmt).all())
