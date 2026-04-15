"""Build Experiment from CLI args using registry lookups."""

from collections.abc import Mapping

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.evaluator import Evaluator
from ergon_core.api.experiment import Experiment
from ergon_core.api.worker import Worker


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

    benchmark_cls = BENCHMARKS[benchmark_slug]
    worker_cls = WORKERS[worker_slug]
    evaluator_cls = EVALUATORS[evaluator_slug]

    benchmark = _construct_benchmark(benchmark_cls, workflow=workflow, limit=limit)
    evaluator = evaluator_cls(name="evaluator")

    if benchmark_slug == "delegation-smoke":
        return _build_delegation_experiment(benchmark, model, evaluator, WORKERS)

    if benchmark_slug.startswith("researchrubrics-"):
        return _build_researchrubrics_experiment(benchmark, model, evaluator, WORKERS)

    if worker_slug == "manager-researcher":
        return _build_manager_researcher_experiment(benchmark, model, evaluator, WORKERS)

    worker = worker_cls(name="worker", model=model)
    return Experiment.from_single_worker(
        benchmark=benchmark,
        worker=worker,
        evaluators={"default": evaluator},
    )


def _build_manager_researcher_experiment(
    benchmark: Benchmark,
    model: str,
    evaluator: Evaluator,
    workers_registry: Mapping[str, type[Worker]],
) -> Experiment:
    """Build experiment with manager-researcher + researcher for any benchmark.

    The manager-researcher is assigned to all static benchmark tasks.
    The researcher worker is registered as a sub-worker binding only —
    it receives no static task assignments; dynamic tasks spawned by the
    manager via add_task() will resolve it via ExperimentDefinitionWorker
    lookup in _prepare_graph_native().
    """
    manager_cls = workers_registry["manager-researcher"]
    researcher_cls = workers_registry["researcher"]

    manager = manager_cls(name="manager-researcher", model=model)
    researcher = researcher_cls(name="researcher", model=model)

    # Collect all task keys so we can explicitly assign the manager to them.
    # The persistence service only auto-assigns when there is exactly 1 worker;
    # with 2 workers we must provide explicit assignments.
    instances = benchmark.build_instances()
    all_task_keys = [task.task_key for tasks in instances.values() for task in tasks]

    return Experiment(
        benchmark=benchmark,
        workers={
            "manager-researcher": manager,
            "researcher": researcher,
        },
        evaluators={"default": evaluator},
        assignments={"manager-researcher": all_task_keys},
    )


def _build_delegation_experiment(
    benchmark: Benchmark,
    model: str,
    evaluator: Evaluator,
    workers_registry: Mapping[str, type[Worker]],
) -> Experiment:
    """Build experiment with both manager and researcher worker bindings."""
    manager_cls = workers_registry["manager-researcher"]
    researcher_cls = workers_registry["researcher"]

    manager = manager_cls(name="manager-researcher", model=model)
    researcher = researcher_cls(name="researcher", model=model)

    return Experiment(
        benchmark=benchmark,
        workers={
            "manager-researcher": manager,
            "researcher": researcher,
        },
        evaluators={"default": evaluator},
        assignments={"manager-researcher": "manager-task"},
    )


def _build_researchrubrics_experiment(
    benchmark: Benchmark,
    model: str,
    evaluator: Evaluator,
    workers_registry: Mapping[str, type[Worker]],
) -> Experiment:
    """Build experiment with researchrubrics-manager + researcher.

    Manager is assigned to all static benchmark tasks.  Researcher is
    registered as a sub-worker binding only -- dynamic tasks spawned by
    the manager via add_task() resolve it at runtime.
    """
    manager_cls = workers_registry["researchrubrics-manager"]
    researcher_cls = workers_registry["researchrubrics-researcher"]

    manager = manager_cls(name="researchrubrics-manager", model=model)
    researcher = researcher_cls(name="researchrubrics-researcher", model=model)

    instances = benchmark.build_instances()
    all_task_keys = [task.task_key for tasks in instances.values() for task in tasks]

    return Experiment(
        benchmark=benchmark,
        workers={
            "researchrubrics-manager": manager,
            "researchrubrics-researcher": researcher,
        },
        evaluators={"default": evaluator},
        assignments={"researchrubrics-manager": all_task_keys},
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
