"""Danger-prefixed FastAPI router exposing narrow DTOs for tests.

Wire-shape stability: these DTOs are consumed by Playwright helpers in the
dashboard. Schema is additive-only — never remove or rename a field without
coordinating a TS helper update.
"""

from dataclasses import asdict
from collections.abc import Iterator
from typing import Annotated, Literal
from uuid import UUID

from ergon_core.api.experiment import Environment, Experiment, Sample
from ergon_core.core.application.experiments.service import ExperimentSubmissionService
from ergon_core.core.application.testing.test_harness_service import (
    UnknownSampleStatusError,
    get_session_dep,
    read_experiment_samples as _read_experiment_samples,
    read_sample_state as _read_sample_state,
    reset_test_rows as _reset_test_rows,
    seed_sample as _seed_sample,
)
from ergon_core.core.persistence.shared.db import get_session
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from tests.fixtures.smoke_components.benchmarks import (
    GDPEvalSmokeBenchmark,
    MiniF2FSmokeBenchmark,
    ResearchRubricsSmokeBenchmark,
    SweBenchSmokeBenchmark,
)

router = APIRouter(
    prefix="/api/__danger__/test-harness",
    tags=["danger-test-harness"],
    include_in_schema=False,
)

_SMOKE_BENCHMARKS = {
    benchmark.type_slug: benchmark
    for benchmark in (
        GDPEvalSmokeBenchmark,
        MiniF2FSmokeBenchmark,
        ResearchRubricsSmokeBenchmark,
        SweBenchSmokeBenchmark,
    )
}


# ---------------------------------------------------------------------------
# DTOs (Playwright wire shape — additive-only)
# ---------------------------------------------------------------------------


class TestGraphNodeDto(BaseModel):
    id: UUID
    task_slug: str
    level: int
    status: str
    parent_task_id: UUID | None
    parent_task_slug: str | None


class TestEvaluationDto(BaseModel):
    task_id: UUID
    task_slug: str | None
    score: float
    reason: str


class TestSampleRuntimeEventDto(BaseModel):
    table: str
    event_type: str
    target_id: UUID | None
    payload: dict


class TestExecutionDto(BaseModel):
    task_slug: str | None
    status: str
    error: str | None


class TestSampleStateDto(BaseModel):
    sample_id: UUID
    status: str
    graph_nodes: list[TestGraphNodeDto]
    events: list[TestSampleRuntimeEventDto]
    evaluations: list[TestEvaluationDto]
    executions: list[TestExecutionDto]
    execution_count: int
    event_count: int
    resource_count: int
    thread_count: int
    context_event_count: int


class TestExperimentSampleDto(BaseModel):
    sample_id: UUID
    status: str


# ---------------------------------------------------------------------------
# Read endpoint
# ---------------------------------------------------------------------------


@router.get("/read/samples/{sample_id}/state", response_model=TestSampleStateDto)
def read_sample_state(
    sample_id: UUID,
    session: Annotated[object, Depends(get_session_dep)],
) -> TestSampleStateDto:
    state = _read_sample_state(sample_id, session)  # type: ignore[arg-type]
    if state is None:
        raise HTTPException(status_code=404, detail=f"sample {sample_id} not found")
    return TestSampleStateDto(**asdict(state))


@router.get(
    "/read/experiment/{experiment}/samples",
    response_model=list[TestExperimentSampleDto],
)
def read_experiment_samples(
    experiment: str,
    session: Annotated[object, Depends(get_session_dep)],
) -> list[TestExperimentSampleDto]:
    """List all samples attached to a v2 experiment grouping tag."""
    return [
        TestExperimentSampleDto(sample_id=sample.sample_id, status=sample.status)
        for sample in _read_experiment_samples(experiment, session)  # type: ignore[arg-type]
    ]


# ---------------------------------------------------------------------------
# Write endpoints — danger-prefixed local/test harness
# ---------------------------------------------------------------------------
#
# Seeded rows record the test experiment tag in ``summary_json`` and
# ``SampleRecord.experiment`` so dashboard/read tests use the canonical v2 grouping
# column.
# ``ResetRequest.experiment_prefix`` has no default: reset is destructive, so
# callers must always specify what to nuke.


class SeedSampleRequest(BaseModel):
    benchmark_type: str = "test-harness"
    instance_key: str = "seeded"
    worker_team: dict = Field(default_factory=lambda: {"primary": "test-harness-worker"})
    experiment: str = "_test_"
    status: str = "completed"
    task_slugs: list[str] = []


class ResetRequest(BaseModel):
    experiment_prefix: str


@router.post("/write/samples/seed", status_code=201)
def seed_sample(
    body: SeedSampleRequest,
) -> dict:
    try:
        sample_id = _seed_sample(
            benchmark_type=body.benchmark_type,
            instance_key=body.instance_key,
            worker_team=body.worker_team,
            experiment=body.experiment,
            status=body.status,
            task_slugs=body.task_slugs,
        )
    except UnknownSampleStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown sample status: {body.status!r}",
        ) from exc
    return {"sample_id": str(sample_id)}


@router.post("/write/reset", status_code=204)
def reset_test_rows(
    body: ResetRequest,
) -> None:
    _reset_test_rows(experiment_prefix=body.experiment_prefix)
    return None


# ---------------------------------------------------------------------------
# Experiment sample submission endpoint — the single entry point for smoke drivers.
#
# Moved here (rather than a separate /samples POST) because it's the test
# harness that cares about grouped multi-run submission.  Host-side
# pytest never imports ergon internals; it just POSTs slugs.  That keeps
# the smoke fixtures single-sourced in the api container's process (one
# ``register_smoke_fixtures()`` call in app.py) and eliminates the host /
# container fixture-drift risk.
# ---------------------------------------------------------------------------


class ExperimentSampleSlotRequest(BaseModel):
    worker_slug: str
    evaluator_slug: str


class SubmitExperimentSamplesRequest(BaseModel):
    benchmark_slug: str
    slots: list[ExperimentSampleSlotRequest]
    experiment: str
    sandbox_slug: str | None = None
    dependency_extras: tuple[str, ...] = ("none",)
    # Smoke workers don't hit an LLM; the field is required downstream
    # only because ``WorkerSpec`` models it.  Default matches the CLI.
    model: str = "openai:gpt-4o"
    limit: int = 1


class SubmitExperimentSamplesResponse(BaseModel):
    sample_ids: list[UUID]


class _HarnessEnvironment(Environment):
    samples: list[Sample]
    source_mode: Literal["materialized"] = "materialized"

    def iter_samples(self) -> Iterator[Sample]:
        return iter(self.samples)


@router.post("/write/experiment-samples", response_model=SubmitExperimentSamplesResponse)
async def submit_experiment_samples(
    body: SubmitExperimentSamplesRequest,
) -> SubmitExperimentSamplesResponse:
    """Build + persist + dispatch samples under one experiment tag."""

    sample_ids: list[UUID] = []
    for slot in body.slots:
        try:
            benchmark_cls = _SMOKE_BENCHMARKS[body.benchmark_slug]
        except KeyError:
            known = ", ".join(sorted(_SMOKE_BENCHMARKS))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown smoke benchmark {body.benchmark_slug!r}; known: {known}",
            ) from None
        benchmark_source = benchmark_cls(
            metadata={
                "benchmark_slug": body.benchmark_slug,
                "source": "test-harness",
                "experiment": body.experiment,
                "default_worker_team": {"primary": slot.worker_slug},
                "default_evaluator_slug": slot.evaluator_slug,
                "default_model_target": body.model,
                "sandbox_slug": body.sandbox_slug or body.benchmark_slug,
                "dependency_extras": list(body.dependency_extras),
            },
            created_by="test-harness",
        )
        setattr(benchmark_source, "worker_slug", slot.worker_slug)
        setattr(benchmark_source, "model", body.model)
        authored_samples: list[Sample] = []
        for instance_key, tasks in benchmark_source.build_instances().items():
            authored_samples.append(
                Sample.from_tasks(
                    name=f"{body.benchmark_slug}:{instance_key}",
                    sample_key=instance_key,
                    environment_name=body.benchmark_slug,
                    tasks=tasks,
                    sample_ref={"instance_key": instance_key},
                    metadata={
                        "experiment": body.experiment,
                        "worker_slug": slot.worker_slug,
                        "evaluator_slug": slot.evaluator_slug,
                    },
                )
            )
        environment = _HarnessEnvironment(
            name=body.benchmark_slug,
            samples=authored_samples[: body.limit],
            metadata={"source": "test-harness"},
        )
        experiment = Experiment(
            name=body.experiment,
            environments=[environment],
            metadata={"source": "test-harness"},
        )
        with get_session() as session:
            result = await experiment.submit(
                service=ExperimentSubmissionService.for_session(session),
                k=body.limit,
            )
        sample_ids.extend(result.sample_ids)

    return SubmitExperimentSamplesResponse(sample_ids=sample_ids)
