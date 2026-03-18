"""Smoke test rubric for evaluation pipeline testing.

Simple rubric that supports both CodeRule and LLMJudgeRule evaluation
to test the full evaluation pipeline.
"""

from typing import TYPE_CHECKING, Literal, Union, cast

import inngest
from pydantic import BaseModel, Field

from h_arcane.core._internal.db.models import TaskEvaluationResult, CriterionResult
from h_arcane.core._internal.evaluation.rules import CodeRule, LLMJudgeRule

if TYPE_CHECKING:
    from h_arcane.core._internal.evaluation.schemas import TaskEvaluationContext

# Rule type union for smoke test
SmokeTestRule = Union[CodeRule, LLMJudgeRule]


class SmokeTestRubric(BaseModel):
    """Simple rubric for smoke test evaluation.

    Supports both CodeRule and LLMJudgeRule to test the full evaluation
    pipeline including sandbox code execution.
    """

    benchmark: Literal["smoke_test"] = "smoke_test"  # Discriminator
    rules: list[SmokeTestRule] = Field(description="List of evaluation rules (CodeRule or LLMJudgeRule)")

    async def compute_scores(
        self,
        context: "TaskEvaluationContext",
        inngest_ctx: inngest.Context,
    ) -> TaskEvaluationResult:
        """
        Evaluate task output against rules.

        All rules are evaluated in parallel via Inngest steps.

        Args:
            context: Task evaluation context
            inngest_ctx: Inngest context for step tracing

        Returns:
            TaskEvaluationResult with scores
        """
        # Step 1: Serialize rules for Inngest steps
        async def prepare_rules_step() -> list[dict]:
            rules_data = []
            for idx, rule in enumerate(self.rules):
                rules_data.append({
                    "idx": idx,
                    "weight": rule.weight,
                    "rule": rule.model_dump(),
                    "rule_type": rule.type,  # "code" or "llm_judge"
                })
            return rules_data

        rules_with_data = cast(
            list[dict],
            await inngest_ctx.step.run("prepare-rules", prepare_rules_step),
        )

        # Step 2: Create parallel invokers
        def make_rule_invoker(rule_idx: int, weight: float, rule_dict: dict, rule_type: str):
            from h_arcane.core._internal.evaluation.events import CriterionEvaluationEvent
            from h_arcane.core._internal.evaluation.inngest_functions.criterion import (
                evaluate_criterion_fn,
            )

            # Reconstruct the rule based on type
            if rule_type == "code":
                rule = CodeRule(**rule_dict)
            else:
                rule = LLMJudgeRule(**rule_dict)

            step_id = f"rule-{rule_idx}-{rule_type}"

            event_data = CriterionEvaluationEvent(
                run_id=str(context.run_id),
                task_input=context.task_input,
                agent_reasoning=context.agent_reasoning,
                agent_outputs=context.agent_outputs,
                benchmark_name="smoke_test",  # Use smoke_test sandbox manager
                stage_name=f"Rule-{rule_idx}",
                stage_idx=0,
                rule_idx=rule_idx,
                max_score=weight,
                rule=rule,
            )
            event_data_dict = event_data.model_dump(mode="json")

            return (
                lambda ctx_ref=inngest_ctx, sid=step_id, data=event_data_dict: ctx_ref.step.invoke(
                    step_id=sid,
                    function=evaluate_criterion_fn,
                    data=data,
                )
            )

        parallel_invokers = tuple(
            make_rule_invoker(
                item["idx"], item["weight"], item["rule"], item["rule_type"]
            )
            for item in rules_with_data
        )

        # Step 3: Execute all rules in parallel
        criterion_results_tuple = await inngest_ctx.group.parallel(parallel_invokers)
        criterion_results_raw = list(criterion_results_tuple)

        criterion_results = [
            CriterionResult(**cr) if isinstance(cr, dict) else cr
            for cr in criterion_results_raw
        ]

        # Step 4: Aggregate scores
        async def aggregate_scores_step() -> dict:
            total_score = sum(r.score for r in criterion_results)
            max_score = sum(r.max_score for r in criterion_results)
            normalized_score = total_score / max_score if max_score > 0 else 0.0
            return {
                "total_score": total_score,
                "max_score": max_score,
                "normalized_score": normalized_score,
            }

        aggregate = cast(
            dict,
            await inngest_ctx.step.run("aggregate-scores", aggregate_scores_step),
        )

        return TaskEvaluationResult(
            run_id=context.run_id,
            criterion_results=[cr.model_dump() for cr in criterion_results],
            total_score=aggregate["total_score"],
            max_score=aggregate["max_score"],
            normalized_score=aggregate["normalized_score"],
            stages_evaluated=1,
            stages_passed=1 if aggregate["total_score"] > 0 else 0,
            failed_gate=None,
        )
