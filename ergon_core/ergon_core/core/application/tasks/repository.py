"""Task execution domain repository."""

from uuid import UUID
from typing import TypeVar

from ergon_core.core.persistence.definitions.models import ExperimentDefinitionTask
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, col, select

PayloadModelT = TypeVar("PayloadModelT", bound=BaseModel)


class TaskExecutionRepository:
    """Domain queries over task execution rows."""

    def latest_for_node(self, session: Session, node_id: UUID) -> RunTaskExecution | None:
        stmt = (
            select(RunTaskExecution)
            .where(RunTaskExecution.node_id == node_id)
            .order_by(
                col(RunTaskExecution.attempt_number).desc(),
                col(RunTaskExecution.started_at).desc(),
            )
            .limit(1)
        )
        return session.exec(stmt).first()

    def latest_execution_id_for_node(self, session: Session, node_id: UUID) -> UUID | None:
        execution = self.latest_for_node(session, node_id)
        return None if execution is None else execution.id

    def latest_for_definition_task(
        self,
        session: Session,
        run_id: UUID,
        definition_task_id: UUID,
    ) -> RunTaskExecution | None:
        stmt = (
            select(RunTaskExecution)
            .where(
                RunTaskExecution.run_id == run_id,
                RunTaskExecution.definition_task_id == definition_task_id,
            )
            .order_by(
                col(RunTaskExecution.attempt_number).desc(),
                col(RunTaskExecution.started_at).desc(),
            )
            .limit(1)
        )
        return session.exec(stmt).first()

    def list_children_of_execution(
        self,
        session: Session,
        parent_execution_id: UUID,
    ) -> list[RunTaskExecution]:
        parent = session.get(RunTaskExecution, parent_execution_id)
        if parent is None or parent.node_id is None:
            return []
        child_node_ids_stmt = select(RunGraphNode.id).where(
            RunGraphNode.parent_node_id == parent.node_id
        )
        stmt = select(RunTaskExecution).where(
            col(RunTaskExecution.node_id).in_(child_node_ids_stmt)
        )
        return list(session.exec(stmt).all())

    def task_payload_for_execution(
        self,
        session: Session,
        task_execution_id: UUID,
        payload_model: type[PayloadModelT],
    ) -> PayloadModelT | None:
        stmt = (
            select(ExperimentDefinitionTask)
            .join(
                RunTaskExecution,
                RunTaskExecution.definition_task_id == ExperimentDefinitionTask.id,
            )
            .where(RunTaskExecution.id == task_execution_id)
        )
        result = session.exec(stmt).first()
        if result is None:
            return None
        return result.task_payload_as(payload_model)

    def next_attempt_for_node(self, session: Session, run_id: UUID, node_id: UUID) -> int:
        count = session.exec(
            select(func.count(RunTaskExecution.id)).where(
                RunTaskExecution.run_id == run_id,
                RunTaskExecution.node_id == node_id,
            )
        ).one()
        return count + 1

    def next_attempt_for_definition_task(
        self,
        session: Session,
        run_id: UUID,
        definition_task_id: UUID,
    ) -> int:
        count = session.exec(
            select(func.count(RunTaskExecution.id)).where(
                RunTaskExecution.run_id == run_id,
                RunTaskExecution.definition_task_id == definition_task_id,
            )
        ).one()
        return count + 1
