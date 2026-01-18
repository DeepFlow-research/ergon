"""MiniF2F rubric definition."""

from typing import TYPE_CHECKING, Literal

import inngest
from pydantic import BaseModel, Field

from h_arcane.core._internal.db.models import TaskEvaluationResult
from h_arcane.core._internal.evaluation.runner import EvaluationRunner
from h_arcane.core._internal.evaluation.schemas import EvaluationData
from h_arcane.benchmarks.minif2f.sandbox import MiniF2FSandboxManager
from h_arcane.benchmarks.minif2f.rules import ProofVerificationRule

if TYPE_CHECKING:
    from h_arcane.core._internal.evaluation.schemas import TaskEvaluationContext


class MiniF2FRubric(BaseModel):
    """MiniF2F rubric for proof verification."""

    benchmark: Literal["minif2f"] = "minif2f"

    max_score: float = Field(default=1.0, description="Maximum score for proof verification")
    partial_credit_for_syntax: float = Field(
        default=0.2,
        description="Partial credit multiplier for valid Lean syntax that doesn't prove theorem",
    )

    async def compute_scores(
        self,
        context: "TaskEvaluationContext",
        inngest_ctx: inngest.Context,
    ) -> TaskEvaluationResult:
        """
        Evaluate MiniF2F proof verification.

        MiniF2F evaluation is simpler than GDPEval:
        - Single criterion: does the proof verify?
        - Binary pass/fail (1.0 or 0.0)
        - Optional partial credit for valid Lean syntax
        """
        # Create proof verification rule
        rule = ProofVerificationRule(
            name="proof_verification",
            description="Verify Lean proof compiles and proves the theorem",
            weight=1.0,
            problem_statement=context.task_input,
        )

        # Build evaluation data
        data = EvaluationData(
            run_id=context.run_id,
            task_input=context.task_input,
            agent_reasoning=context.agent_reasoning,
            agent_outputs=context.agent_outputs,
            stage_idx=0,
            stage_name="Proof Verification",
            rule_idx=0,
            max_score=self.max_score,
        )

        # Evaluate proof - use MiniF2F sandbox manager for Lean installation
        sandbox_manager = MiniF2FSandboxManager()
        runner = EvaluationRunner(data, sandbox_manager, inngest_ctx=inngest_ctx)
        criterion_result = await rule.evaluate(runner)
        await runner.cleanup()

        # Calculate final score
        if criterion_result.score >= self.max_score:
            total_score = self.max_score
            passed = True
        elif criterion_result.score > 0:
            total_score = self.partial_credit_for_syntax * self.max_score
            passed = False
        else:
            total_score = 0.0
            passed = False

        normalized_score = total_score / self.max_score if self.max_score > 0 else 0.0

        return TaskEvaluationResult(
            run_id=context.run_id,
            criterion_results=[criterion_result.model_dump()],
            total_score=total_score,
            max_score=self.max_score,
            normalized_score=normalized_score,
            stages_evaluated=1,
            stages_passed=1 if passed else 0,
            failed_gate="Proof Verification" if not passed else None,
        )
