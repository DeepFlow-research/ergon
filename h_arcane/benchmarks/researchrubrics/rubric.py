"""ResearchRubrics rubric definition with compute_scores()."""

from typing import TYPE_CHECKING, Literal, cast

import inngest
from pydantic import BaseModel, Field

from h_arcane.core.db.models import TaskEvaluationResult, CriterionResult
from h_arcane.core.evaluation.rules import LLMJudgeRule
from h_arcane.benchmarks.researchrubrics.schemas import RubricCriterion

if TYPE_CHECKING:
    from h_arcane.core.evaluation.task_context import TaskEvaluationContext


class ResearchRubricsRubric(BaseModel):
    """ResearchRubrics rubric for weighted criteria evaluation.

    Unlike GDPEval's staged rubric, ResearchRubrics has a flat list of
    weighted criteria without stages. Weights can be positive or negative.
    """

    benchmark: Literal["researchrubrics"] = "researchrubrics"
    criteria: list[RubricCriterion] = Field(description="List of evaluation criteria")

    async def compute_scores(
        self,
        context: "TaskEvaluationContext",
        inngest_ctx: inngest.Context,
    ) -> TaskEvaluationResult:
        """
        Evaluate research output against weighted criteria.

        Process:
        1. Convert each RubricCriterion to LLMJudgeRule with judge prompt
        2. Create CriterionEvaluationEvent for each criterion
        3. Evaluate all criteria in parallel via Inngest steps
        4. Aggregate: weighted sum of scores (criterion.weight * score)
        5. Return TaskEvaluationResult

        Args:
            context: Task evaluation context with run_id, task_input,
                     agent_reasoning, agent_outputs, and rubric
            inngest_ctx: Inngest context for step tracing

        Returns:
            TaskEvaluationResult with criterion-level and aggregate scores
        """
        # Import here to avoid circular imports
        from h_arcane.core.orchestration.criteria_evaluator import evaluate_criterion_fn
        from h_arcane.core.orchestration.events import CriterionEvaluationEvent

        # Step 1: Convert RubricCriterion to LLMJudgeRule
        async def convert_criteria_step() -> list[dict]:
            """Convert criteria to LLMJudgeRule objects with judge prompts."""
            rules_data = []
            for idx, criterion in enumerate(self.criteria):
                # Build judge prompt for this criterion
                judge_prompt = self._build_judge_prompt(criterion)

                # Create LLMJudgeRule
                llm_rule = LLMJudgeRule(
                    name=f"criterion_{idx}",
                    description=criterion.criterion,
                    weight=1.0,  # Weight is handled in aggregation
                    judge_prompt=judge_prompt,
                    expectation=None,  # Criterion text is self-explanatory
                    axis=criterion.axis,
                )
                rules_data.append(
                    {
                        "idx": idx,
                        "criterion_weight": criterion.weight,
                        "criterion_axis": criterion.axis,
                        "rule": llm_rule.model_dump(),
                    }
                )
            return rules_data

        criteria_with_rules = cast(
            list[dict],
            await inngest_ctx.step.run("convert-criteria-to-rules", convert_criteria_step),
        )

        # Step 2: Create parallel invokers for each criterion
        def make_criterion_invoker(
            criterion_idx: int,
            criterion_weight: float,
            llm_rule_dict: dict,
        ):
            """Create an invoker for evaluating a single criterion."""
            step_id = f"criterion-{criterion_idx}"
            # Max score is abs(weight) - we handle sign in aggregation
            max_score = abs(criterion_weight)

            # Reconstruct LLMJudgeRule from dict
            llm_rule = LLMJudgeRule(**llm_rule_dict)

            # Build event data
            event_data = CriterionEvaluationEvent(
                run_id=str(context.run_id),
                task_input=context.task_input,
                agent_reasoning=context.agent_reasoning,
                agent_outputs=context.agent_outputs,
                stage_name=f"Criterion-{criterion_idx}",  # No stages in ResearchRubrics
                stage_idx=0,  # All criteria at same level
                rule_idx=criterion_idx,
                max_score=max_score,
                rule=llm_rule,  # Pydantic handles serialization
            )
            event_data_dict = event_data.model_dump(mode="json")

            # Return lambda that invokes the generic criterion evaluator
            return (
                lambda ctx_ref=inngest_ctx, sid=step_id, data=event_data_dict: ctx_ref.step.invoke(
                    step_id=sid,
                    function=evaluate_criterion_fn,
                    data=data,
                )
            )

        # Build list of parallel invokers
        parallel_invokers = tuple(
            make_criterion_invoker(
                item["idx"],
                item["criterion_weight"],
                item["rule"],
            )
            for item in criteria_with_rules
        )

        # Step 3: Execute ALL criteria in parallel
        criterion_results_tuple = await inngest_ctx.group.parallel(parallel_invokers)
        criterion_results_raw = list(criterion_results_tuple)

        # Convert raw dicts to CriterionResult objects
        criterion_results = [
            CriterionResult(**cr) if isinstance(cr, dict) else cr for cr in criterion_results_raw
        ]

        # Step 4: Aggregate weighted scores
        async def aggregate_scores_step() -> dict:
            """Calculate weighted sum of scores."""
            total_score = 0.0
            max_possible_score = 0.0  # Sum of positive weights
            min_possible_score = 0.0  # Sum of negative weights

            for item in criteria_with_rules:
                idx = item["idx"]
                criterion_weight = item["criterion_weight"]
                result = criterion_results[idx]

                # Score is 0 or max_score (binary from LLM judge)
                # If criterion passed, apply its weight (positive or negative)
                if result.max_score != 0 and result.score > 0:
                    weighted_score = criterion_weight  # Full weight if passed
                else:
                    weighted_score = 0.0  # No score if failed

                total_score += weighted_score

                # Track possible score range
                if criterion_weight > 0:
                    max_possible_score += criterion_weight
                else:
                    min_possible_score += criterion_weight

            # Normalized score: (total - min) / (max - min) if range > 0
            score_range = max_possible_score - min_possible_score
            if score_range > 0:
                normalized_score = (total_score - min_possible_score) / score_range
            else:
                normalized_score = 0.0

            return {
                "total_score": total_score,
                "max_score": max_possible_score,
                "min_score": min_possible_score,
                "normalized_score": normalized_score,
            }

        aggregate = cast(
            dict,
            await inngest_ctx.step.run("aggregate-weighted-scores", aggregate_scores_step),
        )

        # Convert CriterionResult objects to dicts for JSON storage
        criterion_results_dicts: list[dict] = [cr.model_dump() for cr in criterion_results]

        return TaskEvaluationResult(
            run_id=context.run_id,
            criterion_results=criterion_results_dicts,
            total_score=aggregate["total_score"],
            max_score=aggregate["max_score"],
            normalized_score=aggregate["normalized_score"],
            stages_evaluated=1,  # All criteria evaluated as one "stage"
            stages_passed=1 if aggregate["total_score"] > 0 else 0,
            failed_gate=None,  # No gate logic in ResearchRubrics
        )

    def _build_judge_prompt(self, criterion: RubricCriterion) -> str:
        """
        Build judge prompt for evaluating a single criterion.

        Args:
            criterion: The RubricCriterion to build a prompt for

        Returns:
            System prompt for the LLM judge
        """
        axis_context = (
            f"\n\nThis criterion belongs to the '{criterion.axis}' axis." if criterion.axis else ""
        )
        weight_note = f"\n\nWeight: {criterion.weight}" if criterion.weight != 1.0 else ""

        return f"""You are an expert evaluator assessing research reports against specific criteria.

Your task is to evaluate whether a research report meets this criterion:
{criterion.criterion}{axis_context}{weight_note}

You will be given:
- The original task/request given to the researcher
- The researcher's reasoning and thought process
- The final research report/output

Evaluate whether the output meets this criterion. Provide:
1. Detailed reasoning explaining your decision, citing specific evidence from the task input, researcher reasoning, and outputs
2. A binary verdict: True if the criterion is met, False otherwise

This is a pass/fail decision. The criterion is either satisfied (True) or not satisfied (False).
Be thorough but fair in your evaluation."""
