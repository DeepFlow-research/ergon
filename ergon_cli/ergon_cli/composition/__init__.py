"""Build Experiment from CLI args using registry lookups."""

from collections.abc import Mapping

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.evaluator import Evaluator
from ergon_core.api.experiment import Experiment
from ergon_core.api.worker import Worker


def build_experiment(
    benchmark_slug: str,
    model: str,
    worker_slug: str = "react-v1",
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

    # Three composition paths, one per real manager worker:
    # ``manager-researcher`` (generic) binds a plain ``react-v1`` sub-agent;
    # ``researchrubrics-manager`` binds ``researchrubrics-researcher`` (report
    # writing); ``minif2f-manager`` binds ``minif2f-prover`` (Lean 4 proof).
    # Each manager assigns itself to every static task and registers its
    # dedicated sub-worker under a matching binding key so ``add_subtask``
    # resolves to it.
    match worker_slug:
        case "manager-researcher":
            return _build_manager_researcher_experiment(benchmark, model, evaluator, WORKERS)
        case "researchrubrics-manager":
            return _build_researchrubrics_experiment(benchmark, model, evaluator, WORKERS)
        case "minif2f-manager":
            return _build_minif2f_experiment(benchmark, model, evaluator, WORKERS)
        case _:
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
    """Build experiment with manager-researcher + react-v1 sub-worker.

    The manager is assigned to all static benchmark tasks.  A generic
    ReAct sub-worker is bound under the ``"researcher"`` key so that
    dynamic subtasks spawned via ``add_subtask()`` (default binding key
    ``"researcher"`` per ``subtask_lifecycle_toolkit``) resolve to a
    real agent rather than the retired ``StubWorker`` alias.
    """
    manager_cls = workers_registry["manager-researcher"]
    researcher_cls = workers_registry["react-v1"]

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


def _build_researchrubrics_experiment(
    benchmark: Benchmark,
    model: str,
    evaluator: Evaluator,
    workers_registry: Mapping[str, type[Worker]],
) -> Experiment:
    """Build experiment with researchrubrics-manager + researcher.

    Manager is assigned to all static benchmark tasks.  Researcher is
    registered as a sub-worker binding only -- dynamic tasks spawned by
    the manager via add_subtask() resolve it at runtime.
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


def _build_minif2f_experiment(
    benchmark: Benchmark,
    model: str,
    evaluator: Evaluator,
    workers_registry: Mapping[str, type[Worker]],
) -> Experiment:
    """Build experiment with minif2f-manager + minif2f-prover sub-worker.

    Manager is assigned to all static benchmark tasks.  Prover is registered
    as a sub-worker binding only — dynamic subtasks spawned by the manager
    via ``add_subtask(worker_binding_key='minif2f-prover')`` resolve it at
    runtime.
    """
    manager_cls = workers_registry["minif2f-manager"]
    prover_cls = workers_registry["minif2f-prover"]

    manager = manager_cls(name="minif2f-manager", model=model)
    prover = prover_cls(name="minif2f-prover", model=model)

    instances = benchmark.build_instances()
    all_task_keys = [task.task_key for tasks in instances.values() for task in tasks]

    return Experiment(
        benchmark=benchmark,
        workers={
            "minif2f-manager": manager,
            "minif2f-prover": prover,
        },
        evaluators={"default": evaluator},
        assignments={"minif2f-manager": all_task_keys},
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
