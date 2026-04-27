"""Experiment definition service."""

from collections.abc import Mapping
from typing import Type

from ergon_core.api.benchmark import Benchmark
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import ExperimentRecord
from ergon_core.core.runtime.services.experiment_schemas import (
    ExperimentDefineRequest,
    ExperimentDefineResult,
)
from ergon_core.core.utils import utcnow


class ExperimentDefinitionService:
    """Create experiment records without launching runs."""

    def __init__(self, *, benchmarks: Mapping[str, Type[Benchmark]] | None = None) -> None:
        self._benchmarks = benchmarks

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

    def _benchmark_cls(self, benchmark_slug: str) -> Type[Benchmark]:
        if self._benchmarks is None:
            from ergon_builtins.registry import BENCHMARKS

            self._benchmarks = BENCHMARKS
        return self._benchmarks[benchmark_slug]


def _construct_benchmark(cls: Type[Benchmark], *, limit: int | None) -> Benchmark:
    if limit is not None:
        try:
            return cls(limit=limit)
        except TypeError:
            pass
    return cls()


def _select_samples(
    instances: Mapping[str, object],
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

