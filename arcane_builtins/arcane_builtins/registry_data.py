"""Components that require the [data] capability (pandas, datasets, HF hub).

Eager, fully-typed imports.
"""

from h_arcane.api import Benchmark, Evaluator

from arcane_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark
from arcane_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from arcane_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric

BENCHMARKS: dict[str, type[Benchmark]] = {
    "gdpeval": GDPEvalBenchmark,
    "researchrubrics": ResearchRubricsBenchmark,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "research-rubric": ResearchRubricsRubric,
}
