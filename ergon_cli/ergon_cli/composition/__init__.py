"""Build Experiment from CLI args using registry lookups."""

from ergon_core.api import Experiment
from ergon_core.api.registry import registry
from ergon_builtins.registry import register_builtins


def build_experiment(
    benchmark_slug: str,
    model: str,
    worker_slug: str = "training-stub",
    evaluator_slug: str = "stub-rubric",
    workflow: str = "single",
    limit: int | None = None,
) -> Experiment:

    if (
        worker_slug not in registry.workers
        or benchmark_slug not in registry.benchmarks
        or evaluator_slug not in registry.evaluators
    ):
        register_builtins(registry)
    if worker_slug not in registry.workers:
        raise KeyError(worker_slug)
    benchmark_cls = registry.require_benchmark(benchmark_slug)
    evaluator_cls = registry.require_evaluator(evaluator_slug)
    worker_cls = registry.require_worker(worker_slug)

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
    # otherwise ``task_execution_service._prepare_graph_native`` will
    # raise ``ConfigurationError: No ExperimentDefinitionWorker with
    # binding_key='{env}-smoke-leaf'`` when the first subtask fires.
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
