"""Read and write repository for run telemetry tables."""

from uuid import UUID

from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.persistence.shared.ids import new_id
from ergon_core.core.persistence.telemetry.models import RunTaskEvaluation
from pydantic import BaseModel
from sqlmodel import Session, select


class CreateTaskEvaluation(BaseModel):
    """Command object for persisting a task evaluation row."""

    model_config = {"frozen": True}

    run_id: UUID
    task_id: UUID
    task_execution_id: UUID
    evaluator_index: int | None = None
    evaluator_name: str | None = None
    score: float | None = None
    passed: bool | None = None
    feedback: str | None = None
    summary_json: JsonObject | None = None


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

    def create_task_evaluation(
        self,
        session: Session,
        command: CreateTaskEvaluation,
    ) -> RunTaskEvaluation:
        evaluation = RunTaskEvaluation(
            id=new_id(),
            run_id=command.run_id,
            task_id=command.task_id,
            task_execution_id=command.task_execution_id,
            evaluator_index=command.evaluator_index,
            evaluator_name=command.evaluator_name,
            score=command.score,
            passed=command.passed,
            feedback=command.feedback,
            summary_json={} if command.summary_json is None else command.summary_json,
        )
        session.add(evaluation)
        session.flush()
        return evaluation
