"""Read and write repository for run telemetry tables."""

from uuid import UUID

from ergon_core.api.json_types import JsonObject
from ergon_core.core.persistence.shared.ids import new_id
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
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

    def create_task_evaluation(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
        task_execution_id: UUID,
        definition_task_id: UUID | None,
        definition_evaluator_id: UUID,
        score: float | None = None,
        passed: bool | None = None,
        feedback: str | None = None,
        summary_json: JsonObject | None = None,
    ) -> RunTaskEvaluation:
        evaluation = RunTaskEvaluation(
            id=new_id(),
            run_id=run_id,
            node_id=node_id,
            task_execution_id=task_execution_id,
            definition_task_id=definition_task_id,
            definition_evaluator_id=definition_evaluator_id,
            score=score,
            passed=passed,
            feedback=feedback,
            summary_json={} if summary_json is None else summary_json,
        )
        session.add(evaluation)
        session.flush()
        return evaluation

    def refresh_run_evaluation_summary(self, session: Session, run_id: UUID) -> None:
        run = session.get(RunRecord, run_id)
        if run is None:
            return
        evaluations = self.get_task_evaluations(session, run_id)
        scores = [evaluation.score for evaluation in evaluations if evaluation.score is not None]
        final_score = sum(scores) if scores else None
        normalized_score = final_score / len(scores) if scores and final_score is not None else None
        existing_summary = dict({} if run.summary_json is None else run.summary_json)
        existing_summary.update(
            {
                "final_score": final_score,
                "normalized_score": normalized_score,
                "evaluators_count": len(evaluations),
            }
        )
        run.summary_json = existing_summary
        session.add(run)
        session.flush()
