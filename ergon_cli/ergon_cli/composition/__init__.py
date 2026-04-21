"""Build Experiment from CLI args using registry lookups."""

from collections.abc import Mapping, Sequence

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.evaluator import Evaluator
from ergon_core.api.experiment import Experiment
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker import Worker


def build_experiment(
    benchmark_slug: str,
    model: str,
    worker_slug: str = "stub-worker",
    evaluator_slug: str = "stub-rubric",
    workflow: str = "single",
    limit: int | None = None,
    toolkit_benchmark: str | None = None,
) -> Experiment:
    # Deferred: CLI startup cost
    from ergon_builtins.registry import BENCHMARKS, EVALUATORS, WORKERS

    benchmark_cls = BENCHMARKS[benchmark_slug]
    worker_cls = WORKERS[worker_slug]
    evaluator_cls = EVALUATORS[evaluator_slug]

    benchmark = _construct_benchmark(benchmark_cls, workflow=workflow, limit=limit)
    if toolkit_benchmark is not None:
        _inject_toolkit_benchmark(benchmark, toolkit_benchmark)
    evaluator = evaluator_cls(name="evaluator")

    # Composition is driven by the explicit worker selection first; the
    # benchmark only wins when nothing else matches (delegation-smoke needs
    # both manager + researcher regardless of which single worker the user
    # typed).
    match (worker_slug, benchmark_slug):
        case (_, "delegation-smoke"):
            return _build_delegation_experiment(benchmark, model, evaluator, WORKERS)
        case ("manager-researcher", _):
            return _build_manager_researcher_experiment(benchmark, model, evaluator, WORKERS)
        case ("researchrubrics-manager", _):
            return _build_researchrubrics_experiment(benchmark, model, evaluator, WORKERS)
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
    """Build experiment with manager-researcher + researcher for any benchmark.

    The manager-researcher is assigned to all static benchmark tasks.
    The researcher worker is registered as a sub-worker binding only —
    it receives no static task assignments; dynamic tasks spawned by the
    manager via add_subtask() will resolve it via ExperimentDefinitionWorker
    lookup in _prepare_graph_native().
    """
    manager_cls = workers_registry["manager-researcher"]
    researcher_cls = workers_registry["researcher"]

    manager = manager_cls(name="manager-researcher", model=model)
    researcher = researcher_cls(name="researcher", model=model)

    # Collect all task slugs so we can explicitly assign the manager to them.
    # The persistence service only auto-assigns when there is exactly 1 worker;
    # with 2 workers we must provide explicit assignments.
    instances = benchmark.build_instances()
    all_task_slugs = [task.task_slug for tasks in instances.values() for task in tasks]

    return Experiment(
        benchmark=benchmark,
        workers={
            "manager-researcher": manager,
            "researcher": researcher,
        },
        evaluators={"default": evaluator},
        assignments={"manager-researcher": all_task_slugs},
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
    the manager via add_subtask() resolve it at runtime.
    """
    manager_cls = workers_registry["researchrubrics-manager"]
    researcher_cls = workers_registry["researchrubrics-researcher"]

    manager = manager_cls(name="researchrubrics-manager", model=model)
    researcher = researcher_cls(name="researchrubrics-researcher", model=model)

    instances = benchmark.build_instances()
    all_task_slugs = [task.task_slug for tasks in instances.values() for task in tasks]

    return Experiment(
        benchmark=benchmark,
        workers={
            "researchrubrics-manager": manager,
            "researchrubrics-researcher": researcher,
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


def _inject_toolkit_benchmark(benchmark: Benchmark, toolkit_benchmark: str) -> None:
    """Wrap benchmark.build_instances so every returned task carries toolkit_benchmark.

    BenchmarkTask is a frozen Pydantic model, so direct mutation is not
    possible.  Instead we wrap the benchmark's build_instances method once:
    the wrapper creates new task objects via model_copy(update={...}) with
    toolkit_benchmark merged into task_payload.  The original method is
    preserved as the delegate so the wrapping is idempotent-safe.
    """
    original_build = benchmark.build_instances

    def _patched_build_instances():
        raw: Mapping[str, Sequence[BenchmarkTask]] = original_build()
        return {
            key: [
                task.model_copy(
                    update={
                        "task_payload": {
                            **task.task_payload,
                            "toolkit_benchmark": toolkit_benchmark,
                        }
                    }
                )
                for task in tasks
            ]
            for key, tasks in raw.items()
        }

    benchmark.build_instances = _patched_build_instances  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]
