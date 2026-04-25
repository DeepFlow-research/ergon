"""Build Experiment from CLI args using registry lookups."""

from ergon_core.api.experiment import Experiment
from ergon_core.api.worker_spec import WorkerSpec


def build_experiment(
    benchmark_slug: str,
    model: str,
    worker_slug: str = "training-stub",
    evaluator_slug: str = "stub-rubric",
    workflow: str = "single",
    limit: int | None = None,
) -> Experiment:
    # Deferred: CLI startup cost
    from ergon_builtins.registry import BENCHMARKS, EVALUATORS, WORKERS

    if worker_slug not in WORKERS:
        raise KeyError(worker_slug)
    benchmark_cls = BENCHMARKS[benchmark_slug]
    evaluator_cls = EVALUATORS[evaluator_slug]

    benchmark = _construct_benchmark(benchmark_cls, workflow=workflow, limit=limit)
    evaluator = evaluator_cls(name="evaluator")

    # Smoke-worker composition: the parent worker spawns 9 subtasks via
    # ``add_subtask(assigned_worker_slug="{env}-smoke-leaf")``, so the
    # experiment must also carry a binding for that leaf slug —
    # otherwise ``task_execution_service._prepare_graph_native`` will
    # raise ``ConfigurationError: No ExperimentDefinitionWorker with
    # binding_key='{env}-smoke-leaf'`` when the first subtask fires.
    # ``researchrubrics-sadpath-smoke-worker`` additionally needs the
    # failing leaf binding so ``l_2`` can resolve.
    if _is_smoke_worker(worker_slug):
        return _build_smoke_experiment(
            benchmark=benchmark,
            evaluator=evaluator,
            worker_slug=worker_slug,
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
    benchmark,
    evaluator,
    worker_slug: str,
    model: str,
):
    """Smoke composition: register parent + leaf(s) as experiment workers.

    The parent worker is assigned to all benchmark tasks (single static
    assignment).  Leaf worker slugs are registered as sub-worker
    bindings only — dynamic subtasks spawned by the parent resolve them
    at runtime via ``ExperimentDefinitionWorker`` lookup in
    ``task_execution_service._prepare_graph_native``.
    """
    # reason: deferred import keeps CLI startup cost on the hot path low
    # (matches the pattern at the top of ``build_experiment``).
    from ergon_builtins.registry import WORKERS

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

    # Best-effort sanity: skip unregistered leaf slugs rather than
    # failing fast — an operator invoking an env without the fixture
    # hook imported will see the ``ConfigurationError`` from the
    # runtime (clearer stack) than a composition-time
    # ``KeyError: {env}-smoke-leaf``.
    leaf_slugs = [slug for slug in leaf_slugs if slug in WORKERS]

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
        evaluators={"default": evaluator},
        assignments={parent_name: all_task_slugs},
    )


def _construct_benchmark(cls, workflow: str, limit: int | None):
    """Try constructing with all kwargs, progressively dropping unsupported ones."""
    kwargs: dict[str, str | int] = {}
    if limit is not None:
        kwargs["limit"] = limit

    # Try with workflow + limit
    try:
        return cls(workflow=workflow, **kwargs)
    except TypeError:
        pass  # slopcop: ignore[no-pass-except]

    # Try with just limit (no workflow)
    try:
        return cls(**kwargs)
    except TypeError:
        pass  # slopcop: ignore[no-pass-except]

    # Bare constructor
    return cls()
