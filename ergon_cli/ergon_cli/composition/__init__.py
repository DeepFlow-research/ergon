"""Build Experiment from CLI args using registry lookups."""

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.evaluator import Evaluator
from ergon_core.api.experiment import Experiment
from ergon_core.api.worker_spec import WorkerSpec


def build_experiment(
    benchmark_slug: str,
    model: str,
    worker_slug: str = "stub-worker",
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

    # Composition is driven by the explicit worker selection.
    match worker_slug:
        case "manager-researcher":
            return _build_manager_researcher_experiment(benchmark, model, evaluator)
        case "researchrubrics-manager":
            return _build_researchrubrics_experiment(benchmark, model, evaluator)
        case _:
            spec = WorkerSpec(worker_slug=worker_slug, name="worker", model=model)
            return Experiment.from_single_worker(
                benchmark=benchmark,
                worker=spec,
                evaluators={"default": evaluator},
            )


def _build_manager_researcher_experiment(
    benchmark: Benchmark,
    model: str,
    evaluator: Evaluator,
) -> Experiment:
    """Build experiment with manager-researcher + researcher for any benchmark.

    The manager-researcher is assigned to all static benchmark tasks.
    The researcher worker is registered as a sub-worker binding only —
    it receives no static task assignments; dynamic tasks spawned by the
    manager via add_subtask() will resolve it via ExperimentDefinitionWorker
    lookup in _prepare_graph_native().
    """
    manager_spec = WorkerSpec(
        worker_slug="manager-researcher", name="manager-researcher", model=model
    )
    researcher_spec = WorkerSpec(worker_slug="researcher", name="researcher", model=model)

    # Collect all task slugs so we can explicitly assign the manager to them.
    # The persistence service only auto-assigns when there is exactly 1 worker;
    # with 2 workers we must provide explicit assignments.
    instances = benchmark.build_instances()
    all_task_slugs = [task.task_slug for tasks in instances.values() for task in tasks]

    return Experiment(
        benchmark=benchmark,
        workers={
            "manager-researcher": manager_spec,
            "researcher": researcher_spec,
        },
        evaluators={"default": evaluator},
        assignments={"manager-researcher": all_task_slugs},
    )


def _build_researchrubrics_experiment(
    benchmark: Benchmark,
    model: str,
    evaluator: Evaluator,
) -> Experiment:
    """Build experiment with researchrubrics-manager + researcher.

    Manager is assigned to all static benchmark tasks.  Researcher is
    registered as a sub-worker binding only -- dynamic tasks spawned by
    the manager via add_subtask() resolve it at runtime.
    """
    manager_spec = WorkerSpec(
        worker_slug="researchrubrics-manager",
        name="researchrubrics-manager",
        model=model,
    )
    researcher_spec = WorkerSpec(
        worker_slug="researchrubrics-researcher",
        name="researchrubrics-researcher",
        model=model,
    )

    instances = benchmark.build_instances()
    all_task_slugs = [task.task_slug for tasks in instances.values() for task in tasks]

    return Experiment(
        benchmark=benchmark,
        workers={
            "researchrubrics-manager": manager_spec,
            "researchrubrics-researcher": researcher_spec,
        },
        evaluators={"default": evaluator},
        assignments={"researchrubrics-manager": all_task_slugs},
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
