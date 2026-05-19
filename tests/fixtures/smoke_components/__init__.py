"""Test-only smoke component registration."""

from ergon_core.api.registry import ComponentCatalog, registry
from tests.fixtures.smoke_components.benchmarks import (
    GDPEvalSmokeBenchmark,
    MiniF2FSmokeBenchmark,
    ResearchRubricsSmokeBenchmark,
    SweBenchSmokeBenchmark,
)
from tests.fixtures.smoke_components.criteria.smoke_rubrics import (
    MiniF2FSmokeRubric,
    ResearchRubricsSmokeRubric,
    SweBenchSmokeRubric,
)
from tests.fixtures.smoke_components.criteria.timing import SmokePostRootTimingRubric
from tests.fixtures.smoke_components.sandbox import SmokeSandboxManager
from tests.fixtures.smoke_components.workers.minif2f_smoke import (
    MiniF2FFailingLeafWorker,
    MiniF2FRecursiveSmokeWorker,
    MiniF2FSadPathSmokeWorker,
    MiniF2FSmokeLeafWorker,
    MiniF2FSmokeWorker,
)
from tests.fixtures.smoke_components.workers.researchrubrics_smoke import (
    ResearchRubricsFailingLeafWorker,
    ResearchRubricsRecursiveSmokeWorker,
    ResearchRubricsSadPathSmokeWorker,
    ResearchRubricsSmokeLeafWorker,
    ResearchRubricsSmokeWorker,
)
from tests.fixtures.smoke_components.workers.swebench_smoke import (
    SweBenchFailingLeafWorker,
    SweBenchRecursiveSmokeWorker,
    SweBenchSadPathSmokeWorker,
    SweBenchSmokeLeafWorker,
    SweBenchSmokeWorker,
)


def register_smoke_fixtures(target: ComponentCatalog = registry) -> None:
    """Register smoke-only benchmark, worker, evaluator, and sandbox slugs."""

    # Production benchmark loaders fetch external datasets. The smoke harness
    # owns its benchmark roots so CI stays deterministic and offline whenever
    # this explicit test bootstrap is called.
    for benchmark_cls in (
        ResearchRubricsSmokeBenchmark,
        MiniF2FSmokeBenchmark,
        SweBenchSmokeBenchmark,
        GDPEvalSmokeBenchmark,
    ):
        target.deregister("benchmark", benchmark_cls.type_slug)
        target.register_benchmark(benchmark_cls)
        target.deregister("sandbox_manager", benchmark_cls.type_slug)
        target.register_sandbox_manager(benchmark_cls.type_slug, SmokeSandboxManager)

    # ResearchRubrics happy-path
    target.register_worker(ResearchRubricsSmokeWorker.type_slug, ResearchRubricsSmokeWorker)
    target.register_worker(ResearchRubricsSmokeLeafWorker.type_slug, ResearchRubricsSmokeLeafWorker)
    target.register_worker(
        ResearchRubricsRecursiveSmokeWorker.type_slug,
        ResearchRubricsRecursiveSmokeWorker,
    )
    target.register_evaluator(ResearchRubricsSmokeRubric)
    target.register_evaluator(SmokePostRootTimingRubric)

    # ResearchRubrics sad-path (paired with the happy run in each smoke cohort)
    target.register_worker(
        ResearchRubricsSadPathSmokeWorker.type_slug, ResearchRubricsSadPathSmokeWorker
    )
    target.register_worker(
        ResearchRubricsFailingLeafWorker.type_slug, ResearchRubricsFailingLeafWorker
    )

    # MiniF2F happy + sad-path
    target.register_worker(MiniF2FSmokeWorker.type_slug, MiniF2FSmokeWorker)
    target.register_worker(MiniF2FSmokeLeafWorker.type_slug, MiniF2FSmokeLeafWorker)
    target.register_worker(MiniF2FRecursiveSmokeWorker.type_slug, MiniF2FRecursiveSmokeWorker)
    target.register_worker(MiniF2FSadPathSmokeWorker.type_slug, MiniF2FSadPathSmokeWorker)
    target.register_worker(MiniF2FFailingLeafWorker.type_slug, MiniF2FFailingLeafWorker)
    target.register_evaluator(MiniF2FSmokeRubric)

    # SWE-Bench Verified happy + sad-path
    target.register_worker(SweBenchSmokeWorker.type_slug, SweBenchSmokeWorker)
    target.register_worker(SweBenchSmokeLeafWorker.type_slug, SweBenchSmokeLeafWorker)
    target.register_worker(SweBenchRecursiveSmokeWorker.type_slug, SweBenchRecursiveSmokeWorker)
    target.register_worker(SweBenchSadPathSmokeWorker.type_slug, SweBenchSadPathSmokeWorker)
    target.register_worker(SweBenchFailingLeafWorker.type_slug, SweBenchFailingLeafWorker)
    target.register_evaluator(SweBenchSmokeRubric)


register_smoke_components = register_smoke_fixtures
