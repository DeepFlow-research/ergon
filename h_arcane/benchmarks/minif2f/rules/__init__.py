"""MiniF2F evaluation rules."""

from h_arcane.core.evaluation.rules import CodeRule, LLMJudgeRule
from h_arcane.benchmarks.minif2f.rules.proof_verification import ProofVerificationRule

MiniF2FRule = CodeRule | LLMJudgeRule | ProofVerificationRule

__all__ = ["ProofVerificationRule", "MiniF2FRule"]
