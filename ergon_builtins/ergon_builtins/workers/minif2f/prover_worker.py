"""Lean prover sub-agent for the MiniF2F manager+prover demo.

Mirrors ``MiniF2FReActWorker`` — same MiniF2F toolkit, same final-proof
capture via ``/workspace/final_output/final_solution.lean`` — but with
a system prompt framed for a sub-agent working on a manager-assigned
theorem.  Kept as a subclass so any future toolkit/extraction change
flows to both workers.
"""

from typing import ClassVar

from ergon_builtins.workers.baselines.minif2f_react_worker import MiniF2FReActWorker

_PROVER_SYSTEM_PROMPT = (
    "You are a Lean 4 prover sub-agent spawned by a manager. Prove the "
    "theorem the manager assigned you and write a single, verified proof.\n\n"
    "Workflow:\n"
    "1. Call write_lean_file to save a candidate proof to "
    "/workspace/scratchpad/draft.lean. Use 'sorry' as a placeholder while "
    "iterating.\n"
    "2. Call check_lean_file to see compilation errors and remaining goals.\n"
    "3. Iterate until the proof has no 'sorry' and no errors.\n"
    "4. Write the final proof to /workspace/final_output/final_solution.lean "
    "and call verify_lean_proof to confirm the Lean kernel accepts it.\n\n"
    "Always import Mathlib at the top. Keep proofs short — for trivial "
    "goals 'by decide', 'by rfl', 'by norm_num', or 'by simp' usually suffice."
)


class MiniF2FProverWorker(MiniF2FReActWorker):
    """Prover sub-agent for the MiniF2F demo.

    Functionally identical to :class:`MiniF2FReActWorker`; distinguished by
    slug so the CLI composition can bind it under a dedicated binding key.
    """

    type_slug: ClassVar[str] = "minif2f-prover"

    def __init__(
        self,
        *,
        name: str = "minif2f-prover",
        model: str | None = None,
        max_iterations: int = 20,
    ) -> None:
        super().__init__(
            name=name,
            model=model,
            system_prompt=_PROVER_SYSTEM_PROMPT,
            max_iterations=max_iterations,
        )
