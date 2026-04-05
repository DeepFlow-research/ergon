"""Proof-verification criterion for formal mathematics (Lean).

Extracts the agent's ``final_solution.lean`` from the worker result
artifacts, writes it into the sandbox, and invokes the Lean compiler
to verify the proof.
"""

from __future__ import annotations

from typing import Any, ClassVar

from h_arcane.api.criterion import Criterion
from h_arcane.api.evaluation_context import EvaluationContext
from h_arcane.api.results import CriterionResult
from pydantic import BaseModel

LEAN_CMD = (
    "export PATH=$HOME/.elan/bin:$PATH && "
    "cd /tools/mathlib_project && lean src/verify.lean 2>&1"
)


class ExtractedProof(BaseModel):
    """Typed payload extracted from agent outputs."""

    proof_code: str
    source: str
    evaluated_resource_ids: list[str]


class ProofVerificationOutcome(BaseModel):
    """Typed result from Lean compiler verification."""

    verified: bool
    errors: str | None = None
    output: str | None = None


class ProofVerificationCriterion(Criterion):
    """Criterion that verifies Lean formal proofs via sandbox compilation.

    The evaluate path:
    1. Extract ``final_solution.lean`` from ``worker_result.artifacts``
    2. Reject proofs containing ``sorry`` (incomplete)
    3. Write proof into sandbox and run the Lean compiler
    4. Return full-score on exit-code 0, else 0
    """

    type_slug: ClassVar[str] = "proof-verification"

    def __init__(
        self,
        *,
        name: str = "proof_verification",
        weight: float = 1.0,
        max_score: float = 1.0,
        problem_statement: str | None = None,
        ground_truth_proof: str | None = None,
        formal_system: str = "lean",
    ) -> None:
        super().__init__(name=name, weight=weight)
        self.max_score = max_score
        self.problem_statement = problem_statement
        self.ground_truth_proof = ground_truth_proof
        self.formal_system = formal_system

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        proof_data = self._extract_proof(context)
        proof_code = proof_data.proof_code
        problem_stmt = self.problem_statement or context.task.description

        evaluation_log = (
            f"-- Expected theorem:\n"
            f"-- {problem_stmt.replace(chr(10), chr(10) + '-- ')}\n\n"
            f"-- Agent's proof file:\n{proof_code}\n"
        )

        outcome = await self._verify_proof(context, proof_code)
        score = self.max_score if outcome.verified else 0.0
        feedback = (
            "Proof successfully verified by Lean compiler."
            if outcome.verified
            else f"Proof verification failed:\n{outcome.errors or 'Unknown error'}"
        )

        return CriterionResult(
            name=self.name,
            score=score,
            passed=outcome.verified,
            weight=self.weight,
            feedback=feedback,
            metadata={
                "evaluation_input": evaluation_log,
                "evaluated_resource_ids": proof_data.evaluated_resource_ids,
            },
        )

    # ------------------------------------------------------------------

    def _extract_proof(self, context: EvaluationContext) -> ExtractedProof:
        """Extract proof code from worker result artifacts."""
        artifacts: dict[str, Any] = context.worker_result.artifacts

        proof_code = artifacts.get("final_solution.lean")
        if proof_code is not None:
            return ExtractedProof(
                proof_code=str(proof_code),
                source="artifact:final_solution.lean",
                evaluated_resource_ids=[],
            )

        lean_files = [k for k in artifacts if k.endswith(".lean")]
        if lean_files:
            raise ValueError(
                f"No 'final_solution.lean' found in worker artifacts. "
                f"Found other .lean files: {lean_files}. "
                "The worker must store the final proof as "
                "artifacts['final_solution.lean']."
            )

        if context.worker_result.output and context.worker_result.output.strip():
            return ExtractedProof(
                proof_code=context.worker_result.output,
                source="worker_output",
                evaluated_resource_ids=[],
            )

        raise ValueError(
            "No 'final_solution.lean' found in worker artifacts and no "
            "proof code in worker output."
        )

    async def _verify_proof(
        self,
        context: EvaluationContext,
        proof_code: str,
    ) -> ProofVerificationOutcome:
        """Write proof into sandbox and run Lean verification.

        Falls back to static analysis when no sandbox is available.
        """
        if "sorry" in proof_code:
            return ProofVerificationOutcome(
                verified=False,
                errors="Proof contains 'sorry' — incomplete proof not allowed",
            )

        sandbox_id = context.sandbox_id
        if sandbox_id is None:
            return ProofVerificationOutcome(
                verified=False,
                errors=(
                    "No sandbox available for Lean verification. "
                    "Proof was extracted but could not be compiled."
                ),
            )

        runtime = context.metadata.get("runtime")
        if runtime is None:
            return ProofVerificationOutcome(
                verified=False,
                errors="No criterion runtime in evaluation context metadata.",
            )

        await runtime.write_file(
            "/tools/mathlib_project/src/verify.lean",
            proof_code.encode("utf-8"),
        )

        result = await runtime.run_command(LEAN_CMD, timeout=120)

        output = (result.stdout or "") + (result.stderr or "")
        verified = result.exit_code == 0
        if not verified and not output:
            output = f"Lean verification failed with exit code {result.exit_code}"

        return ProofVerificationOutcome(
            verified=verified,
            errors=output if not verified else None,
            output=output if verified else None,
        )
