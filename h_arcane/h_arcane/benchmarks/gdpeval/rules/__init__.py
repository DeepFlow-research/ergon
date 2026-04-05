"""GDPEval evaluation rules."""

from h_arcane.core._internal.evaluation.rules import CodeRule, LLMJudgeRule

GDPEvalRule = CodeRule | LLMJudgeRule

__all__ = ["GDPEvalRule"]
