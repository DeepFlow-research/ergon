"""Build Experiment from CLI args using explicit builtins maps."""

from ergon_core.api import Experiment
from ergon_builtins.registry_core import (
    BENCHMARKS as CORE_BENCHMARKS,
    EVALUATORS as CORE_EVALUATORS,
    WORKERS as CORE_WORKERS,
)


def build_experiment(
    benchmark_slug: str,
    model: str,
    worker_slug: str = "training-stub",
    evaluator_slug: str = "stub-rubric",
    workflow: str = "single",
    limit: int | None = None,
) -> Experiment:
    benchmarks = dict(CORE_BENCHMARKS)
    evaluators = dict(CORE_EVALUATORS)
    workers = dict(CORE_WORKERS)
    try:
        from ergon_builtins.registry_data import (
            BENCHMARKS as DATA_BENCHMARKS,
            EVALUATORS as DATA_EVALUATORS,
            WORKERS as DATA_WORKERS,
        )
    except ImportError:
        pass
    else:
        benchmarks.update(DATA_BENCHMARKS)
        evaluators.update(DATA_EVALUATORS)
        workers.update(DATA_WORKERS)

    if worker_slug not in workers:
        raise KeyError(worker_slug)
    benchmark_cls = benchmarks[benchmark_slug]
    evaluator_cls = evaluators[evaluator_slug]
    worker_cls = workers[worker_slug]

    evaluator = evaluator_cls(name="default")
    worker = worker_cls(name="worker", model=model)
    benchmark = _construct_benchmark(
        benchmark_cls,
        workflow=workflow,
        limit=limit,
        worker=worker,
        evaluators=(evaluator,),
    )

    # Smoke-worker composition: the parent worker spawns 9 subtasks via
    # ``add_subtask(assigned_worker_slug="{env}-smoke-leaf")``, so the
    # experiment must also carry a binding for that leaf slug —
    # object-bound tasks must carry the extra smoke evaluators at benchmark
    # construction time.
    # Happy smoke parents additionally route top-level ``l_2`` to
    # ``{env}-smoke-recursive-worker`` so dependency propagation waits on
    # a non-leaf dynamic task. ``{env}-sadpath-smoke-worker`` instead needs
    # the failing leaf binding so ``l_2`` can resolve.
    if _is_smoke_worker(worker_slug):
        return _build_smoke_experiment(
            benchmark=benchmark,
            evaluator=evaluator,
            worker_slug=worker_slug,
            model=model,
        )
    if worker_slug == "researchrubrics-workflow-cli-react":
        return _build_researchrubrics_workflow_experiment(
            benchmark=benchmark,
            evaluator=evaluator,
            model=model,
        )

    return Experiment(benchmark=benchmark)


def _is_smoke_worker(worker_slug: str) -> bool:
    """Match any parent smoke worker: ``{env}-smoke-worker`` or
    ``{env}-sadpath-smoke-worker``."""
    return worker_slug.endswith("-smoke-worker") or worker_slug.endswith(
        "-sadpath-smoke-worker",
    )


def _build_smoke_experiment(
    *,
    benchmark,
    evaluator,
    worker_slug: str,
    model: str,
):
    """Smoke composition for object-bound benchmark tasks."""
    # reason: optional test-support smoke fixtures; imported only for smoke compositions.
    from tests.fixtures.smoke_components.criteria.timing import (
        SmokePostRootTimingRubric,
    )

    if hasattr(benchmark, "evaluators"):
        benchmark.evaluators = (evaluator, SmokePostRootTimingRubric(name="post-root"))
    return Experiment(benchmark=benchmark)


def _build_researchrubrics_workflow_experiment(
    *,
    benchmark,
    evaluator,
    model: str,
):
    """Build workflow experiment with benchmark-owned task bindings."""
    evaluators = [evaluator]
    if "post-root" in benchmark.evaluator_requirements():
        # reason: optional test-support smoke fixtures; imported only when requested.
        from tests.fixtures.smoke_components.criteria.timing import (
            SmokePostRootTimingRubric,
        )

        evaluators.append(SmokePostRootTimingRubric(name="post-root"))
    if hasattr(benchmark, "evaluators"):
        benchmark.evaluators = tuple(evaluators)

    return Experiment(benchmark=benchmark)


def _construct_benchmark(cls, workflow: str, limit: int | None, **overrides):
    """Try constructing with all kwargs, progressively dropping unsupported ones."""
    kwargs: dict[str, str | int] = {}
    if limit is not None:
        kwargs["limit"] = limit

    # Try with workflow + limit
    try:
        return cls(workflow=workflow, **kwargs, **overrides)
    except TypeError:
        pass  # slopcop: ignore[no-pass-except]

    # Try with just limit (no workflow)
    try:
        return cls(**kwargs, **overrides)
    except TypeError:
        pass  # slopcop: ignore[no-pass-except]

    # Bare constructor
    return cls(**overrides)
