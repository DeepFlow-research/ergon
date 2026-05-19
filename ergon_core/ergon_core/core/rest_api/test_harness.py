"""Danger-prefixed FastAPI router exposing narrow DTOs for tests.

Wire-shape stability: these DTOs are consumed by Playwright helpers in the
dashboard. Schema is additive-only — never remove or rename a field without
coordinating a TS helper update.
"""

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

import inngest
from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import (
    ExperimentCohort,
    RunRecord,
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
    Thread,
)
from ergon_core.core.application.events.task_events import WorkflowStartedEvent
from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.core.application.read_models.cohorts import experiment_cohort_service
from ergon_core.core.application.experiments.service import (
    run_experiment as _run_experiment,
)
from ergon_core.core.application.experiments.definition_writer import persist_benchmark
from ergon_core.core.application.experiments.models import (
    ExperimentRunRequest,
)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, asc, select
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


class TestCohortRunDto(BaseModel):
    run_id: UUID
    status: str


class TestCohortIdDto(BaseModel):
    cohort_id: UUID


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_session_dep() -> Iterator[Session]:
    """Session-factory dependency.

    Overridable from tests via ``app.dependency_overrides[get_session_dep]``
    so unit tests can inject a stub without a live Postgres.
    """
    with Session(get_engine()) as session:
        yield session


def _execution_error_message(execution: RunTaskExecution) -> str | None:
    error = execution.parsed_error()
    if error is None:
        return None
    for key in ("message", "error", "detail"):
        value = error.get(key)
        if isinstance(value, str):
            return value
    return str(error)


def _cohort_id_from_definition(definition: ExperimentDefinition) -> UUID | None:
    raw = definition.parsed_metadata().get("cohort_id")
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    if isinstance(raw, str):
        return UUID(raw)
    return None


# ---------------------------------------------------------------------------
# Read endpoint
# ---------------------------------------------------------------------------


@router.get("/read/run/{run_id}/state", response_model=TestRunStateDto)
def read_run_state(
    run_id: UUID,
    session: Annotated[Session, Depends(get_session_dep)],
) -> TestRunStateDto:
    run = session.exec(select(RunRecord).where(RunRecord.id == run_id)).first()
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")

    nodes = list(session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all())
    slug_by_task_id: dict[UUID, str] = {n.task_id: n.task_slug for n in nodes}

    graph_nodes = [
        TestGraphNodeDto(
            id=n.task_id,
            task_slug=n.task_slug,
            level=n.level,
            status=n.status,
            parent_task_id=n.parent_task_id,
            parent_task_slug=(slug_by_task_id.get(n.parent_task_id) if n.parent_task_id else None),
        )
        for n in nodes
    ]

    mutation_rows = list(
        session.exec(
            select(RunGraphMutation)
            .where(RunGraphMutation.run_id == run_id)
            .order_by(asc(RunGraphMutation.sequence))
        ).all()
    )
    mutations = [
        TestGraphMutationDto(
            sequence=m.sequence,
            mutation_type=m.mutation_type,
            target_task_slug=slug_by_task_id.get(m.target_id) if m.target_id else None,
        )
        for m in mutation_rows
    ]

    eval_rows = list(
        session.exec(select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)).all()
    )
    evaluations = [
        TestEvaluationDto(
            task_id=ev.task_id,
            task_slug=slug_by_task_id.get(ev.task_id),
            score=float(ev.score) if ev.score is not None else 0.0,
            reason="" if ev.feedback is None else ev.feedback,
        )
        for ev in eval_rows
    ]

    execution_rows = list(
        session.exec(select(RunTaskExecution).where(RunTaskExecution.run_id == run_id)).all()
    )
    executions = [
        TestExecutionDto(
            task_slug=slug_by_task_id.get(ex.task_id),
            status=ex.status,
            error=_execution_error_message(ex),
        )
        for ex in execution_rows
    ]

    resource_count = len(
        list(session.exec(select(RunResource).where(RunResource.run_id == run_id)).all())
    )
    thread_count = len(list(session.exec(select(Thread).where(Thread.run_id == run_id)).all()))
    context_event_count = len(
        list(session.exec(select(RunContextEvent).where(RunContextEvent.run_id == run_id)).all())
    )

    # RunRecord.status is a str-subclass Enum, so pydantic accepts it directly
    # into ``status: str`` — matches the runs.py RunSnapshotDto precedent.
    return TestRunStateDto(
        run_id=run_id,
        status=run.status,
        graph_nodes=graph_nodes,
        mutations=mutations,
        evaluations=evaluations,
        executions=executions,
        execution_count=len(execution_rows),
        mutation_count=len(mutation_rows),
        resource_count=resource_count,
        thread_count=thread_count,
        context_event_count=context_event_count,
    )


@router.get(
    "/read/cohort/{cohort_key}/id",
    response_model=TestCohortIdDto,
)
def read_cohort_id(
    cohort_key: str,
    session: Annotated[Session, Depends(get_session_dep)],
) -> TestCohortIdDto:
    """Resolve a cohort name to its UUID for dashboard navigation."""
    cohort = session.exec(
        select(ExperimentCohort).where(ExperimentCohort.name == cohort_key),
    ).first()
    if cohort is None:
        raise HTTPException(status_code=404, detail=f"Cohort {cohort_key!r} not found")
    return TestCohortIdDto(cohort_id=cohort.id)


@router.get(
    "/read/cohort/{cohort_key}/runs",
    response_model=list[TestCohortRunDto],
)
def read_cohort_runs(
    cohort_key: str,
    session: Annotated[Session, Depends(get_session_dep)],
) -> list[TestCohortRunDto]:
    """List all runs attached to a cohort by name.

    ``cohort_key`` matches ``ExperimentCohort.name`` exactly.  Returns
    empty list when the cohort does not exist (rather than 404) so
    Playwright / pytest can poll cheaply while a cohort is being
    submitted.
    """
    cohort = session.exec(
        select(ExperimentCohort).where(ExperimentCohort.name == cohort_key),
    ).first()
    if cohort is None:
        return []
    definition_ids = [
        definition.id
        for definition in session.exec(select(ExperimentDefinition)).all()
        if _cohort_id_from_definition(definition) == cohort.id
    ]
    if not definition_ids:
        return []
    runs = list(
        session.exec(
            select(RunRecord).where(
                RunRecord.definition_id.in_(definition_ids)  # type: ignore[attr-defined]
            )
        ).all(),
    )
    return [TestCohortRunDto(run_id=r.id, status=r.status) for r in runs]


# ---------------------------------------------------------------------------
# Write endpoints — danger-prefixed local/test harness
# ---------------------------------------------------------------------------
#
# Seeded rows record the test cohort tag in ``summary_json`` and stamp the
# target definition metadata with the resolved cohort id so dashboard read
# models can use the canonical definition tables.
# ``ResetRequest.cohort_prefix`` has no default: reset is destructive, so
# callers must always specify what to nuke.


class SeedRunRequest(BaseModel):
    definition_id: UUID
    benchmark_type: str = "test-harness"
    instance_key: str = "seeded"
    worker_team: dict = Field(default_factory=lambda: {"primary": "test-harness-worker"})
    cohort: str = "_test_"
    status: str = "completed"
    task_slugs: list[str] = []


class ResetRequest(BaseModel):
    cohort_prefix: str


@router.post("/write/run/seed", status_code=201)
def seed_run(
    body: SeedRunRequest,
) -> dict:
    # Map spec string ``status`` onto the RunStatus StrEnum; unknown strings
    # are rejected as 422-equivalent 400s so bad tests fail loud.
    try:
        run_status = RunStatus(body.status)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown run status: {body.status!r}",
        ) from exc
    with Session(get_engine()) as s:
        cohort = experiment_cohort_service.resolve_or_create(
            name=body.cohort,
            description="test harness seeded cohort",
            created_by="test-harness",
        )
        definition = s.get(ExperimentDefinition, body.definition_id)
        if definition is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"definition {body.definition_id} not found",
            )
        metadata = dict(definition.metadata_json)
        metadata.update(
            {
                "cohort_id": str(cohort.id),
                "_test_seeded": True,
                "_test_cohort": body.cohort,
                "default_worker_team": body.worker_team,
                "status": "seeded",
            }
        )
        definition.metadata_json = metadata
        s.add(definition)
        run = RunRecord(
            definition_id=body.definition_id,
            benchmark_type=body.benchmark_type,
            instance_key=body.instance_key,
            worker_team_json=body.worker_team,
            status=run_status,
            summary_json={
                "_test_seeded": True,
                "_test_cohort": body.cohort,
                "_test_task_slugs": body.task_slugs,
            },
        )
        s.add(run)
        s.commit()
        s.refresh(run)
        return {"run_id": str(run.id)}


@router.post("/write/reset", status_code=204)
def reset_test_rows(
    body: ResetRequest,
) -> None:
    with Session(get_engine()) as s:
        # Cannot SQL-filter on JSON prefix portably; load seeded rows and
        # filter in Python. Bounded by the seed endpoint being test-only.
        candidates = list(s.exec(select(RunRecord)).all())
        for r in candidates:
            meta = {} if r.summary_json is None else r.summary_json
            if not meta.get("_test_seeded"):
                continue
            tag = meta.get("_test_cohort")
            if isinstance(tag, str) and tag.startswith(body.cohort_prefix):
                s.delete(r)
        definitions = list(s.exec(select(ExperimentDefinition)).all())
        for definition in definitions:
            meta = {} if definition.metadata_json is None else definition.metadata_json
            tag = meta.get("_test_cohort")
            if isinstance(tag, str) and tag.startswith(body.cohort_prefix):
                cleaned = dict(meta)
                cleaned.pop("cohort_id", None)
                cleaned.pop("_test_seeded", None)
                cleaned.pop("_test_cohort", None)
                cleaned.pop("default_worker_team", None)
                cleaned.pop("status", None)
                definition.metadata_json = cleaned
                s.add(definition)
        s.commit()
    return None


# ---------------------------------------------------------------------------
# Cohort submission endpoint — the single entry point for smoke drivers.
#
# Moved here (rather than a separate /runs POST) because it's the test
# harness that cares about cohort-scoped multi-run submission.  Host-side
# pytest never imports ergon internals; it just POSTs slugs.  That keeps
# the smoke fixtures single-sourced in the api container's process (one
# ``register_smoke_fixtures()`` call in app.py) and eliminates the host /
# container fixture-drift risk.
# ---------------------------------------------------------------------------


class CohortSlotRequest(BaseModel):
    worker_slug: str
    evaluator_slug: str


class SubmitCohortRequest(BaseModel):
    benchmark_slug: str
    slots: list[CohortSlotRequest]
    cohort_key: str
    sandbox_slug: str | None = None
    dependency_extras: tuple[str, ...] = ("none",)
    # Smoke workers don't hit an LLM; the field is required downstream
    # only because ``WorkerSpec`` models it.  Default matches the CLI.
    model: str = "openai:gpt-4o"
    limit: int = 1


class SubmitCohortResponse(BaseModel):
    run_ids: list[UUID]
    cohort_id: UUID


@router.post("/write/cohort", response_model=SubmitCohortResponse)
async def submit_cohort(body: SubmitCohortRequest) -> SubmitCohortResponse:
    """Build + persist + dispatch N runs under one cohort.

    Per-slot flow persists the object-bound smoke ``Benchmark`` into the
    immutable ``ExperimentDefinition`` tables. Cohort/display metadata is
    written onto the definition metadata before launch. Slots submit
    sequentially — typical N ≤ 3, so the parallel-gather savings are negligible.
    """
    cohort = experiment_cohort_service.resolve_or_create(
        name=body.cohort_key,
        description=f"smoke cohort: {body.benchmark_slug}",
        created_by="test-harness",
    )

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
                "_test_cohort": body.cohort_key,
                "cohort_id": str(cohort.id),
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

    return SubmitCohortResponse(run_ids=run_ids, cohort_id=cohort.id)
