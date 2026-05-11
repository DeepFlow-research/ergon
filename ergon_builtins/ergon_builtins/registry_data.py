"""Components that require the [data] capability (pandas, datasets, HF hub).

Eager, fully-typed imports.
"""

from ergon_core.api import Benchmark, Worker
from ergon_core.api.rubric import Evaluator

from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark
from ergon_builtins.benchmarks.gdpeval.worker_factory import GDPEvalReactWorker
from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.vanilla import (
    ResearchRubricsVanillaBenchmark,
)
from ergon_builtins.benchmarks.researchrubrics.worker_factory import (
    ResearchRubricsResearcherWorker,
)
from ergon_builtins.benchmarks.researchrubrics.worker_factory import (
    ResearchRubricsWorkflowCliReActWorker,
)

BENCHMARKS: dict[str, type[Benchmark]] = {
    "gdpeval": GDPEvalBenchmark,
    "researchrubrics": ResearchRubricsBenchmark,
    "researchrubrics-vanilla": ResearchRubricsVanillaBenchmark,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "research-rubric": ResearchRubricsRubric,
    "researchrubrics-rubric": ResearchRubricsRubric,
}

WORKERS: dict[str, type[Worker]] = {
    "gdpeval-react": GDPEvalReactWorker,
    "researchrubrics-researcher": ResearchRubricsResearcherWorker,
    "researchrubrics-workflow-cli-react": ResearchRubricsWorkflowCliReActWorker,
}

def register_data_builtins() -> None:
    """Compatibility hook for model/backend registration parity."""
