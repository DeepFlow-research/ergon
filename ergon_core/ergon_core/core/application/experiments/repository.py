"""Definition-domain read helpers."""

from uuid import UUID

from ergon_core.core.application.experiments.errors import (
    DefinitionInstanceNotFoundError,
    DefinitionTaskNotFoundError,
)
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
            raise DefinitionTaskNotFoundError(task_id)
        instance = session.get(ExperimentDefinitionInstance, task.instance_id)
        if instance is None:
            raise DefinitionInstanceNotFoundError(task.instance_id)
        return task, instance
