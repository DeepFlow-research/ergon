"""Proof verification rule for formal math (Lean)."""

from typing import Literal, TYPE_CHECKING

from pydantic import Field

from h_arcane.evaluation.rules.base import BaseRule
from h_arcane.db.models import CriterionResult

if TYPE_CHECKING:
    from h_arcane.evaluation.context import EvaluationRunner


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

        # Step 1: Ensure sandbox exists
        await runner.step("ensure-sandbox", runner.ensure_sandbox)

        # Step 2: Install Lean (cached per sandbox)
        async def install_lean():
            from h_arcane.tools.formal_math.utils import ensure_lean_installed

            sandbox = runner.sandbox_manager.get_sandbox(data.run_id)
            if not sandbox:
                raise RuntimeError("Sandbox not created")
            success = await ensure_lean_installed(sandbox)
            return {"installed": success}

        lean_status = await runner.step("install-lean", install_lean)
        if not lean_status["installed"]:
            return CriterionResult(
                run_id=data.run_id,
                stage_num=data.stage_idx,
                stage_name=data.stage_name,
                criterion_num=data.rule_idx,
                criterion_type="proof_verification",
                criterion_description=self.description,
                score=0.0,
                max_score=data.max_score,
                feedback="Lean installation failed. Cannot verify proof.",
                evaluation_input="",
                evaluated_action_ids=[],
                evaluated_resource_ids=[],
            )

        # Step 3: Extract proof from agent output
        async def extract_proof():
            # Look for .lean files in agent outputs
            lean_files = [r for r in data.agent_outputs if r.name.endswith(".lean")]

            if not lean_files:
                raise ValueError(
                    "No .lean file found in agent outputs. "
                    "The worker must write a .lean file as the final output for evaluation."
                )

            # Use the first .lean file found
            lean_file = lean_files[0]
            proof_code = lean_file.load_text()
            return {
                "proof_code": proof_code,
                "source": f"file:{lean_file.name}",
                "evaluated_resource_ids": [str(lean_file.id)],
            }

        proof_data = await runner.step("extract-proof", extract_proof)
        proof_code = proof_data["proof_code"]

        # Combine with problem statement
        full_code = f"""{self.problem_statement}

-- Agent's proof:
{proof_code}
"""

        # Step 4: Verify proof
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

            # Write proof to temporary file in sandbox
            await sandbox.files.write("/workspace/verify.lean", full_code.encode("utf-8"))

            # Run Lean compiler with --check flag
            result = await sandbox.commands.run(
                "export PATH=$HOME/.elan/bin:$PATH && cd /workspace && lean --check verify.lean 2>&1",
                timeout=60,
            )

            output = (result.stdout or "") + (result.stderr or "")
            verified = result.exit_code == 0

            return {
                "verified": verified,
                "errors": output if not verified else None,
                "output": output if verified else None,
            }

        verify_result = await runner.step("verify-proof", verify_proof)

        # Step 5: Compute score
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
            evaluation_input=full_code,
            evaluated_action_ids=[],
            evaluated_resource_ids=proof_data["evaluated_resource_ids"],
        )
