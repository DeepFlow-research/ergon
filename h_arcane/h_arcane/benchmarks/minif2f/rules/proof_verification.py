"""Proof verification criterion for formal math (Lean)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from h_arcane.core._internal.db.models import CriterionResult
from h_arcane.core._internal.evaluation.rules.base import BaseCriterion

if TYPE_CHECKING:
    from h_arcane.core._internal.evaluation.runtime import CriterionRuntime
    from h_arcane.core._internal.evaluation.schemas import CriterionContext


class ExtractedProof(BaseModel):
    """Typed payload extracted from agent outputs."""

    proof_code: str
    source: str
    evaluated_resource_ids: list[str]


class ProofVerificationOutcome(BaseModel):
    """Typed result from Lean proof verification."""

    verified: bool
    errors: str | None = None
    output: str | None = None


class ProofVerificationRule(BaseCriterion):
    """Criterion for verifying formal proofs in Lean."""

    type: Literal["proof_verification"] = "proof_verification"
    problem_statement: str | None = Field(
        default=None,
        description="Optional theorem statement override; defaults to criterion context task_input.",
    )
    ground_truth_proof: str | None = Field(
        default=None,
        description="Ground truth proof (for reference, not used in evaluation)",
    )
    formal_system: Literal["lean"] = Field(
        default="lean",
        description="Formal system used (currently only Lean supported)",
    )

    async def evaluate(
        self,
        runtime: "CriterionRuntime",
        context: "CriterionContext",
    ) -> CriterionResult:
        """Verify Lean proof."""
        await runtime.ensure_sandbox()

        proof_data = self._extract_proof(context)
        proof_code = proof_data.proof_code
        problem_statement = self.problem_statement or context.task_input

        evaluation_log = f"""-- Expected theorem:
-- {problem_statement.replace(chr(10), chr(10) + "-- ")}

-- Agent's proof file:
{proof_code}
"""

        verify_result = await self._verify_proof(runtime, proof_code)
        score = context.max_score if verify_result.verified else 0.0
        feedback = (
            "Proof successfully verified by Lean compiler."
            if verify_result.verified
            else f"Proof verification failed:\n{verify_result.errors or 'Unknown error'}"
        )

        return CriterionResult(
            run_id=context.run_id,
            stage_num=context.stage_idx,
            stage_name=context.stage_name,
            criterion_num=context.criterion_idx,
            criterion_type="proof_verification",
            criterion_description=self.description,
            score=score,
            max_score=context.max_score,
            feedback=feedback,
            evaluation_input=evaluation_log,
            evaluated_action_ids=[],
            evaluated_resource_ids=proof_data.evaluated_resource_ids,
        )

    def _extract_proof(self, context: "CriterionContext") -> ExtractedProof:
        """Extract proof from criterion outputs."""
        final_solution = next(
            (r for r in context.agent_outputs if r.name == "final_solution.lean"),
            None,
        )

        if not final_solution:
            other_lean_files = [r.name for r in context.agent_outputs if r.name.endswith(".lean")]
            if other_lean_files:
                files_list = ", ".join(other_lean_files)
                raise ValueError(
                    f"No 'final_solution.lean' found in /workspace/final_output/. "
                    f"Found other .lean files: [{files_list}]. "
                    "The worker must write their final proof to "
                    "'/workspace/final_output/final_solution.lean' for evaluation."
                )
            raise ValueError(
                "No 'final_solution.lean' found in agent outputs. "
                "The worker must write their final proof to "
                "'/workspace/final_output/final_solution.lean' for evaluation."
            )

        return ExtractedProof(
            proof_code=final_solution.load_text(),
            source="file:final_solution.lean",
            evaluated_resource_ids=[str(final_solution.id)],
        )

    async def _verify_proof(
        self,
        runtime: "CriterionRuntime",
        proof_code: str,
    ) -> ProofVerificationOutcome:
        """Write proof to sandbox and run Lean verification."""
        if "sorry" in proof_code:
            return ProofVerificationOutcome(
                verified=False,
                errors="Proof contains 'sorry' - incomplete proof not allowed",
                output=None,
            )

        await runtime.write_file(
            "/tools/mathlib_project/src/verify.lean",
            proof_code.encode("utf-8"),
        )

        result = await runtime.run_command(
            "export PATH=$HOME/.elan/bin:$PATH && cd /tools/mathlib_project && lean src/verify.lean 2>&1",
            timeout=120,
        )

        output = (result.stdout or "") + (result.stderr or "")
        verified = result.exit_code == 0
        if not verified and not output:
            output = f"Lean verification failed with exit code {result.exit_code}"

        return ProofVerificationOutcome(
            verified=verified,
            errors=output if not verified else None,
            output=output if verified else None,
        )
