"""Proof verification rule for formal math (Lean)."""

from typing import Literal, TYPE_CHECKING

from e2b.sandbox.commands.command_handle import CommandExitException
from pydantic import Field

from h_arcane.core.evaluation.rules.base import BaseRule
from h_arcane.core.db.models import CriterionResult

if TYPE_CHECKING:
    from h_arcane.core.evaluation.context import EvaluationRunner


class ProofVerificationRule(BaseRule):
    """Rule for verifying formal proofs in Lean."""

    type: Literal["proof_verification"] = "proof_verification"
    problem_statement: str = Field(description="The theorem statement to prove")
    ground_truth_proof: str | None = Field(
        default=None,
        description="Ground truth proof (for reference, not used in evaluation)",
    )
    formal_system: Literal["lean"] = Field(
        default="lean",
        description="Formal system used (currently only Lean supported)",
    )

    async def evaluate(self, runner: "EvaluationRunner") -> CriterionResult:
        """Verify Lean proof with granular Inngest steps."""
        data = runner.data

        # Step 1: Ensure sandbox exists (MiniF2FSandboxManager installs Lean during create())
        await runner.step("ensure-sandbox", runner.ensure_sandbox)

        # Step 2: Extract proof from agent output
        async def extract_proof():
            # Look specifically for final_solution.lean - the required submission file
            final_solution = next(
                (r for r in data.agent_outputs if r.name == "final_solution.lean"),
                None,
            )

            if not final_solution:
                # Provide helpful error message listing what files were found
                other_lean_files = [r.name for r in data.agent_outputs if r.name.endswith(".lean")]
                if other_lean_files:
                    files_list = ", ".join(other_lean_files)
                    raise ValueError(
                        f"No 'final_solution.lean' found. "
                        f"Found other .lean files: [{files_list}]. "
                        f"The worker must write their final proof to 'final_solution.lean' for evaluation."
                    )
                else:
                    raise ValueError(
                        "No 'final_solution.lean' found in agent outputs. "
                        "The worker must write their final proof to 'final_solution.lean' for evaluation."
                    )

            proof_code = final_solution.load_text()
            return {
                "proof_code": proof_code,
                "source": "file:final_solution.lean",
                "evaluated_resource_ids": [str(final_solution.id)],
            }

        proof_data = await runner.step("extract-proof", extract_proof)
        proof_code = proof_data["proof_code"]

        # Agent's file is already a complete valid Lean file with imports.
        # We verify it directly - don't prepend the theorem statement as that
        # would put imports after the theorem (invalid Lean syntax).
        # The problem_statement is kept for logging/evaluation_input only.
        full_code = proof_code

        # For evaluation_input logging, show what was expected vs what agent wrote
        evaluation_log = f"""-- Expected theorem:
-- {self.problem_statement.replace(chr(10), chr(10) + "-- ")}

-- Agent's proof file:
{proof_code}
"""

        # Step 3: Verify proof
        async def verify_proof():
            sandbox = runner.sandbox_manager.get_sandbox(data.run_id)
            if not sandbox:
                raise RuntimeError("Sandbox not created")

            # Check for sorry - not allowed in final verification
            if "sorry" in proof_code:
                return {
                    "verified": False,
                    "errors": "Proof contains 'sorry' - incomplete proof not allowed",
                    "output": None,
                }

            # Write proof to Mathlib project src directory so imports resolve
            await sandbox.files.write(
                "/tools/mathlib_project/src/verify.lean", full_code.encode("utf-8")
            )

            # Run Lean from within the Mathlib project so it can find Mathlib imports
            try:
                result = await sandbox.commands.run(
                    "export PATH=$HOME/.elan/bin:$PATH && cd /tools/mathlib_project && lean src/verify.lean 2>&1",
                    timeout=120,  # May need longer for compilation with Mathlib
                )
                output = (result.stdout or "") + (result.stderr or "")
                verified = result.exit_code == 0

            except CommandExitException as e:
                # Command failed (non-zero exit code) - this is expected when proof is invalid
                output = (e.stdout or "") + (e.stderr or "")
                if not output:
                    output = f"Lean verification failed with exit code {e.exit_code}"
                verified = False

            return {
                "verified": verified,
                "errors": output if not verified else None,
                "output": output if verified else None,
            }

        verify_result = await runner.step("verify-proof", verify_proof)

        # Step 4: Compute score
        score = data.max_score if verify_result["verified"] else 0.0
        feedback = (
            "Proof successfully verified by Lean compiler."
            if verify_result["verified"]
            else f"Proof verification failed:\n{verify_result.get('errors', 'Unknown error')}"
        )

        return CriterionResult(
            run_id=data.run_id,
            stage_num=data.stage_idx,
            stage_name=data.stage_name,
            criterion_num=data.rule_idx,
            criterion_type="proof_verification",
            criterion_description=self.description,
            score=score,
            max_score=data.max_score,
            feedback=feedback,
            evaluation_input=evaluation_log,
            evaluated_action_ids=[],
            evaluated_resource_ids=proof_data["evaluated_resource_ids"],
        )
