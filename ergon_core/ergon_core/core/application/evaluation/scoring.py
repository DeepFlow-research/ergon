"""Shared score aggregation semantics for run-level evaluation summaries."""

from collections.abc import Iterable
from typing import Protocol

from pydantic import BaseModel


class ScoredEvaluation(Protocol):
    score: float | None


class EvaluationScoreSummary(BaseModel):
    model_config = {"frozen": True}

    final_score: float | None
    normalized_score: float | None
    evaluators_count: int


# TODO: mixing of models and function logic, bad!
def aggregate_evaluation_scores(
    evaluations: Iterable[ScoredEvaluation],
) -> EvaluationScoreSummary:
    rows = list(evaluations)
    scores = [row.score for row in rows if row.score is not None]
    final_score = sum(scores) if scores else None
    normalized_score = final_score / len(scores) if scores and final_score is not None else None
    return EvaluationScoreSummary(
        final_score=final_score,
        normalized_score=normalized_score,
        evaluators_count=len(rows),
    )
