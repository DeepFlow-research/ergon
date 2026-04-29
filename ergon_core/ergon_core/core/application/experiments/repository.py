"""Definition-domain read helpers."""

from uuid import UUID

from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
)
from sqlmodel import Session


class DefinitionRepository:
    """Domain reads over experiment definition rows."""

    def get(self, session: Session, definition_id: UUID) -> ExperimentDefinition | None:
        return session.get(ExperimentDefinition, definition_id)

    def task_with_instance(
        self,
        session: Session,
        task_id: UUID,
    ) -> tuple[ExperimentDefinitionTask, ExperimentDefinitionInstance]:
        task = session.get(ExperimentDefinitionTask, task_id)
        if task is None:
            raise ValueError(f"ExperimentDefinitionTask {task_id} not found")
        instance = session.get(ExperimentDefinitionInstance, task.instance_id)
        if instance is None:
            raise ValueError(f"ExperimentDefinitionInstance {task.instance_id} not found")
        return task, instance
