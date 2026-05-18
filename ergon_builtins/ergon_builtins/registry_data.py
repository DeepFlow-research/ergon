"""Components that require the [data] capability (pandas, datasets, HF hub).

Eager, fully-typed imports.
"""

from ergon_core.api import Benchmark, Worker
from ergon_core.api.registry import ComponentRegistry, registry
from ergon_core.api.rubric import Evaluator
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager

from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark
from ergon_builtins.benchmarks.gdpeval.worker_factory import GDPEvalReactWorker
from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.sandbox_manager import (
    ResearchRubricsSandboxManager,
)
from ergon_builtins.benchmarks.researchrubrics.vanilla import (
    ResearchRubricsVanillaBenchmark,
)
from ergon_builtins.benchmarks.researchrubrics.workers import (
    ResearchRubricsResearcherWorker,
)
from ergon_builtins.benchmarks.researchrubrics.workers import (
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

SANDBOX_MANAGERS: dict[str, type[BaseSandboxManager]] = {
    "researchrubrics": ResearchRubricsSandboxManager,
    "researchrubrics-vanilla": ResearchRubricsSandboxManager,
}


def register_data_builtins(target: ComponentRegistry = registry) -> None:
    """Register builtins that require the [data] optional dependency group."""

    for benchmark_cls in BENCHMARKS.values():
        target.register_benchmark(benchmark_cls)
    for slug, evaluator_cls in EVALUATORS.items():
        target.register_evaluator(evaluator_cls, slug=slug)
    for slug, worker_factory in WORKERS.items():
        target.register_worker(slug, worker_factory)
    for slug, manager_cls in SANDBOX_MANAGERS.items():
        target.register_sandbox_manager(slug, manager_cls)
