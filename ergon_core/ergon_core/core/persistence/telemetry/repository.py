"""Read and write repository for run telemetry tables."""

from uuid import UUID

from ergon_core.core.persistence.shared.ids import new_id
from ergon_core.core.persistence.telemetry.models import (
    CreateTaskEvaluation,
    RunTaskEvaluation,
)
from sqlmodel import Session, select


class TelemetryRepository:
    """Combined read/write operations for run-scoped telemetry rows."""

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_task_evaluations(self, session: Session, run_id: UUID) -> list[RunTaskEvaluation]:
        stmt = select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
        return list(session.exec(stmt).all())

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def create_task_evaluation(
        self,
        session: Session,
        command: CreateTaskEvaluation,
    ) -> RunTaskEvaluation:
        evaluation = RunTaskEvaluation(
            id=new_id(),
            run_id=command.run_id,
            task_execution_id=command.task_execution_id,
            task_id=command.task_id,
            definition_evaluator_id=command.definition_evaluator_id,
            score=command.score,
            passed=command.passed,
            feedback=command.feedback,
            summary_json={} if command.summary_json is None else command.summary_json,
        )
        session.add(evaluation)
        session.flush()
        return evaluation
