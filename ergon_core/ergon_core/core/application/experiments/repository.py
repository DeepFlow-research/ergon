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
from ergon_core.core.persistence.telemetry.models import BenchmarkDefinitionRecord
from sqlmodel import Session, select


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

    def list_by_experiment_tag(
        self,
        session: Session,
        tag: str,
    ) -> list[BenchmarkDefinitionRecord]:
        """List ``BenchmarkDefinitionRecord`` rows tagged with ``tag``.

        The ``experiment`` column groups records into a named logical
        experiment; this helper is the read side of that grouping.
        """
        stmt = select(BenchmarkDefinitionRecord).where(
            BenchmarkDefinitionRecord.experiment == tag,
        )
        return list(session.exec(stmt).all())

    def distinct_experiment_tags(self, session: Session) -> list[str]:
        """Distinct non-null ``experiment`` tag values across all records."""
        stmt = (
            select(BenchmarkDefinitionRecord.experiment)
            .where(BenchmarkDefinitionRecord.experiment.is_not(None))
            .distinct()
        )
        return [row for row in session.exec(stmt).all() if row is not None]
