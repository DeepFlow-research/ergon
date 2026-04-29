"""Single front-door service for experiment definition, persistence, and launch."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from inspect import Parameter, signature
from typing import TYPE_CHECKING
from uuid import UUID

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.benchmark import Task
from ergon_core.api.registry import registry
from ergon_core.core.domain.experiments import DefinitionHandle
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import ExperimentRecord
from ergon_core.core.application.experiments.models import (
    ExperimentDefineRequest,
    ExperimentDefineResult,
    ExperimentRunRequest,
    ExperimentRunResult,
    RunAssignment,
)
from ergon_core.core.shared.utils import utcnow
from pydantic import BaseModel

if TYPE_CHECKING:
    from ergon_core.core.domain.experiments import Experiment

WorkflowDefinitionFactory = Callable[
    [ExperimentRecord, RunAssignment],
    DefinitionHandle,
]
WorkflowStartedEmitter = Callable[[UUID, UUID], Awaitable[None]]


class ExperimentService:
    """Define persisted experiments, write immutable definitions, and launch runs."""

    def __init__(
        self,
        *,
        benchmarks: Mapping[str, Callable[..., Benchmark]] | None = None,
        workflow_definition_factory: WorkflowDefinitionFactory | None = None,
        emit_workflow_started: WorkflowStartedEmitter | None = None,
    ) -> None:
        self._benchmarks = benchmarks
        self._workflow_definition_factory = workflow_definition_factory
        self._emit_workflow_started = emit_workflow_started

    def define_benchmark_experiment(
        self, request: ExperimentDefineRequest
    ) -> ExperimentDefineResult:
        benchmark_cls = self._benchmark_cls(request.benchmark_slug)
        benchmark = _construct_benchmark(benchmark_cls, limit=request.limit)
        instances = benchmark.build_instances()
        selected_samples = _select_samples(instances, request)
        name = request.name or _generated_name(request.benchmark_slug, len(selected_samples))

        experiment = ExperimentRecord(
            cohort_id=request.cohort_id,
            name=name,
            benchmark_type=benchmark.type_slug,
            sample_count=len(selected_samples),
            sample_selection_json={"instance_keys": selected_samples},
            default_worker_team_json=request.default_worker_team,
            default_evaluator_slug=request.default_evaluator_slug,
            default_model_target=request.default_model_target,
            sandbox_slug=request.sandbox_slug,
            dependency_extras_json={"extras": list(request.dependency_extras)},
            design_json=request.design,
            seed=request.seed,
            metadata_json={
                **request.metadata,
                "benchmark_slug": request.benchmark_slug,
            },
            status="defined",
        )
        with get_session() as session:
            session.add(experiment)
            session.commit()
            session.refresh(experiment)

        return ExperimentDefineResult(
            experiment_id=experiment.id,
            cohort_id=experiment.cohort_id,
            benchmark_type=experiment.benchmark_type,
            sample_count=experiment.sample_count,
            selected_samples=selected_samples,
        )

    def persist_definition(self, experiment: "Experiment") -> DefinitionHandle:
        """Persist an authored experiment as immutable workflow definition rows."""
        from ergon_core.core.application.experiments.definition_writer import (  # slopcop: ignore[guarded-function-import] -- reason: keep heavy definition writer private to the lifecycle service
            _ExperimentDefinitionWriter,
        )

        return _ExperimentDefinitionWriter().persist_definition(experiment)

    async def run_experiment(self, request: ExperimentRunRequest) -> ExperimentRunResult:
        """Materialize runs for a previously defined experiment."""
        from ergon_core.core.application.experiments.launch import (  # slopcop: ignore[guarded-function-import] -- reason: launch helper is private runtime plumbing behind this front door
            _ExperimentRunLauncher,
        )

        return await _ExperimentRunLauncher(
            workflow_definition_factory=self._workflow_definition_factory,
            emit_workflow_started=self._emit_workflow_started,
        ).run_experiment(request)

    def _benchmark_cls(self, benchmark_slug: str) -> Callable[..., Benchmark]:
        if self._benchmarks is None:
            self._benchmarks = registry.benchmarks
        return self._benchmarks[benchmark_slug]


def _construct_benchmark(cls: Callable[..., Benchmark], *, limit: int | None) -> Benchmark:
    parameters = signature(cls).parameters
    accepts_limit = "limit" in parameters or any(
        parameter.kind is Parameter.VAR_KEYWORD for parameter in parameters.values()
    )
    if limit is not None and accepts_limit:
        return cls(limit=limit)
    return cls()


def _select_samples(
    instances: Mapping[str, Sequence[Task[BaseModel]]],
    request: ExperimentDefineRequest,
) -> list[str]:
    if request.sample_ids is not None:
        missing = [sample_id for sample_id in request.sample_ids if sample_id not in instances]
        if missing:
            raise ValueError(f"Unknown benchmark sample ids: {missing}")
        return list(request.sample_ids)
    return list(instances.keys())


def _generated_name(benchmark_slug: str, sample_count: int) -> str:
    return f"{benchmark_slug} n={sample_count} {utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
