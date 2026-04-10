"""MiniF2F-specific criterion configurations.

Provides a factory for the default proof-verification criterion used
by the MiniF2F rubric.
"""

from arcane_builtins.benchmarks.minif2f.rules.proof_verification import (
    ProofVerificationCriterion,
)

def build_proof_criterion(
    *,
    max_score: float = 1.0,
    problem_statement: str | None = None,
    ground_truth_proof: str | None = None,
) -> ProofVerificationCriterion:
    """Create the default proof-verification criterion for MiniF2F.

    Parameters
    ----------
    max_score:
        Maximum score awarded for a fully verified proof.
    problem_statement:
        Optional theorem statement override.
    ground_truth_proof:
        Ground-truth proof text (for reference only, not used in grading).
    """
    return ProofVerificationCriterion(
        name="proof_verification",
        weight=1.0,
        max_score=max_score,
        problem_statement=problem_statement,
        ground_truth_proof=ground_truth_proof,
    )
