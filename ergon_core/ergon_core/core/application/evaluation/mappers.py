"""Internal mapping helpers for evaluation-domain summaries."""

from typing import Protocol

from ergon_core.api.rubric import TaskEvaluationResult
from ergon_core.core.application.evaluation.models import CriterionSpec
from ergon_core.core.application.evaluation.summary import (
    CriterionOutcomeEntry,
    EvaluationSummary,
)
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError


class EvaluationSummarySource(Protocol):
    result: TaskEvaluationResult
    specs: list[CriterionSpec]


def _criterion_status(*, passed: bool, error: dict | None, skipped_reason: str | None) -> str:
    if error is not None:
        return "errored"
    if skipped_reason is not None:
        return "skipped"
    return "passed" if passed else "failed"


def _summary_max_score(
    result: TaskEvaluationResult,
    specs: list[CriterionSpec],
) -> float:
    if result.metadata.get("score_scale") == "normalized_0_1":
        return 1.0
    return sum(s.max_score for s in specs) if specs else 1.0


def build_evaluation_summary(
    service_result: EvaluationSummarySource,
    evaluation_input: str | None,
) -> EvaluationSummary:
    result = service_result.result
    specs = service_result.specs
    spec_by_idx = {s.criterion_idx: s for s in specs}
    max_score_total = _summary_max_score(result, specs)
    entries: list[CriterionOutcomeEntry] = []
    for i, cr in enumerate(result.criterion_results):
        spec = spec_by_idx.get(i)
        if spec is None:
            raise ContractViolationError(
                f"Criterion result at index {i} ({cr.slug!r}) has no matching "
                "CriterionSpec - specs and results are out of sync",
            )
        entries.append(
            CriterionOutcomeEntry(
                criterion_slug=cr.slug,
                criterion_name=cr.name or cr.slug,
                criterion_type=spec.criterion.type_slug,
                criterion_description=spec.criterion.description,
                stage_num=spec.stage_idx,
                stage_name=spec.stage_name,
                criterion_num=spec.criterion_idx,
                status=_criterion_status(
                    passed=cr.passed,
                    error=cr.error,
                    skipped_reason=cr.skipped_reason,
                ),
                score=cr.score,
                max_score=spec.max_score,
                passed=cr.passed,
                weight=cr.weight,
                contribution=cr.score,
                feedback=cr.feedback,
                model_reasoning=cr.model_reasoning,
                skipped_reason=cr.skipped_reason,
                evaluation_input=cr.evaluation_input or evaluation_input,
                evaluated_action_ids=cr.evaluated_action_ids,
                evaluated_resource_ids=cr.evaluated_resource_ids,
                observation=cr.observation,
                error=cr.error,
            )
        )
    stage_names = {s.stage_name for s in specs}
    stages_passed = sum(
        1
        for stage_name in stage_names
        if all(e.passed for e in entries if e.stage_name == stage_name)
    )
    return EvaluationSummary(
        evaluator_name=result.evaluator_name,
        max_score=max_score_total,
        normalized_score=result.score,
        stages_evaluated=len(stage_names),
        stages_passed=stages_passed,
        metadata=result.metadata,
        criterion_results=entries,
    )
