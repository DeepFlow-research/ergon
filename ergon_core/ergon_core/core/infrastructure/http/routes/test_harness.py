"""Danger-prefixed FastAPI router exposing narrow DTOs for tests.

Wire-shape stability: these DTOs are consumed by Playwright helpers in the
dashboard. Schema is additive-only — never remove or rename a field without
coordinating a TS helper update.
"""

from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from ergon_core.core.application.experiments.models import (
    ExperimentRunRequest,
)
from ergon_core.core.application.experiments.service import (
    run_experiment as _run_experiment,
)
from ergon_core.core.application.testing.test_harness_service import (
    DefinitionNotFoundError,
    UnknownRunStatusError,
    get_session_dep,
    read_experiment_runs as _read_experiment_runs,
    read_run_state as _read_run_state,
    reset_test_rows as _reset_test_rows,
    seed_run as _seed_run,
)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from tests.fixtures.smoke_components.benchmarks import (
    GDPEvalSmokeBenchmark,
    MiniF2FSmokeBenchmark,
    ResearchRubricsSmokeBenchmark,
    SweBenchSmokeBenchmark,
)

router = APIRouter(prefix="/api/__danger__/test-harness", tags=["danger-test-harness"])

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


class TestGraphMutationDto(BaseModel):
    sequence: int
    mutation_type: str
    target_task_slug: str | None


class TestExecutionDto(BaseModel):
    task_slug: str | None
    status: str
    error: str | None


class TestRunStateDto(BaseModel):
    run_id: UUID
    status: str
    graph_nodes: list[TestGraphNodeDto]
    mutations: list[TestGraphMutationDto]
    evaluations: list[TestEvaluationDto]
    executions: list[TestExecutionDto]
    execution_count: int
    mutation_count: int
    resource_count: int
    thread_count: int
    context_event_count: int


class TestExperimentRunDto(BaseModel):
    run_id: UUID
    status: str


# ---------------------------------------------------------------------------
# Read endpoint
# ---------------------------------------------------------------------------


@router.get("/read/run/{run_id}/state", response_model=TestRunStateDto)
def read_run_state(
    run_id: UUID,
    session: Annotated[object, Depends(get_session_dep)],
) -> TestRunStateDto:
    state = _read_run_state(run_id, session)  # type: ignore[arg-type]
    if state is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return TestRunStateDto(**asdict(state))


@router.get(
    "/read/experiment/{experiment}/runs",
    response_model=list[TestExperimentRunDto],
)
def read_experiment_runs(
    experiment: str,
    session: Annotated[object, Depends(get_session_dep)],
) -> list[TestExperimentRunDto]:
    """List all runs attached to a v2 experiment grouping tag."""
    return [
        TestExperimentRunDto(run_id=run.run_id, status=run.status)
        for run in _read_experiment_runs(experiment, session)  # type: ignore[arg-type]
    ]


# ---------------------------------------------------------------------------
# Write endpoints — danger-prefixed local/test harness
# ---------------------------------------------------------------------------
#
# Seeded rows record the test experiment tag in ``summary_json`` and
# ``RunRecord.experiment`` so dashboard/read tests use the canonical v2 grouping
# column.
# ``ResetRequest.experiment_prefix`` has no default: reset is destructive, so
# callers must always specify what to nuke.


class SeedRunRequest(BaseModel):
    definition_id: UUID
    benchmark_type: str = "test-harness"
    instance_key: str = "seeded"
    worker_team: dict = Field(default_factory=lambda: {"primary": "test-harness-worker"})
    experiment: str = "_test_"
    status: str = "completed"
    task_slugs: list[str] = []


class ResetRequest(BaseModel):
    experiment_prefix: str


@router.post("/write/run/seed", status_code=201)
def seed_run(
    body: SeedRunRequest,
) -> dict:
    try:
        run_id = _seed_run(
            definition_id=body.definition_id,
            benchmark_type=body.benchmark_type,
            instance_key=body.instance_key,
            worker_team=body.worker_team,
            experiment=body.experiment,
            status=body.status,
            task_slugs=body.task_slugs,
        )
    except UnknownRunStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown run status: {body.status!r}",
        ) from exc
    except DefinitionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"definition {body.definition_id} not found",
        ) from exc
    return {"run_id": str(run_id)}


@router.post("/write/reset", status_code=204)
def reset_test_rows(
    body: ResetRequest,
) -> None:
    _reset_test_rows(experiment_prefix=body.experiment_prefix)
    return None


# ---------------------------------------------------------------------------
# Experiment-run submission endpoint — the single entry point for smoke drivers.
#
# Moved here (rather than a separate /runs POST) because it's the test
# harness that cares about grouped multi-run submission.  Host-side
# pytest never imports ergon internals; it just POSTs slugs.  That keeps
# the smoke fixtures single-sourced in the api container's process (one
# ``register_smoke_fixtures()`` call in app.py) and eliminates the host /
# container fixture-drift risk.
# ---------------------------------------------------------------------------


class ExperimentRunSlotRequest(BaseModel):
    worker_slug: str
    evaluator_slug: str


class SubmitExperimentRunsRequest(BaseModel):
    benchmark_slug: str
    slots: list[ExperimentRunSlotRequest]
    experiment: str
    sandbox_slug: str | None = None
    dependency_extras: tuple[str, ...] = ("none",)
    # Smoke workers don't hit an LLM; the field is required downstream
    # only because ``WorkerSpec`` models it.  Default matches the CLI.
    model: str = "openai:gpt-4o"
    limit: int = 1


class SubmitExperimentRunsResponse(BaseModel):
    run_ids: list[UUID]


@router.post("/write/experiment-runs", response_model=SubmitExperimentRunsResponse)
async def submit_experiment_runs(
    body: SubmitExperimentRunsRequest,
) -> SubmitExperimentRunsResponse:
    """Build + persist + dispatch N runs under one experiment tag.

    Per-slot flow persists the object-bound smoke ``Benchmark`` into the
    immutable ``ExperimentDefinition`` tables. The v2 experiment grouping tag
    is written into definition metadata and copied to ``RunRecord.experiment``
    by launch. Slots submit sequentially — typical N ≤ 3, so the
    parallel-gather savings are negligible.
    """
    from ergon_core.core.application.experiments.definition_writer import persist_benchmark

    run_ids: list[UUID] = []
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
        handle = persist_benchmark(benchmark_source)

        launched = await _run_experiment(ExperimentRunRequest(definition_id=handle.definition_id))
        run_ids.extend(launched.run_ids)

    return SubmitExperimentRunsResponse(run_ids=run_ids)
