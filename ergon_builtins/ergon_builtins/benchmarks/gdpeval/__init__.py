"""GDPEval benchmark — document-processing evaluation with staged rubrics."""

from arcane_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark
from arcane_builtins.benchmarks.gdpeval.rubric import EvaluationStage, StagedRubric
from arcane_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager

__all__ = [
    "GDPEvalBenchmark",
    "EvaluationStage",
    "StagedRubric",
    "GDPEvalSandboxManager",
]
