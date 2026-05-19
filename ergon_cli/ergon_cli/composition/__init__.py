"""Build Experiment from CLI args using registry lookups."""

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.registry import registry
from ergon_core.api.rubric import Evaluator
from ergon_core.core.domain.experiments import Experiment, WorkerSpec
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

    benchmark = _construct_benchmark(benchmark_cls, workflow=workflow, limit=limit)
    evaluator = evaluator_cls(name="evaluator")

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

    spec = WorkerSpec(worker_slug=worker_slug, name="worker", model=model)
    return Experiment.from_single_worker(
        benchmark=benchmark,
        worker=spec,
        evaluators={"default": evaluator},
    )


def _is_smoke_worker(worker_slug: str) -> bool:
    """Match any parent smoke worker: ``{env}-smoke-worker`` or
    ``{env}-sadpath-smoke-worker``."""
    return worker_slug.endswith("-smoke-worker") or worker_slug.endswith(
        "-sadpath-smoke-worker",
    )


def _build_smoke_experiment(
    *,
    benchmark: Benchmark,
    evaluator: Evaluator,
    worker_slug: str,
    model: str,
) -> Experiment:
    """Smoke composition: register parent + leaf(s) as experiment workers.

    The parent worker is assigned to all benchmark tasks (single static
    assignment).  Leaf worker slugs are registered as sub-worker
    bindings only — dynamic subtasks spawned by the parent resolve them
    at runtime via ``ExperimentDefinitionWorker`` lookup in
    ``task_execution_service._prepare_graph_native``.
    """
    # reason: optional test-support smoke fixtures; imported only for smoke compositions.
    from tests.fixtures.smoke_components.criteria.timing import (
        SmokePostRootTimingRubric,
    )

    parent_name = "parent"
    parent_spec = WorkerSpec(worker_slug=worker_slug, name=parent_name, model=model)

    # Infer which leaves this parent needs.  ``{env}-smoke-worker`` needs
    # ``{env}-smoke-leaf``.  ``{env}-sadpath-smoke-worker`` additionally
    # needs ``{env}-smoke-leaf-failing`` (for l_2 routing).
    leaf_slugs: list[str] = []
    if worker_slug.endswith("-sadpath-smoke-worker"):
        env = worker_slug.removesuffix("-sadpath-smoke-worker")
        # Sad-path parent's ``leaf_slug`` attribute is the happy leaf;
        # its ``FAILING_LEAF_SLUG`` is the second binding.
        leaf_slugs.append(f"{env}-smoke-leaf")
        leaf_slugs.append(f"{env}-smoke-leaf-failing")
    elif worker_slug.endswith("-smoke-worker"):
        env = worker_slug.removesuffix("-smoke-worker")
        leaf_slugs.append(f"{env}-smoke-leaf")
        leaf_slugs.append(f"{env}-smoke-recursive-worker")

    # Best-effort sanity: skip unregistered leaf slugs rather than
    # failing fast — an operator invoking an env without the fixture
    # hook imported will see the ``ConfigurationError`` from the
    # runtime (clearer stack) than a composition-time
    # ``KeyError: {env}-smoke-leaf``.
    leaf_slugs = [slug for slug in leaf_slugs if slug in registry.workers]

    workers: dict[str, WorkerSpec] = {parent_name: parent_spec}
    for leaf_slug in leaf_slugs:
        workers[leaf_slug] = WorkerSpec(
            worker_slug=leaf_slug,
            name=leaf_slug,
            model=model,
        )

    # Collect static task slugs so we can explicitly assign the parent
    # worker.  The persistence service only auto-assigns when there is
    # exactly one worker; with 2+ workers we must pass ``assignments``.
    instances = benchmark.build_instances()
    all_task_slugs = [task.task_slug for tasks in instances.values() for task in tasks]

    return Experiment(
        benchmark=benchmark,
        workers=workers,
        evaluators={
            "default": evaluator,
            "post-root": SmokePostRootTimingRubric(name="post-root"),
        },
        assignments={parent_name: all_task_slugs},
    )


def _build_researchrubrics_workflow_experiment(
    *,
    benchmark: Benchmark,
    evaluator: Evaluator,
    model: str,
) -> Experiment:
    """Register CLI-manager plus child worker bindings for dynamic subtasks."""
    manager_name = "manager"
    workers = {
        manager_name: WorkerSpec(
            worker_slug="researchrubrics-workflow-cli-react",
            name=manager_name,
            model=model,
        ),
        "researchrubrics-workflow-cli-react": WorkerSpec(
            worker_slug="researchrubrics-workflow-cli-react",
            name="researchrubrics-workflow-cli-react",
            model=model,
        ),
        "researchrubrics-researcher": WorkerSpec(
            worker_slug="researchrubrics-researcher",
            name="researchrubrics-researcher",
            model=model,
        ),
    }
    instances = benchmark.build_instances()
    all_task_slugs = [task.task_slug for tasks in instances.values() for task in tasks]
    evaluators = {"default": evaluator}
    if "post-root" in benchmark.evaluator_requirements():
        # reason: optional test-support smoke fixtures; imported only when requested.
        from tests.fixtures.smoke_components.criteria.timing import (
            SmokePostRootTimingRubric,
        )

        evaluators["post-root"] = SmokePostRootTimingRubric(name="post-root")

    return Experiment(
        benchmark=benchmark,
        workers=workers,
        evaluators=evaluators,
        assignments={manager_name: all_task_slugs},
    )


def _construct_benchmark(cls: type[Benchmark], workflow: str, limit: int | None) -> Benchmark:
    """Try constructing with all kwargs, progressively dropping unsupported ones.

    Benchmark subclasses define their own ``__init__`` signatures; we
    duck-type the constructor at runtime and catch ``TypeError`` to
    handle subclasses that don't accept these kwargs. The type checker
    can't see beyond ``Benchmark.__init__``, so the calls below carry
    ``# ty: ignore`` — the try/except is the real safety net.
    """
    kwargs: dict[str, str | int] = {}
    if limit is not None:
        kwargs["limit"] = limit

    # Try with workflow + limit
    try:
        return cls(workflow=workflow, **kwargs)  # ty: ignore[unknown-argument]
    except TypeError:
        pass  # slopcop: ignore[no-pass-except]

    # Try with just limit (no workflow)
    try:
        return cls(**kwargs)  # ty: ignore[unknown-argument]
    except TypeError:
        pass  # slopcop: ignore[no-pass-except]

    # Bare constructor
    return cls()
