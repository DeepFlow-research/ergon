"""Components that require the [data] capability (pandas, datasets, HF hub).

Eager, fully-typed imports.
"""

from collections.abc import Callable

from ergon_core.api import Benchmark, Evaluator, Worker

from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark
from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.vanilla import (
    ResearchRubricsVanillaBenchmark,
)
from ergon_builtins.registry_core import _plain
from ergon_builtins.workers.research_rubrics.manager_worker import (
    ResearchRubricsManagerWorker,
)
from ergon_builtins.workers.research_rubrics.researcher_worker import (
    ResearchRubricsResearcherWorker,
)

BENCHMARKS: dict[str, type[Benchmark]] = {
    "gdpeval": GDPEvalBenchmark,
    "researchrubrics": ResearchRubricsBenchmark,
    "researchrubrics-ablated": ResearchRubricsBenchmark,
    "researchrubrics-vanilla": ResearchRubricsVanillaBenchmark,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "research-rubric": ResearchRubricsRubric,
}

# Wrap with `_plain` so entries accept the `task_id` / `sandbox_id` kwargs
# that `worker_execute.py` now passes into every factory (RFC 2026-04-22 §1,
# Open Question 1 resolution (a)). Research-rubrics workers don't need the
# sandbox identifiers; `_plain` drops them before forwarding.
WORKERS: dict[str, Callable[..., Worker]] = {
    "researchrubrics-manager": _plain(ResearchRubricsManagerWorker),
    "researchrubrics-researcher": _plain(ResearchRubricsResearcherWorker),
}
