# Experiment Cohort Backend

This document defines the backend changes needed to support the frontend product model introduced in `paper_code_structure_plans/frontend_spec/13_COHORT_VIEW.md`.

The key shift is:

- the product is no longer only "open one run and inspect it"
- the product is now "operate a named cohort of many runs, then drill into a run, then into a task"

That requires a real backend cohort concept.

## Goal

Introduce a first-class `Experiment Cohort` backend model that:

- groups many runs under one named cohort
- preserves reproducibility metadata for that cohort
- exposes live aggregate status and score metrics
- supports cohort-level list and detail queries for the FE
- emits cohort-level updates as runs progress

## Why This Exists

The current backend model is largely:

- `Experiment` = one benchmark task definition
- `Run` = one execution of one experiment

That is enough for:

- single-run debugging
- benchmark task storage

It is not enough for the FE we now want, which needs:

- a named top-level cohort like `minif2f-react-worker-gpt-5-v3`
- many runs attached to that cohort
- cohort-level aggregate progress
- breadcrumb and lineage from run -> cohort
- reproducibility metadata explaining what this cohort actually was

## Product Contract

The intended FE hierarchy is:

1. experiment cohort
2. run
3. task graph
4. selected-task workspace

The backend must support that hierarchy explicitly.

## Non-Goals

This doc is not trying to build:

- a general analytics warehouse
- arbitrary cohort nesting
- a full experiment comparison engine
- historical metric time-series for every cohort change

Those may come later.

The goal here is the smallest clean backend shape that supports:

- cohort identity
- cohort lineage
- cohort summaries
- cohort live updates

## Existing Model

Today the important records already include:

- `Experiment`
- `Run`
- task graph state
- `TaskExecution`
- `Action`
- `ResourceRecord`
- `Evaluation` and `CriterionResult`
- `Thread` and `ThreadMessage`

What is missing is:

- top-level cohort identity
- run membership in that cohort
- cohort reproducibility metadata
- cohort aggregate state

## Proposed Backend Concepts

## `ExperimentCohort`

This should be a first-class persistent model.

Primary meaning:

- one named launch or logical collection of runs that the operator cares about as a unit

Examples:

- `minif2f-react-worker-gpt-5-v3`
- `researchrubrics-baseline-sweep-2026-03-18`
- `mixed-benchmark-regression-check-001`

### Core Fields

- `id`
- `name`
- `description` optional
- `created_at`
- `created_by` optional
- `status` optional cohort lifecycle status
- `metadata_json`

### Reproducibility Metadata

The cohort should be able to store:

- code commit SHA
- repo dirty flag
- prompt or worker version
- model/provider version
- tool/sandbox config snapshot
- dispatch configuration snapshot

This can start as JSON rather than over-normalized columns.

## `ExperimentCohortStats`

This should be a separate denormalized record for fast FE queries.

One row per cohort is enough for v1.

Primary meaning:

- the current aggregate snapshot of the cohort

### Suggested Fields

- `cohort_id`
- `total_runs`
- `pending_runs`
- `executing_runs`
- `evaluating_runs`
- `completed_runs`
- `failed_runs`
- `average_score`
- `best_score`
- `worst_score`
- `average_duration_ms`
- `failure_rate`
- `updated_at`
- `stats_json` for extra aggregates

Separating this from `ExperimentCohort` is useful because:

- identity/config metadata changes rarely
- stats change frequently
- recomputation/update semantics stay cleaner

## `Run.cohort_id`

Each `Run` should belong to exactly one cohort.

That means the cleanest model is:

- add `cohort_id` foreign key to `runs`

instead of:

- a many-to-many join table

The expected product behavior is that one dispatched run is part of one cohort.

If we ever need one run in multiple logical views later, we can add derived groupings on top rather than weakening the core model now.

## Why Not Put Cohort On `Experiment`

Because:

- an `Experiment` is the benchmark task definition
- a cohort is an execution grouping across many runs
- the same experiment may be run in many cohorts over time

So the cohort belongs to `Run`, not to `Experiment`.

## Mixed Benchmarks

Mixed-benchmark cohorts are valid.

That means:

- cohort membership must not assume one benchmark family
- cohort summary queries must be able to join `Run -> Experiment` to expose benchmark identity per run

The FE cohort page should therefore receive benchmark name for each run row.

## Dispatch Contract

The dispatch layer should require a compulsory cohort name.

Recommended rule:

- starting a run without an explicit `experiment_name` or cohort name should no longer be the default path for the main experiment-running workflows

The backend should:

1. resolve or create the named cohort
2. persist the run with `cohort_id`
3. persist reproducibility metadata at cohort creation time

This likely affects:

- CLI dispatch
- benchmark runners
- any manual run-start entrypoints

## Query Surface

The backend should support these read patterns.

## Cohort List

Return:

- cohort identity
- creation time
- high-level reproducibility summary
- aggregate status counts
- aggregate score summary

This is the landing page query.

## Cohort Detail

Return:

- cohort metadata
- cohort stats
- run list for that cohort

Each run row should include at least:

- `run_id`
- `benchmark_name`
- `status`
- `started_at`
- `completed_at`
- running time so far or duration
- `final_score`
- failure summary if any

## Run Detail Breadcrumb Context

The run detail query should be able to return or cheaply derive:

- `cohort_id`
- `cohort_name`

so the FE can render breadcrumb navigation back to the cohort.

## Aggregation Strategy

The cohort FE needs fast, simple aggregate queries.

There are two options.

### Option A: Compute On Read

Pros:

- simplest storage model
- no denormalized sync concerns

Cons:

- repeated aggregate queries across many runs
- awkward for live FE updates
- eventually expensive if cohorts get large

### Option B: Maintain `ExperimentCohortStats`

Pros:

- fast FE reads
- easy cohort summary cards
- straightforward websocket update model

Cons:

- requires event-driven recomputation or update logic

Recommended:

- use `ExperimentCohortStats`

This is the cleanest fit for the product.

## Update Flow

The backend already has meaningful run lifecycle transitions.

When a run changes state, the backend should:

1. persist the run state normally
2. enqueue or trigger cohort stats recomputation for that run's cohort
3. emit a cohort-level update event for the FE

Likely trigger points:

- run created
- run started
- run moved to evaluating
- run completed
- run failed

If score or duration changes at completion, the cohort stats should be recomputed then as well.

## Eventing Model

The FE needs both:

- run-level live updates
- cohort-level live updates

### Recommended New Event Family

- `cohort.updated`

Payload should include:

- `cohort_id`
- updated aggregate stats
- maybe the specific `run_id` that caused the update

### Run-Level Event Payloads

Run-level events should include:

- `cohort_id`

so the FE and any subscription layer can route updates cleanly.

## API / DTO Shape

The exact transport can vary, but the data contract should roughly support:

## `CohortSummaryDto`

- `id`
- `name`
- `created_at`
- `status_counts`
- `average_score`
- `best_score`
- `worst_score`
- `average_duration_ms`
- `failure_rate`
- `metadata_summary`

## `CohortRunRowDto`

- `run_id`
- `cohort_id`
- `cohort_name`
- `benchmark_name`
- `experiment_id`
- `status`
- `started_at`
- `completed_at`
- `running_duration_ms`
- `final_score`
- `error_summary`

## `CohortDetailDto`

- `cohort`
- `stats`
- `runs`

## Raw Event Relationship

The raw run-events drawer does not require cohort-specific storage.

But cohort lineage still matters because:

- the user will open a run from cohort context
- run page breadcrumb must lead back to that cohort

## Recommended Schema Changes

## New Tables

### `experiment_cohorts`

Suggested fields:

- `id`
- `name` unique or unique-enough for the intended namespace
- `description`
- `created_at`
- `created_by`
- `metadata_json`

### `experiment_cohort_stats`

Suggested fields:

- `cohort_id`
- status counts
- score aggregates
- duration aggregates
- `updated_at`
- `stats_json`

## Existing Table Changes

### `runs`

Add:

- `cohort_id` foreign key

Optional but useful:

- `dispatch_metadata_json`

if per-run launch metadata needs a normalized home rather than being hidden inside `benchmark_specific_results`.

## Proposed Code Locations

To make this reviewable as an implementation shape rather than just a concept, here is the recommended file layout.

## Existing Files To Change

### `h_arcane/core/_internal/db/models.py`

Change:

- add `ExperimentCohort`
- add `ExperimentCohortStats`
- add `Run.cohort_id`

Why here:

- this is already the central SQLModel home for persisted entities

### `h_arcane/core/_internal/db/queries.py`

Change:

- add `ExperimentCohortsQueries`
- add `ExperimentCohortStatsQueries`
- add run query helpers such as `get_by_cohort`

Why here:

- this is already the repo’s query layer for model access

### `h_arcane/core/_internal/task/persistence.py`

Change:

- thread `cohort_id` through `create_run_from_config(...)`
- thread any dispatch metadata snapshot through run creation if we choose to persist it

Why here:

- this is where `Run` persistence currently happens

### `h_arcane/core/_internal/infrastructure/events.py`

Change:

- add cohort-related event contracts such as `CohortUpdatedEvent`

Why here:

- current Inngest event contracts already live under domain folders and `infrastructure/events.py` is an existing precedent

### `h_arcane/core/_internal/api/main.py`

Change:

- eventually register cohort routes once FE-facing read APIs exist

## New Files To Add

### `h_arcane/core/_internal/cohorts/__init__.py`

Purpose:

- define a cohort domain package instead of scattering all logic into db/infrastructure/task modules

### `h_arcane/core/_internal/cohorts/schemas.py`

Purpose:

- Pydantic DTOs for cohort list/detail responses and aggregate metric shapes

Suggested contents:

- `CohortSummaryDto`
- `CohortRunRowDto`
- `CohortDetailDto`
- `CohortStatusCounts`
- `CohortMetadataSummary`

### `h_arcane/core/_internal/cohorts/service.py`

Purpose:

- application service for cohort creation, lookup, detail loading, and FE-facing DTO assembly

Suggested class:

- `ExperimentCohortService`

### `h_arcane/core/_internal/cohorts/stats_service.py`

Purpose:

- encapsulate cohort stat recomputation/update logic

Suggested class:

- `ExperimentCohortStatsService`

### `h_arcane/core/_internal/cohorts/events.py`

Purpose:

- if we want to keep cohort event contracts in a dedicated domain file rather than `infrastructure/events.py`

Recommended contents:

- `CohortUpdatedEvent`

Either location is fine, but we should pick one and stay consistent.

### `h_arcane/core/_internal/cohorts/inngest_functions/refresh_stats.py`

Purpose:

- background recomputation/update of cohort stats in response to run lifecycle events

Suggested function:

- `refresh_cohort_stats`

### `h_arcane/core/_internal/api/cohorts.py`

Purpose:

- FastAPI router for cohort list and detail endpoints

Suggested endpoints:

- `GET /cohorts`
- `GET /cohorts/{cohort_id}`

## Recommended Package Shape

The cleanest structure is:

```text
h_arcane/core/_internal/
├── cohorts/
│   ├── __init__.py
│   ├── schemas.py
│   ├── service.py
│   ├── stats_service.py
│   ├── events.py
│   └── inngest_functions/
│       ├── __init__.py
│       └── refresh_stats.py
├── db/
│   ├── models.py
│   └── queries.py
└── api/
    ├── main.py
    └── cohorts.py
```

This keeps:

- persistence in `db`
- application logic in `cohorts`
- transport contracts in `api`
- async recomputation wiring in `cohorts/inngest_functions`

## Concrete Schema Sketches

These are not final code, but they are intended to be close enough to review structure and naming.

## JSON Field Pattern

As a design rule, any `dict`-typed JSON field persisted on a SQLModel table should have:

- a raw storage field ending in `_json` where appropriate
- a typed accessor instance method
- a typed parsing classmethod

This should follow the same pattern already used elsewhere in `db/models.py`, for example:

- `parsed_ground_truth_rubric()`
- `_parse_ground_truth_rubric(...)`
- `parsed_task_tree()`
- `_parse_task_tree(...)`

We should not treat raw `dict` access as the main application API.

Recommended rule:

- DB tables may store JSON blobs
- application code should prefer typed accessor methods
- transport DTOs and service code should build on the typed view, not on raw dict indexing

### `db/models.py`

```python
from sqlmodel import SQLModel, Field, Column, Index
from sqlalchemy import JSON
from uuid import UUID, uuid4
from datetime import datetime
from pydantic import BaseModel


class SandboxConfigSnapshot(BaseModel):
    provider: str | None = None
    template_id: str | None = None
    timeout_seconds: int | None = None
    extras: dict = Field(default_factory=dict)


class DispatchConfigSnapshot(BaseModel):
    worker_model: str | None = None
    max_questions: int | None = None
    max_concurrent_runs: int | None = None
    max_retries: int | None = None
    extras: dict = Field(default_factory=dict)


class CohortMetadata(BaseModel):
    code_commit_sha: str | None = None
    repo_dirty: bool | None = None
    prompt_version: str | None = None
    worker_version: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    sandbox_config: SandboxConfigSnapshot = Field(default_factory=SandboxConfigSnapshot)
    dispatch_config: DispatchConfigSnapshot = Field(default_factory=DispatchConfigSnapshot)


class CohortStatsExtras(BaseModel):
    # Keep this small in v1 and grow only when concrete FE needs emerge.
    pass


class ExperimentCohort(SQLModel, table=True):
    __tablename__ = "experiment_cohorts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str | None = None
    created_by: str | None = None
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)

    def parsed_metadata(self) -> CohortMetadata:
        return self.__class__._parse_metadata(self.metadata_json)

    @classmethod
    def _parse_metadata(cls, data: dict | None) -> CohortMetadata:
        return CohortMetadata(**(data or {}))


class ExperimentCohortStats(SQLModel, table=True):
    __tablename__ = "experiment_cohort_stats"

    cohort_id: UUID = Field(foreign_key="experiment_cohorts.id", primary_key=True)
    total_runs: int = 0
    pending_runs: int = 0
    executing_runs: int = 0
    evaluating_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    average_score: float | None = None
    best_score: float | None = None
    worst_score: float | None = None
    average_duration_ms: int | None = None
    failure_rate: float = 0.0
    stats_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=_utcnow)

    def parsed_stats_json(self) -> CohortStatsExtras:
        return self.__class__._parse_stats_json(self.stats_json)

    @classmethod
    def _parse_stats_json(cls, data: dict | None) -> CohortStatsExtras:
        return CohortStatsExtras(**(data or {}))


class Run(SQLModel, table=True):
    # existing fields...
    cohort_id: UUID | None = Field(
        default=None,
        foreign_key="experiment_cohorts.id",
        index=True,
    )
```

Tightening note:

- `Run.cohort_id` should be nullable only for the migration phase
- once dispatch requires cohort name everywhere, the target steady state should be non-null `cohort_id`

If we add:

- `dispatch_metadata_json`

then it should follow the same pattern:

- `parsed_dispatch_metadata()`
- `_parse_dispatch_metadata(...)`

### `cohorts/schemas.py`

```python
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class CohortStatusCounts(BaseModel):
    total: int
    pending: int
    executing: int
    evaluating: int
    completed: int
    failed: int


class CohortSummaryDto(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    status_counts: CohortStatusCounts
    average_score: float | None = None
    best_score: float | None = None
    worst_score: float | None = None
    average_duration_ms: int | None = None
    failure_rate: float = 0.0
    metadata_summary: dict = Field(default_factory=dict)


class CohortRunRowDto(BaseModel):
    run_id: UUID
    cohort_id: UUID
    cohort_name: str
    benchmark_name: BenchmarkName
    experiment_id: UUID
    status: RunStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    running_duration_ms: int | None = None
    final_score: float | None = None
    error_summary: str | None = None


class CohortDetailDto(BaseModel):
    cohort: CohortSummaryDto
    runs: list[CohortRunRowDto]
```

The typed metadata view exposed by DTOs should preferably come from:

- `ExperimentCohort.parsed_metadata()`

rather than passing raw JSON through the service layer.

### `cohorts/service.py`

```python
class ExperimentCohortService:
    def get_or_create_by_name(self, name: str, metadata: dict | None = None) -> ExperimentCohort: ...
    def list_cohorts(self, limit: int = 50) -> list[CohortSummaryDto]: ...
    def get_cohort_detail(self, cohort_id: UUID) -> CohortDetailDto: ...
    def attach_run(self, run_id: UUID, cohort_id: UUID) -> Run: ...
```

### `cohorts/stats_service.py`

```python
class ExperimentCohortStatsService:
    def recompute(self, cohort_id: UUID) -> ExperimentCohortStats: ...
    def build_summary_dto(self, cohort_id: UUID) -> CohortSummaryDto: ...
```

### `cohorts/events.py`

```python
from typing import ClassVar
from uuid import UUID

from h_arcane.core._internal.events.base import InngestEventContract


class CohortUpdatedEvent(InngestEventContract):
    name: ClassVar[str] = "cohort/updated"

    cohort_id: UUID
    run_id: UUID | None = None
```

Tightening note:

- `run_id` may stay nullable here because some recomputes may be cohort-wide or administrative rather than caused by one identifiable run

## Query Methods To Add

The plan should also be reviewable at the query-layer level.

### `db/queries.py`

Add:

```python
class ExperimentCohortsQueries(BaseQueries[ExperimentCohort]):
    def get_by_name(self, name: str) -> ExperimentCohort | None: ...
    def list_recent(self, limit: int = 50) -> list[ExperimentCohort]: ...


class ExperimentCohortStatsQueries(BaseQueries[ExperimentCohortStats]):
    def get_by_cohort_id(self, cohort_id: UUID) -> ExperimentCohortStats | None: ...


class RunsQueries(BaseQueries[Run]):
    def get_by_cohort(self, cohort_id: UUID) -> list[Run]: ...
```

## Nullability Recommendations

Before implementation, the intended nullability policy should be:

### Should Stay Nullable

- `ExperimentCohort.description`
- `ExperimentCohort.created_by`
- `ExperimentCohortStats.average_score`
- `ExperimentCohortStats.best_score`
- `ExperimentCohortStats.worst_score`
- `ExperimentCohortStats.average_duration_ms`
- `CohortRunRowDto.completed_at`
- `CohortRunRowDto.running_duration_ms`
- `CohortRunRowDto.final_score`
- `CohortRunRowDto.error_summary`
- `CohortUpdatedEvent.run_id`

These are legitimately absent in normal system states.

### Should Be Tightened

- `ExperimentCohortStats.failure_rate` should be non-null and default to `0.0`
- `CohortSummaryDto.failure_rate` should be non-null and default to `0.0`
- `CohortSummaryDto.metadata_summary` should use `Field(default_factory=dict)`, not a bare `{}` default
- `CohortRunRowDto.benchmark_name` should use `BenchmarkName`, not plain `str`
- `CohortRunRowDto.status` should use `RunStatus`, not plain `str`

### Strongly Typed Accessor Requirement

For this cohort slice specifically, the following raw JSON storage fields should all get typed accessors:

- `ExperimentCohort.metadata_json`
- `ExperimentCohortStats.stats_json`
- `Run.dispatch_metadata_json` if introduced

This keeps the new cohort work aligned with the existing model pattern instead of introducing a looser JSON-access style.

### Nullable Only As A Migration Compromise

- `Run.cohort_id`

Recommendation:

- make it nullable for the schema migration and rollout
- treat non-null as the target invariant for all newly created runs

### Worth Revisiting In Existing Core Models

The current `Run` model sets:

- `started_at: datetime = Field(default_factory=_utcnow)`

That makes every run look started immediately on persistence.

Semantically, the cleaner long-term model is probably:

- `started_at: datetime | None = None`

and then set it explicitly when execution actually starts.

That is slightly wider than the cohort work, but it affects the correctness of cohort duration and run-row semantics, so it is worth considering during implementation.

## Endpoint / FE Contract Locations

If we expose cohort data over FastAPI rather than only internal Python calls, the minimal route layout should be:

### `api/cohorts.py`

```python
router = APIRouter(prefix="/cohorts", tags=["cohorts"])


@router.get("")
def list_cohorts() -> list[CohortSummaryDto]: ...


@router.get("/{cohort_id}")
def get_cohort_detail(cohort_id: UUID) -> CohortDetailDto: ...
```

Then wire it in:

### `api/main.py`

```python
from h_arcane.core._internal.api.cohorts import router as cohorts_router

app.include_router(cohorts_router)
```

## Dispatch Wiring Locations

The most likely current write path is still around task/run persistence and benchmark dispatch.

Recommended concrete touches:

### `task/persistence.py`

- extend `create_run_from_config(...)`
- extend `persist_run(...)`

### benchmark dispatch entrypoints

Likely affected files:

- `task/inngest_functions/benchmark_run_start.py`
- CLI or benchmark-runner modules that create runs directly

The dispatch path should accept:

- `cohort_name: str`
- optional `cohort_metadata: dict`

and resolve/create the cohort before persisting the run.

## Event Recompute Wiring Locations

A clean implementation path is:

- emit `CohortUpdatedEvent` after run lifecycle transitions
- have a small Inngest function recompute stats and then notify FE transport

Most likely lifecycle touchpoints:

- `task/inngest_functions/workflow_start.py`
- `task/inngest_functions/workflow_complete.py`
- `task/inngest_functions/workflow_failed.py`

Those do not all need to become cohort-aware directly.

An alternative is:

- one reusable helper called from those functions

## Test File Locations

To make implementation reviewable end-to-end, the test plan should also name concrete file locations.

### Backend State / Contract Tests

Suggested additions:

- `tests/contracts/test_experiment_cohort_service.py`
- `tests/contracts/test_experiment_cohort_stats_service.py`
- `tests/contracts/test_cohort_event_contracts.py`
- `tests/state/test_run_cohort_lineage.py`

These should prove:

- cohort creation and lookup
- run persistence with `cohort_id`
- aggregate stat recomputation
- mixed-benchmark membership
- FE-facing DTO shapes

## Suggested Minimal Slice

If we want the smallest vertical slice before broader eventing:

1. add schema changes in `db/models.py`
2. add queries in `db/queries.py`
3. add `cohorts/schemas.py`
4. add `cohorts/service.py`
5. make dispatch require `cohort_name`
6. add `GET /cohorts` and `GET /cohorts/{id}`
7. add tests for lineage + summary DTOs

Then, in the next slice:

8. add `ExperimentCohortStatsService`
9. add cohort update eventing
10. add FE tests against live-updating cohort summaries

## Services To Add

## `ExperimentCohortService`

Responsibilities:

- create cohort
- get cohort by name or id
- list cohorts
- attach runs to cohort

## `ExperimentCohortStatsService`

Responsibilities:

- recompute stats for one cohort
- expose cohort summary DTOs
- expose cohort detail DTOs

## `ExperimentDispatchService` Changes

Responsibilities:

- require cohort name
- resolve or create cohort
- create run with `cohort_id`
- snapshot reproducibility metadata at dispatch time

## Inngest / Event Handlers

Responsibilities:

- listen for run lifecycle changes
- recompute or update cohort stats
- emit FE-facing cohort update events

## Recommended Implementation Order

The sequence you suggested is broadly right, with one tweak:

1. backend cohort design doc
2. backend schema and service implementation
3. backend tests for cohort lineage, aggregates, and update events
4. FE seeded-state tests against the new backend contracts
5. FE implementation to satisfy those tests

I would not do:

- FE implementation before FE tests

because we now have a much clearer product contract than before.

## Required Backend Tests

At minimum, add tests proving:

### Cohort Lineage

- dispatch with cohort name creates or resolves the cohort
- created run persists `cohort_id`
- run detail can return breadcrumb cohort context

### Cohort Aggregation

- cohort stats count queued, executing, completed, and failed runs correctly
- averages and best/worst score update correctly on completion
- duration aggregates update correctly

### Mixed Benchmark Cohorts

- one cohort can contain runs from multiple benchmarks
- cohort detail query returns benchmark identity per run

### Eventing

- run lifecycle changes trigger cohort stats refresh
- cohort update event payload contains enough FE-facing information

## Migration Strategy

To avoid a large risky migration:

### Phase 1

- add `experiment_cohorts`
- add `experiment_cohort_stats`
- add nullable `runs.cohort_id`
- backfill nothing yet

### Phase 2

- make CLI and benchmark dispatch require cohort name
- all new runs get a cohort

### Phase 3

- add FE cohort queries and events
- build FE tests against those contracts

### Phase 4

- optionally backfill old runs into synthetic cohorts if needed

## Open Questions

These do not block the basic design, but should be decided during implementation:

- should cohort names be globally unique or namespaced?
- do we want soft-deleted or archived cohorts?
- how much reproducibility metadata should be normalized versus stored as JSON?
- should stats recompute synchronously on run updates or via async event handling?

## Recommendation

Implement:

- `ExperimentCohort`
- `ExperimentCohortStats`
- `Run.cohort_id`
- compulsory cohort name at dispatch
- cohort summary/detail queries
- cohort update events

That is the smallest clean backend shape that supports the FE we now actually want.
