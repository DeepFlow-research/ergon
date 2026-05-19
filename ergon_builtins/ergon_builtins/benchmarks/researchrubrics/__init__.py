"""ResearchRubrics benchmark for studying adaptive stakeholder querying."""

# ResearchRubricsBenchmark is intentionally NOT re-exported here.
# benchmark.py imports ResearchE2BSandbox from
# ergon_builtins.benchmarks.researchrubrics.sandbox, and sandbox.py
# imports ResearchRubricsSandboxManager from this package.  Eagerly re-
# exporting ResearchRubricsBenchmark would complete a cycle:
#   benchmarks/researchrubrics/sandbox.py → benchmarks.researchrubrics (here)
#   → benchmark.py → benchmarks/researchrubrics/sandbox.py
# All call sites that need ResearchRubricsBenchmark import it directly:
#   from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)

__all__ = [
    "ResearchRubricsRubric",
    "ResearchRubricsTaskPayload",
    "RubricCriterion",
]
