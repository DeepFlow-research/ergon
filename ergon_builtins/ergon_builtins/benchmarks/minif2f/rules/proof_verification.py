"""Proof-verification criterion for formal mathematics (Lean).

Extracts the agent's ``final_solution.lean`` from the task's
run-resources (published by ``SandboxResourcePublisher.sync()`` after the
worker writes to ``/workspace/final_output/final_solution.lean``),
writes it into the sandbox, and invokes the Lean compiler to verify the
proof.
"""

from typing import ClassVar

from ergon_core.api.criterion import Criterion
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import CriterionResult
from pydantic import BaseModel

from ergon_builtins.benchmarks.minif2f.constants import LEAN_CMD, LEAN_CMD_PREFIX

VERIFY_LEAN_CMD = f"{LEAN_CMD_PREFIX} {LEAN_CMD} src/verify.lean 2>&1"


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
    1. Read ``final_solution.lean`` as a run-resource via
       ``context.runtime.read_resource``
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
        proof_data = await self._extract_proof(context)
        if proof_data is None:
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback=(
                    "No final_solution.lean run-resource published for this task. "
                    "The worker must write to /workspace/final_output/final_solution.lean "
                    "so SandboxResourcePublisher.sync picks it up."
                ),
                metadata={"evaluated_resource_ids": []},
            )
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

    async def _extract_proof(self, context: EvaluationContext) -> ExtractedProof | None:
        """Read the Lean source the agent wrote, or ``None`` if missing.

        Reads from the task-scoped run-resource named
        ``final_solution.lean`` -- published by
        ``SandboxResourcePublisher.sync()`` after the worker writes to
        ``/workspace/final_output/final_solution.lean``.  The pre-RFC
        path through ``worker_result.artifacts`` is not used:
        ``artifacts`` is dropped at the Inngest ``worker_execute``
        boundary, so reading from it was always dead code masked by the
        now-deleted ``MiniF2FAdapter.transform_output``.
        """
        if context.runtime is None:
            return None
        # reason: ResourceNotFoundError is a ``core`` symbol and importing
        # it at module scope would pull runtime internals into a builtins
        # package. Lazy-import at the single call site.
        from ergon_core.core.runtime.evaluation.criterion_runtime import (
            ResourceNotFoundError,
        )

        try:
            raw = await context.runtime.read_resource("final_solution.lean")
        except ResourceNotFoundError:
            return None
        return ExtractedProof(
            proof_code=raw.decode("utf-8", errors="replace"),
            source="run_resource:final_solution.lean",
            evaluated_resource_ids=[],
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

        result = await runtime.run_command(VERIFY_LEAN_CMD, timeout=120)

        output = (result.stdout or "") + (result.stderr or "")
        verified = result.exit_code == 0
        if not verified and not output:
            output = f"Lean verification failed with exit code {result.exit_code}"

        return ProofVerificationOutcome(
            verified=verified,
            errors=output if not verified else None,
            output=output if verified else None,
        )
