"""Test-only FastAPI router exposing narrow DTOs for Playwright/backend tests.

Gates:
  - Router is only mounted when ``ENABLE_TEST_HARNESS=1`` (caller-side in
    ``app.py``). When unset or ``0`` the include_router call is skipped and
    the routes do not exist at all.
  - Write endpoints (Task 7) additionally require the ``X-Test-Secret`` header
    to match ``TEST_HARNESS_SECRET``. Absence of the env var = 500 (distinct
    from 401 bad secret) so misconfiguration is distinguishable from auth
    failure.

Wire-shape stability: these DTOs are consumed by Playwright helpers in the
dashboard. Schema is additive-only — never remove or rename a field without
coordinating a TS helper update.
"""

import os
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

import inngest
from ergon_cli.composition import build_experiment
from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.persistence.telemetry.models import (
    ExperimentCohort,
    RunRecord,
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
    Thread,
)
from ergon_core.core.runtime.events.task_events import WorkflowStartedEvent
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.cohort_service import experiment_cohort_service
from ergon_core.core.runtime.services.run_service import create_run
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, asc, select

router = APIRouter(prefix="/api/test", tags=["test-harness"])


# ---------------------------------------------------------------------------
# DTOs (Playwright wire shape — additive-only)
# ---------------------------------------------------------------------------


class TestGraphNodeDto(BaseModel):
    id: UUID
    task_slug: str
    level: int
    status: str
    parent_node_id: UUID | None
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


def _require_secret(
    x_test_secret: Annotated[str | None, Header(alias="X-Test-Secret")] = None,
) -> None:
    """Gate write endpoints on ``TEST_HARNESS_SECRET``.

    Wired to Task 7 write endpoints; unused in Task 6. Kept here so the
    secret-gating contract is co-located with the DTOs and env-var policy.
    """
    configured = os.environ.get("TEST_HARNESS_SECRET")
    if configured is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TEST_HARNESS_SECRET not configured",
        )
    if x_test_secret != configured:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


def _execution_error_message(execution: RunTaskExecution) -> str | None:
    error = execution.parsed_error()
    if error is None:
        return None
    for key in ("message", "error", "detail"):
        value = error.get(key)
        if isinstance(value, str):
            return value
    return str(error)


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
    slug_by_node_id: dict[UUID, str] = {n.id: n.task_slug for n in nodes}

    graph_nodes = [
        TestGraphNodeDto(
            id=n.id,
            task_slug=n.task_slug,
            level=n.level,
            status=n.status,
            parent_node_id=n.parent_node_id,
            parent_task_slug=(slug_by_node_id.get(n.parent_node_id) if n.parent_node_id else None),
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
            target_task_slug=slug_by_node_id.get(m.target_id) if m.target_id else None,
        )
        for m in mutation_rows
    ]

    eval_rows = list(
        session.exec(select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)).all()
    )
    evaluations = [
        TestEvaluationDto(
            task_id=ev.node_id,
            task_slug=slug_by_node_id.get(ev.node_id),
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
            task_slug=slug_by_node_id.get(ex.node_id) if ex.node_id else None,
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
    runs = list(
        session.exec(select(RunRecord).where(RunRecord.cohort_id == cohort.id)).all(),
    )
    return [TestCohortRunDto(run_id=r.id, status=r.status) for r in runs]


# ---------------------------------------------------------------------------
# Write endpoints (Task 7) — gated on X-Test-Secret
# ---------------------------------------------------------------------------
#
# Schema reality vs. spec:
#   The RFC/plan speaks of ``RunRecord.cohort: str`` and ``metadata``. The
#   actual model has ``cohort_id: UUID | None`` (FK) and ``summary_json: dict``.
#   We bridge by:
#     - Recording the test "cohort tag" as a string inside ``summary_json``
#       under ``_test_cohort`` so reset can match by prefix.
#     - Marking seeded rows with ``summary_json["_test_seeded"] = True``.
#     - Requiring the caller to pass an existing ``experiment_definition_id``
#       (NOT NULL FK) when seeding — no synthetic definition is created here.
#
# ``SeedRunRequest.cohort`` is defaulted so a body with only the required
# ``experiment_definition_id`` passes validation and the secret gate (which
# runs inside the handler body, after FastAPI's validation phase) can surface
# 401/500 without 422 noise. ``experiment_definition_id`` is required because
# ``RunRecord.experiment_definition_id`` is a NOT NULL FK to
# ``experiment_definitions.id`` — no synthetic definition is created here.
# ``ResetRequest.cohort_prefix`` has no default: reset is destructive, so
# callers must always specify what to nuke.


class SeedRunRequest(BaseModel):
    experiment_definition_id: UUID
    cohort: str = "_test_"
    status: str = "completed"
    task_slugs: list[str] = []


class ResetRequest(BaseModel):
    cohort_prefix: str


@router.post("/write/run/seed", status_code=201)
def seed_run(
    body: SeedRunRequest,
    x_test_secret: Annotated[str | None, Header(alias="X-Test-Secret")] = None,
) -> dict:
    _require_secret(x_test_secret)
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
        run = RunRecord(
            experiment_definition_id=body.experiment_definition_id,
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
    x_test_secret: Annotated[str | None, Header(alias="X-Test-Secret")] = None,
) -> None:
    _require_secret(x_test_secret)
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

    Per-slot flow mirrors the CLI's ``ergon benchmark run``:
    ``build_experiment`` → ``validate`` → ``persist`` → ``create_run``
    → send ``WorkflowStartedEvent``.  Slots submit sequentially —
    typical N ≤ 3, so the parallel-gather savings are negligible.
    """
    cohort = experiment_cohort_service.resolve_or_create(
        name=body.cohort_key,
        description=f"smoke cohort: {body.benchmark_slug}",
        created_by="test-harness",
    )

    run_ids: list[UUID] = []
    for slot in body.slots:
        experiment = build_experiment(
            benchmark_slug=body.benchmark_slug,
            model=body.model,
            worker_slug=slot.worker_slug,
            evaluator_slug=slot.evaluator_slug,
            limit=body.limit,
        )
        experiment.validate()
        persisted = experiment.persist()
        run = create_run(persisted, cohort_id=cohort.id)
        await inngest_client.send(
            inngest.Event(
                name=WorkflowStartedEvent.name,
                data=WorkflowStartedEvent(
                    run_id=run.id,
                    definition_id=persisted.definition_id,
                ).model_dump(mode="json"),
            )
        )
        run_ids.append(run.id)

    return SubmitCohortResponse(run_ids=run_ids, cohort_id=cohort.id)
