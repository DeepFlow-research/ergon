"""Workflow finalization: aggregate evaluations and close the run."""

from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.shared.enums import RunStatus
from h_arcane.core.persistence.telemetry.models import RunRecord, RunTaskEvaluation
from h_arcane.core.runtime.services.orchestration_dto import (
    FinalizedWorkflowResult,
    FinalizeWorkflowCommand,
    RunCompletionData,
)
from h_arcane.core.utils import require_not_none, utcnow
from sqlmodel import select


class WorkflowFinalizationService:

    def finalize(self, command: FinalizeWorkflowCommand) -> FinalizedWorkflowResult:
        with get_session() as session:
            evals_stmt = select(RunTaskEvaluation).where(
                RunTaskEvaluation.run_id == command.run_id,
            )
            evaluations = list(session.exec(evals_stmt).all())

            scores = [e.score for e in evaluations if e.score is not None]
            if scores:
                final_score: float | None = sum(scores)
                normalized_score: float | None = final_score / len(scores)
            else:
                final_score = None
                normalized_score = None

            completion = RunCompletionData(
                completed_at=utcnow(),
                final_score=final_score,
                normalized_score=normalized_score,
            )

            run_record = require_not_none(
                session.get(RunRecord, command.run_id),
                f"RunRecord {command.run_id} not found",
            )
            run_record.status = RunStatus.COMPLETED
            run_record.completed_at = completion.completed_at
            run_record.summary_json = {
                "final_score": completion.final_score,
                "normalized_score": completion.normalized_score,
                "evaluators_count": len(evaluations),
                "total_cost_usd": completion.total_cost_usd,
            }
            session.add(run_record)
            session.commit()

            return FinalizedWorkflowResult(
                run_id=command.run_id,
                final_score=final_score,
                normalized_score=normalized_score,
                evaluators_count=len(evaluations),
            )
