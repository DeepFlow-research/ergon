---
status: rejected
opened: 2026-04-18
author: deepflow-research
architecture_refs: [docs/architecture/07_testing.md]
supersedes: []
superseded_by: docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md
---

# RFC: Test-harness API endpoints for Playwright-driven backend assertions

## Problem

The per-benchmark smoke pattern (see `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md`)
requires Playwright to drive the UI and then assert on the resulting backend state: which graph
mutations landed, which evaluations ran, what shape the run took in Postgres. No such read-only
harness endpoint exists today.

Playwright's two options without a harness are both unacceptable:

- **Direct Postgres query from TypeScript.** Brittle: any DB migration breaks the test. Cross-layer
  coupling: frontend tests end up encoding backend schema knowledge.
- **No backend assertion at all.** Playwright tests become shallow UI snapshots that cannot detect
  persistence regressions.

The FastAPI app is the canonical interface to backend state. The existing
`ergon_core/core/api/runs.py` `/runs/{run_id}` endpoint returns a full `RunSnapshotDto` but is
not designed for test-only write paths (seed, reset). Two gaps:

1. No endpoint returns the minimal, Playwright-stable shape needed to assert that a specific run
   has specific graph nodes, specific evaluations, and specific mutation events — the full
   `RunSnapshotDto` from `ergon_core/core/api/runs.py:517` is too large and coupling-heavy for
   test assertions.
2. No write endpoints exist for seeding a predefined fixture run or purging test-created rows;
   a smoke test's setup/teardown needs both.

A first-class test-harness router, mounted only when `ENABLE_TEST_HARNESS=1`, closes both gaps.
This RFC is a dependency of `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md`.

## Proposal

**Option chosen: conditional router mount gated on `ENABLE_TEST_HARNESS=1` (env var at startup).**

Add `ergon_core/core/api/test_harness.py` containing:

- A FastAPI `APIRouter` with prefix `/api/test`.
- Three routes: one read-only (`GET`), two writes (`POST`), each guarded separately by a
  `Depends` that checks `ENABLE_TEST_HARNESS`.
- Write routes additionally verify an `X-Test-Secret` header against `TEST_HARNESS_SECRET` env var.
- A Pydantic `TestRunStateDto` that is a stable, narrow wire shape for Playwright assertions —
  not a mirror of `RunSnapshotDto`.
- Mount the router in `ergon_core/core/api/app.py` only when `ENABLE_TEST_HARNESS=1` is set at
  startup.

The harness lives in one module so a future hosted deployment can add a startup assertion (`raise
if prod`) in a single place.

## Architecture overview

### Before

```
Playwright
    |
    | HTTP
    v
ergon-dashboard (Next.js)   ─── read run state ──>  /runs/{run_id}  (RunSnapshotDto, large)
                                                      ergon_core/core/api/runs.py:517
    |
    | (no backend write path, no stable narrow shape)
```

### After

```
Playwright
    |
    | HTTP (direct to FastAPI, same host as CI stack)
    v
/api/test/read/run/{id}/state   GET   ──>  TestRunStateDto (narrow, stable)
/api/test/write/run/seed        POST  ──>  seed a fixture run  (X-Test-Secret required)
/api/test/write/reset           POST  ──>  purge test-run ids  (X-Test-Secret required)
    |
    v
ergon_core/core/api/test_harness.py
    |
    v
ergon_core/core/persistence/  (RunRecord, RunGraphNode, RunGraphMutation, RunTaskEvaluation)
```

### App startup gate (conceptual)

```
app = FastAPI(...)
if os.getenv("ENABLE_TEST_HARNESS") == "1":
    app.include_router(test_harness_router)
# inngest.fast_api.serve(app, ...)  # unchanged
```

### Sequence: Playwright smoke assertion

```
1. CI compose stack starts api with ENABLE_TEST_HARNESS=1 + TEST_HARNESS_SECRET=ci-secret
2. Playwright calls POST /api/test/write/run/seed (X-Test-Secret: ci-secret)
   → inserts RunRecord + RunGraphNode rows into Postgres
3. Playwright drives the dashboard UI
4. Playwright calls GET /api/test/read/run/{id}/state
   → returns TestRunStateDto
5. Playwright asserts dto.graph_nodes[*].status == expected
6. Playwright calls POST /api/test/write/reset (X-Test-Secret: ci-secret)
   → purges rows with run_ids tagged as test-seeded
```

## Type / interface definitions

### `TestRunStateDto` — read model

```python
# ergon_core/ergon_core/core/api/test_harness.py (top of file — models first)

from __future__ import annotations

import os
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskEvaluation


class TestGraphNodeDto(BaseModel):
    """Minimal graph node shape for Playwright assertions."""

    model_config = ConfigDict(extra="forbid")

    id: str
    task_key: str
    status: str
    parent_node_id: str | None
    level: int


class TestEvaluationDto(BaseModel):
    """Minimal evaluation shape for Playwright assertions."""

    model_config = ConfigDict(extra="forbid")

    id: str
    score: float | None
    passed: bool | None


class TestGraphMutationDto(BaseModel):
    """One entry in the ordered mutation log."""

    model_config = ConfigDict(extra="forbid")

    sequence: int
    mutation_type: str
    target_type: str
    target_id: str
    actor: str


class TestRunStateDto(BaseModel):
    """Stable, narrow wire shape for Playwright-driven backend assertions.

    Intentionally smaller than RunSnapshotDto — contains only the fields
    that smokes need to assert on. New fields are additive and non-breaking.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str
    graph_nodes: list[TestGraphNodeDto] = Field(default_factory=list)
    evaluations: list[TestEvaluationDto] = Field(default_factory=list)
    mutations: list[TestGraphMutationDto] = Field(default_factory=list)
    created_at: str
```

### `SeedRunRequest` — write model

```python
class SeedRunRequest(BaseModel):
    """Body for POST /api/test/write/run/seed.

    Inserts a minimal RunRecord so Playwright can assert on a known run_id
    without running the full Inngest pipeline. The run is tagged in
    summary_json with _test_seeded=true so the reset endpoint can purge it.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    experiment_definition_id: str
    status: str = "completed"
    benchmark_type: str = "smoke-test"
```

### `ResetRequest` — write model

```python
class ResetRequest(BaseModel):
    """Body for POST /api/test/write/reset.

    Optional: restrict purge to a specific run_id list. Absent = purge all
    rows tagged with _test_seeded=true.
    """

    model_config = ConfigDict(extra="forbid")

    run_ids: list[str] | None = None
```

## Full implementation

### `ergon_core/core/api/test_harness.py` (complete file)

```python
# ergon_core/ergon_core/core/api/test_harness.py

"""Test-harness FastAPI router.

Mounted on the main app only when ENABLE_TEST_HARNESS=1 is set at startup.
Provides three endpoints:

  GET  /api/test/read/run/{id}/state  — narrow TestRunStateDto for assertions
  POST /api/test/write/run/seed       — insert a fixture RunRecord
  POST /api/test/write/reset          — purge test-seeded rows

Write endpoints require X-Test-Secret matching TEST_HARNESS_SECRET env var.

This module is the single gate for future prod-deployment checks. Add a
startup assertion here if this service is ever hosted outside dev/CI.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskEvaluation
from ergon_core.core.utils import utcnow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class TestGraphNodeDto(BaseModel):
    """Minimal graph node shape for Playwright assertions."""

    model_config = ConfigDict(extra="forbid")

    id: str
    task_key: str
    status: str
    parent_node_id: str | None
    level: int


class TestEvaluationDto(BaseModel):
    """Minimal evaluation shape for Playwright assertions."""

    model_config = ConfigDict(extra="forbid")

    id: str
    score: float | None
    passed: bool | None


class TestGraphMutationDto(BaseModel):
    """One entry in the ordered mutation log."""

    model_config = ConfigDict(extra="forbid")

    sequence: int
    mutation_type: str
    target_type: str
    target_id: str
    actor: str


class TestRunStateDto(BaseModel):
    """Stable, narrow wire shape for Playwright-driven backend assertions.

    Intentionally smaller than RunSnapshotDto — contains only the fields
    smokes assert on. New fields are additive and non-breaking.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str
    graph_nodes: list[TestGraphNodeDto] = Field(default_factory=list)
    evaluations: list[TestEvaluationDto] = Field(default_factory=list)
    mutations: list[TestGraphMutationDto] = Field(default_factory=list)
    created_at: str


class SeedRunRequest(BaseModel):
    """Body for POST /api/test/write/run/seed."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    experiment_definition_id: str
    status: str = "completed"
    benchmark_type: str = "smoke-test"


class ResetRequest(BaseModel):
    """Body for POST /api/test/write/reset.

    Absent run_ids = purge all rows tagged _test_seeded=true.
    """

    model_config = ConfigDict(extra="forbid")

    run_ids: list[str] | None = None


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

_HARNESS_ENABLED = os.getenv("ENABLE_TEST_HARNESS") == "1"
_HARNESS_SECRET = os.getenv("TEST_HARNESS_SECRET", "")  # slopcop: ignore[no-str-empty-default]

# Sentinel key stored in RunRecord.summary_json so the reset endpoint can
# identify and purge test-seeded rows without touching non-test data.
_TEST_SEED_KEY = "_test_seeded"


def _require_harness_enabled() -> None:
    """FastAPI dependency: 404 if ENABLE_TEST_HARNESS != 1."""
    if not _HARNESS_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")


def _require_write_secret(x_test_secret: str = Header(...)) -> None:  # noqa: B008
    """FastAPI dependency: 401 if X-Test-Secret doesn't match TEST_HARNESS_SECRET.

    Applied only to write endpoints. Read endpoint is intentionally
    secret-free: it surfaces no private data beyond what is already
    visible to anyone who can reach the API port.
    """
    if not _HARNESS_SECRET:
        raise HTTPException(
            status_code=500,
            detail="TEST_HARNESS_SECRET not set — write endpoints are disabled",
        )
    if x_test_secret != _HARNESS_SECRET:
        raise HTTPException(status_code=401, detail="Invalid X-Test-Secret")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/test",
    tags=["test-harness"],
    dependencies=[Depends(_require_harness_enabled)],
)


# ---------------------------------------------------------------------------
# Read endpoint
# ---------------------------------------------------------------------------


@router.get("/read/run/{run_id}/state", response_model=TestRunStateDto)
def get_run_state(run_id: UUID) -> TestRunStateDto:
    """Return a minimal, stable run state for Playwright backend assertions.

    Read-only. No secret required. Returns 404 if run_id does not exist.
    """
    with get_session() as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        nodes = list(
            session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all()
        )
        evaluations = list(
            session.exec(
                select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
            ).all()
        )
        mutations = list(
            session.exec(
                select(RunGraphMutation)
                .where(RunGraphMutation.run_id == run_id)
                .order_by(RunGraphMutation.sequence)
            ).all()
        )

    return TestRunStateDto(
        run_id=str(run.id),
        status=run.status,
        created_at=run.created_at.isoformat(),
        graph_nodes=[
            TestGraphNodeDto(
                id=str(n.id),
                task_key=n.task_key,
                status=n.status,
                parent_node_id=str(n.parent_node_id) if n.parent_node_id else None,
                level=n.level,
            )
            for n in nodes
        ],
        evaluations=[
            TestEvaluationDto(
                id=str(e.id),
                score=e.score,
                passed=e.passed if hasattr(e, "passed") else None,
            )
            for e in evaluations
        ],
        mutations=[
            TestGraphMutationDto(
                sequence=m.sequence,
                mutation_type=m.mutation_type,
                target_type=m.target_type,
                target_id=str(m.target_id),
                actor=m.actor,
            )
            for m in mutations
        ],
    )


# ---------------------------------------------------------------------------
# Write endpoints
# ---------------------------------------------------------------------------


@router.post("/write/run/seed", status_code=201)
def seed_run(
    body: SeedRunRequest,
    _secret: None = Depends(_require_write_secret),  # noqa: B008
) -> dict[str, str]:
    """Insert a minimal fixture RunRecord tagged as test-seeded.

    The run is tagged in summary_json with _test_seeded=true so the reset
    endpoint can purge it without touching non-test rows. The
    experiment_definition_id must reference a row that already exists in
    experiment_definitions; pass a known definition or create one separately.

    Returns {"run_id": "<uuid>"}.
    """
    try:
        run_uuid = UUID(body.run_id)
        def_uuid = UUID(body.experiment_definition_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid UUID: {exc}") from exc

    with get_session() as session:
        existing = session.get(RunRecord, run_uuid)
        if existing is not None:
            raise HTTPException(status_code=409, detail=f"Run {run_uuid} already exists")

        run = RunRecord(
            id=run_uuid,
            experiment_definition_id=def_uuid,
            status=RunStatus(body.status),
            summary_json={
                _TEST_SEED_KEY: True,
                "benchmark_type": body.benchmark_type,
            },
        )
        session.add(run)
        session.commit()

    logger.info("test-harness seeded run_id=%s", run_uuid)
    return {"run_id": str(run_uuid)}


@router.post("/write/reset", status_code=200)
def reset_test_runs(
    body: ResetRequest,
    _secret: None = Depends(_require_write_secret),  # noqa: B008
) -> dict[str, int]:
    """Purge test-seeded RunRecord rows (and their cascade-deleted children).

    If body.run_ids is provided, only those run_ids are purged (provided
    they are tagged _test_seeded=true). If absent, all test-seeded rows
    are purged.

    Relies on DB-level CASCADE deletes for RunGraphNode, RunGraphMutation,
    RunTaskEvaluation, RunTaskExecution, and RunContextEvent rows. Confirmed
    cascade is set on foreign keys in the migration history.

    Returns {"deleted": N}.
    """
    with get_session() as session:
        stmt = select(RunRecord)
        if body.run_ids is not None:
            try:
                uuids = [UUID(r) for r in body.run_ids]
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"Invalid UUID: {exc}") from exc
            stmt = stmt.where(RunRecord.id.in_(uuids))  # type: ignore[union-attr]

        candidates = list(session.exec(stmt).all())
        to_delete = [
            r for r in candidates if r.parsed_summary().get(_TEST_SEED_KEY) is True
        ]

        for run in to_delete:
            session.delete(run)
        session.commit()

    deleted = len(to_delete)
    logger.info("test-harness reset deleted=%d", deleted)
    return {"deleted": deleted}
```

### `ergon_core/core/api/app.py` — exact diff for mount wiring

```diff
--- a/ergon_core/ergon_core/core/api/app.py
+++ b/ergon_core/ergon_core/core/api/app.py
@@ -1,6 +1,8 @@
 """FastAPI application with Inngest webhook registration."""
 
+import os
 import logging
 from contextlib import asynccontextmanager
 
 import inngest.fast_api
 from ergon_core.core.api.cohorts import router as cohorts_router
+from ergon_core.core.api.test_harness import router as test_harness_router
 from ergon_core.core.api.rollouts import init_service as init_rollout_service
 from ergon_core.core.api.rollouts import router as rollouts_router
 from ergon_core.core.api.runs import router as runs_router
@@ -38,6 +40,10 @@ app.include_router(runs_router)
 app.include_router(cohorts_router)
 app.include_router(rollouts_router)
 
+if os.getenv("ENABLE_TEST_HARNESS") == "1":
+    app.include_router(test_harness_router)
+    logger.info("test-harness router mounted — ENABLE_TEST_HARNESS=1")
+
 inngest.fast_api.serve(app, inngest_client, ALL_FUNCTIONS)
```

### `ergon_core/core/api/app.py` — full file after changes

```python
# ergon_core/ergon_core/core/api/app.py

"""FastAPI application with Inngest webhook registration."""

import logging
import os
from contextlib import asynccontextmanager

import inngest.fast_api
from ergon_core.core.api.cohorts import router as cohorts_router
from ergon_core.core.api.rollouts import init_service as init_rollout_service
from ergon_core.core.api.rollouts import router as rollouts_router
from ergon_core.core.api.runs import router as runs_router
from ergon_core.core.api.test_harness import router as test_harness_router
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.rl.rollout_service import RolloutService
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.inngest_registry import ALL_FUNCTIONS
from ergon_core.core.settings import Settings
from fastapi import FastAPI

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting ensure_db...")
    ensure_db()
    logger.info("ensure_db done, initializing RolloutService...")
    settings = Settings()
    init_rollout_service(
        RolloutService(
            session_factory=get_session,
            inngest_send=inngest_client.send_sync,
            tokenizer_name=settings.default_tokenizer,
        )
    )
    logger.info("ready")
    yield


app = FastAPI(
    title="Ergon Core",
    description="Ergon experiment orchestration API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(runs_router)
app.include_router(cohorts_router)
app.include_router(rollouts_router)

if os.getenv("ENABLE_TEST_HARNESS") == "1":
    app.include_router(test_harness_router)
    logger.info("test-harness router mounted — ENABLE_TEST_HARNESS=1")

inngest.fast_api.serve(app, inngest_client, ALL_FUNCTIONS)
```

### `ergon-dashboard/tests/helpers/testHarnessClient.ts` (new file — backend harness)

The existing `ergon-dashboard/tests/helpers/harnessClient.ts` targets the Next.js
`/api/test/dashboard/…` routes (in-memory frontend state). This new file targets the FastAPI
backend harness routes.

```typescript
// ergon-dashboard/tests/helpers/testHarnessClient.ts

/**
 * Playwright helper for the FastAPI test-harness endpoints.
 *
 * Distinct from harnessClient.ts, which targets the Next.js /api/test/dashboard/*
 * routes (in-memory frontend state). This client targets the FastAPI backend:
 *   GET  /api/test/read/run/{id}/state
 *   POST /api/test/write/run/seed
 *   POST /api/test/write/reset
 *
 * Usage:
 *   const harness = new BackendHarnessClient(request, process.env.ERGON_API_BASE_URL!);
 *   await harness.seedRun({ run_id: "...", experiment_definition_id: "..." });
 *   const state = await harness.getRunState(runId);
 *   expect(state.status).toBe("completed");
 *   await harness.reset();
 */

import type { APIRequestContext } from "@playwright/test";

const TEST_SECRET = process.env.TEST_HARNESS_SECRET ?? "ci-secret";

export interface TestGraphNodeDto {
  id: string;
  task_key: string;
  status: string;
  parent_node_id: string | null;
  level: number;
}

export interface TestEvaluationDto {
  id: string;
  score: number | null;
  passed: boolean | null;
}

export interface TestGraphMutationDto {
  sequence: number;
  mutation_type: string;
  target_type: string;
  target_id: string;
  actor: string;
}

export interface TestRunStateDto {
  run_id: string;
  status: string;
  graph_nodes: TestGraphNodeDto[];
  evaluations: TestEvaluationDto[];
  mutations: TestGraphMutationDto[];
  created_at: string;
}

export interface SeedRunPayload {
  run_id: string;
  experiment_definition_id: string;
  status?: string;
  benchmark_type?: string;
}

export interface ResetPayload {
  run_ids?: string[];
}

export class BackendHarnessClient {
  constructor(
    private readonly request: APIRequestContext,
    private readonly baseUrl: string,
  ) {}

  async getRunState(runId: string): Promise<TestRunStateDto> {
    const response = await this.request.get(
      `${this.baseUrl}/api/test/read/run/${runId}/state`,
    );
    if (!response.ok()) {
      throw new Error(
        `GET /api/test/read/run/${runId}/state failed: ${response.status()}`,
      );
    }
    return response.json() as Promise<TestRunStateDto>;
  }

  async seedRun(payload: SeedRunPayload): Promise<{ run_id: string }> {
    const response = await this.request.post(
      `${this.baseUrl}/api/test/write/run/seed`,
      {
        data: payload,
        headers: { "X-Test-Secret": TEST_SECRET },
      },
    );
    if (!response.ok()) {
      throw new Error(
        `POST /api/test/write/run/seed failed: ${response.status()}`,
      );
    }
    return response.json() as Promise<{ run_id: string }>;
  }

  async reset(payload: ResetPayload = {}): Promise<{ deleted: number }> {
    const response = await this.request.post(
      `${this.baseUrl}/api/test/write/reset`,
      {
        data: payload,
        headers: { "X-Test-Secret": TEST_SECRET },
      },
    );
    if (!response.ok()) {
      throw new Error(
        `POST /api/test/write/reset failed: ${response.status()}`,
      );
    }
    return response.json() as Promise<{ deleted: number }>;
  }
}
```

## Package structure

No new Python packages. `test_harness.py` is a new module inside the existing
`ergon_core/ergon_core/core/api/` package. The package `__init__.py` at
`ergon_core/ergon_core/core/api/__init__.py` does not need updating — routers
are imported directly by `app.py`.

## Implementation order

| Step | Phase | What | Files touched |
|------|-------|------|---------------|
| 1 | PR 1 | Add `TestRunStateDto`, `SeedRunRequest`, `ResetRequest`, `get_run_state`, `seed_run`, `reset_test_runs`, `_require_harness_enabled`, `_require_write_secret` to new `test_harness.py` | ADD `ergon_core/ergon_core/core/api/test_harness.py` |
| 2 | PR 1 | Import `test_harness_router` in `app.py`; add `if os.getenv("ENABLE_TEST_HARNESS") == "1": app.include_router(...)` guard | MODIFY `ergon_core/ergon_core/core/api/app.py` |
| 3 | PR 1 | Unit tests: harness disabled → 404; enabled → 200; secret mismatch → 401; unknown run_id → 404; seed + read round-trip; reset purges only tagged rows | ADD `tests/unit/test_test_harness.py` |
| 4 | PR 1 | Add `BackendHarnessClient` TypeScript helper | ADD `ergon-dashboard/tests/helpers/testHarnessClient.ts` |
| 5 | PR 2 | Wire `ENABLE_TEST_HARNESS=1` and `TEST_HARNESS_SECRET=ci-secret` into `docker-compose.ci.yml` api service env block | MODIFY `docker-compose.ci.yml` |
| 6 | PR 2 | Add integration test: seed a run via the harness, run the smoke-test benchmark, read state back, assert mutations and evaluations present | ADD `tests/integration/smokes/test_smoke_harness.py` |
| 7 | PR 2 | Add a first Playwright smoke that uses `BackendHarnessClient.getRunState()` after driving the dashboard UI | ADD `ergon-dashboard/tests/e2e/smoke.harness.spec.ts` |

PRs 1 and 2 are independent after PR 1 lands. PR 2 depends on PR 1 for the FastAPI side, and on
`docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md` for `FixedDelegationStubWorker`.

## File map

### ADD

| File | Purpose |
|------|---------|
| `ergon_core/ergon_core/core/api/test_harness.py` | FastAPI router: DTOs, three endpoints, `_require_harness_enabled` + `_require_write_secret` dependencies |
| `tests/unit/test_test_harness.py` | Unit tests: gate, secret, round-trip, reset |
| `ergon-dashboard/tests/helpers/testHarnessClient.ts` | Playwright `BackendHarnessClient` class |
| `tests/integration/smokes/test_smoke_harness.py` | Integration test: seed → benchmark → assert via harness read |
| `ergon-dashboard/tests/e2e/smoke.harness.spec.ts` | Playwright smoke using `BackendHarnessClient.getRunState()` |

### MODIFY

| File | Change |
|------|--------|
| `ergon_core/ergon_core/core/api/app.py` | Import `test_harness_router`; conditional `include_router` on `ENABLE_TEST_HARNESS=1`; add `import os` |
| `docker-compose.ci.yml` | Add `ENABLE_TEST_HARNESS=1` and `TEST_HARNESS_SECRET=ci-secret` to `api` service env block |

## Testing approach

### Unit tests — `tests/unit/test_test_harness.py`

```python
# tests/unit/test_test_harness.py

"""Unit tests for the test-harness FastAPI router.

Uses TestClient against the real app with ENABLE_TEST_HARNESS toggled via
monkeypatch. Uses in-memory SQLite (state conftest) for persistence.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


class TestGateDisabled:
    """When ENABLE_TEST_HARNESS != 1, the router is not mounted."""

    def test_read_returns_404_when_harness_disabled(self) -> None:
        # Import app without the harness env var set
        with patch.dict("os.environ", {}, clear=False):
            # Remove key if present
            import os
            os.environ.pop("ENABLE_TEST_HARNESS", None)
            # Re-import to get fresh app without router
            import importlib
            import ergon_core.core.api.app as app_module
            importlib.reload(app_module)
            client = TestClient(app_module.app)
            run_id = uuid4()
            resp = client.get(f"/api/test/read/run/{run_id}/state")
            assert resp.status_code == 404


class TestGateEnabled:
    """When ENABLE_TEST_HARNESS=1 + TEST_HARNESS_SECRET set, endpoints are live."""

    @pytest.fixture(autouse=True)
    def _patch_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENABLE_TEST_HARNESS", "1")
        monkeypatch.setenv("TEST_HARNESS_SECRET", "test-secret-123")

    def test_read_unknown_run_returns_404(self) -> None:
        from ergon_core.core.api.test_harness import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        resp = client.get(f"/api/test/read/run/{uuid4()}/state")
        assert resp.status_code == 404

    def test_write_without_secret_returns_401(self) -> None:
        from ergon_core.core.api.test_harness import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        resp = client.post(
            "/api/test/write/reset",
            json={},
            headers={"X-Test-Secret": "wrong-secret"},
        )
        assert resp.status_code == 401

    def test_write_correct_secret_accepted(self) -> None:
        from ergon_core.core.api.test_harness import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        resp = client.post(
            "/api/test/write/reset",
            json={},
            headers={"X-Test-Secret": "test-secret-123"},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0

    def test_seed_then_read_round_trip(self) -> None:
        """Seed a run via POST, then read it back via GET."""
        from ergon_core.core.api.test_harness import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # Requires a live DB session — this test belongs in integration tier
        # if run against real Postgres; shown here with the correct interface.
        pytest.skip("Requires Postgres — run in integration tier (tests/integration/)")


class TestResetPurgesOnlyTaggedRows:
    """reset only touches rows with _test_seeded=true in summary_json."""

    def test_reset_does_not_delete_real_runs(self) -> None:
        # Integration test — see tests/integration/smokes/test_smoke_harness.py
        pytest.skip("Requires Postgres — run in integration tier")
```

### Integration test — `tests/integration/smokes/test_smoke_harness.py`

```python
# tests/integration/smokes/test_smoke_harness.py

"""Integration smoke: seed via harness, assert state via harness read.

Requires: ENABLE_TEST_HARNESS=1, TEST_HARNESS_SECRET set, Postgres live.
Run against docker-compose.ci.yml.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

ERGON_API = "http://localhost:9000"
SECRET = "ci-secret"


@pytest.fixture(autouse=True)
def _harness_reset():
    """Purge test rows before and after each test."""
    httpx.post(
        f"{ERGON_API}/api/test/write/reset",
        json={},
        headers={"X-Test-Secret": SECRET},
        timeout=10,
    )
    yield
    httpx.post(
        f"{ERGON_API}/api/test/write/reset",
        json={},
        headers={"X-Test-Secret": SECRET},
        timeout=10,
    )


def test_seed_and_read_run_state() -> None:
    """Seed a fixture run; assert GET returns matching state."""
    run_id = str(uuid4())
    def_id = str(uuid4())

    seed_resp = httpx.post(
        f"{ERGON_API}/api/test/write/run/seed",
        json={
            "run_id": run_id,
            "experiment_definition_id": def_id,
            "status": "completed",
            "benchmark_type": "smoke-test",
        },
        headers={"X-Test-Secret": SECRET},
        timeout=10,
    )
    assert seed_resp.status_code == 201, seed_resp.text
    assert seed_resp.json()["run_id"] == run_id

    read_resp = httpx.get(
        f"{ERGON_API}/api/test/read/run/{run_id}/state",
        timeout=10,
    )
    assert read_resp.status_code == 200, read_resp.text
    state = read_resp.json()
    assert state["run_id"] == run_id
    assert state["status"] == "completed"
    assert isinstance(state["graph_nodes"], list)
    assert isinstance(state["evaluations"], list)
    assert isinstance(state["mutations"], list)


def test_reset_purges_only_test_runs() -> None:
    """reset does not delete non-test-seeded rows."""
    run_id = str(uuid4())
    def_id = str(uuid4())

    # Seed a test run
    httpx.post(
        f"{ERGON_API}/api/test/write/run/seed",
        json={"run_id": run_id, "experiment_definition_id": def_id},
        headers={"X-Test-Secret": SECRET},
        timeout=10,
    )

    # Confirm it exists
    assert httpx.get(f"{ERGON_API}/api/test/read/run/{run_id}/state", timeout=10).status_code == 200

    # Reset
    reset_resp = httpx.post(
        f"{ERGON_API}/api/test/write/reset",
        json={"run_ids": [run_id]},
        headers={"X-Test-Secret": SECRET},
        timeout=10,
    )
    assert reset_resp.json()["deleted"] == 1

    # Run should no longer exist
    assert httpx.get(f"{ERGON_API}/api/test/read/run/{run_id}/state", timeout=10).status_code == 404
```

### Playwright contract test — `ergon-dashboard/tests/e2e/smoke.harness.spec.ts`

```typescript
// ergon-dashboard/tests/e2e/smoke.harness.spec.ts

import { expect, test } from "@playwright/test";

import { BackendHarnessClient } from "../helpers/testHarnessClient";
import { FIXTURE_IDS } from "../helpers/dashboardFixtures";
import { resetHarness, seedHarness } from "../helpers/harnessClient";
import { createDashboardSeed } from "../helpers/dashboardFixtures";

const ERGON_API = process.env.ERGON_API_BASE_URL ?? "http://localhost:9000";

test.skip(
  process.env.ENABLE_TEST_HARNESS !== "1",
  "Backend harness smoke requires ENABLE_TEST_HARNESS=1",
);

test.beforeEach(async ({ request }) => {
  // Seed the Next.js in-memory state (for UI rendering)
  await resetHarness(request);
  await seedHarness(request, createDashboardSeed());
  // Reset backend test rows
  const harness = new BackendHarnessClient(request, ERGON_API);
  await harness.reset();
});

test.afterEach(async ({ request }) => {
  const harness = new BackendHarnessClient(request, ERGON_API);
  await harness.reset();
});

test("backend harness read endpoint returns run state after smoke benchmark", async ({
  request,
  page,
}) => {
  // This test requires the smoke benchmark to have produced a run with a known ID.
  // In CI, the benchmark is pre-run by the integration tier; the Playwright suite
  // then uses the harness read endpoint to assert backend state. The run_id is
  // passed via SMOKE_RUN_ID env var from the integration job.
  const runId = process.env.SMOKE_RUN_ID;
  test.skip(!runId, "Set SMOKE_RUN_ID to target a real run from the integration smoke");

  const harness = new BackendHarnessClient(request, ERGON_API);
  const state = await harness.getRunState(runId!);

  expect(state.status).toBe("completed");
  expect(state.graph_nodes.length).toBeGreaterThan(0);
  expect(state.evaluations.length).toBeGreaterThan(0);

  // Every leaf node should be in a terminal status
  for (const node of state.graph_nodes) {
    if (node.level > 0) {
      expect(["completed", "failed", "cancelled"]).toContain(node.status);
    }
  }

  // Navigate to the run page and assert the dashboard renders
  await page.goto(`/run/${runId}`);
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
});
```

## Trace / observability impact

Test-harness endpoints intentionally emit **no spans, no metrics**. Rationale:

- These routes exist only in the harness-enabled stack (local / CI). No span data lands in
  production.
- Adding spans would pollute the telemetry backend with test-generated noise if someone leaves
  `ENABLE_TEST_HARNESS=1` on for a longer-running stack.
- Application logs (`logger.info`) are emitted on `seed_run` and `reset_test_runs` so CI logs
  show what the harness wrote and deleted. This is sufficient for debugging.

If a future hosted deployment needs audit-level tracing of harness calls, add a dedicated span
under a `test-harness` service name at that point. Not in scope for v1.

## Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `ENABLE_TEST_HARNESS=1` set in production | All three routes exposed; writes unprotected except by `X-Test-Secret` | (1) No hosted deployment exists today — not an immediate concern. (2) The `_require_harness_enabled` dependency returns 404 for all harness routes when env var is absent. (3) Future: add a startup assertion (`raise RuntimeError` if `NODE_ENV == production` and harness enabled) in `test_harness.py` before the first hosted deployment. |
| `TEST_HARNESS_SECRET` not set when harness is enabled | Write endpoints return HTTP 500, blocking CI | Add `docker-compose.ci.yml` env entry `TEST_HARNESS_SECRET=ci-secret` in Step 5. The `_require_write_secret` dependency returns 500 (not 401) when the secret itself is missing, so misconfiguration is distinguishable from wrong-key. |
| `reset` deletes non-test rows if `_test_seeded` sentinel is missing | Production data loss | `reset` queries only rows where `summary_json._test_seeded == true`. `seed_run` always writes this key. Non-test rows written by the Inngest pipeline never set it. |
| Seed endpoint writes a `RunRecord` with a `definition_id` that does not exist in `experiment_definitions` | FK violation → 500 | Callers must pass a valid `experiment_definition_id`. Integration test creates the definition first or uses a known pre-seeded one. Document in endpoint docstring. If FK enforcement is a recurring issue, add a pre-check in `seed_run` that returns 422 with a clear message. |
| `reset` cascade behavior changes if FK cascade is removed from a migration | Dangling orphan rows accumulate | The reset implementation deletes `RunRecord`; children are removed by cascade. The cascade policy is established in `migrations/`. If a migration removes cascade, the reset endpoint will accumulate orphan rows silently. Track: any migration touching `runs` FK cascade must update this endpoint. |
| `TestRunStateDto` shape grows to mirror `RunSnapshotDto` | DTO becomes coupling-heavy, defeating its purpose | Explicit constraint: `TestRunStateDto` contains only fields that test assertions actually use. New fields require a PR touching this RFC's invariants section. |
| Playwright test that reads backend state races against async Inngest pipeline | Flaky timing failures | Use polling in `BackendHarnessClient.getRunState()` (not yet implemented in v1). For v1, the test waits for the benchmark to complete before calling the harness read endpoint. Polling is a PR-2 follow-up if flakiness is observed. |

## Invariants affected

From `docs/architecture/07_testing.md §7`:

- **Extended:** "Test-harness endpoints (`/api/test/read/*`, `/api/test/write/*`) that mount only
  when `ENABLE_TEST_HARNESS=1`" — this RFC is the implementation. On acceptance, update §7 to
  reference the landed route paths and confirm the write-gating mechanism.
- **New (this RFC):** `TestRunStateDto` is the canonical stable wire shape for Playwright backend
  assertions. Tests MUST NOT assert against `RunSnapshotDto` from `/runs/{run_id}` — that DTO is
  sized for the frontend and will change more frequently.
- **Preserved:** The router MUST NOT mount unless `ENABLE_TEST_HARNESS=1` is set. Enforced by
  the conditional `include_router` in `app.py`. The `_require_harness_enabled` dependency is a
  second safety net if the conditional is bypassed (e.g. dynamic router registration). Both are
  required.
- **Preserved from §4:** Tests exercising graph semantics MUST run against real Postgres and real
  Inngest. The harness seed endpoint creates a `RunRecord` — it does not bypass Inngest for
  running the pipeline. Smoke tests that use the seed endpoint to set up assertion state still
  drive the actual benchmark pipeline through Inngest.

## Alternatives considered

- **Playwright opens a direct Postgres client.** Rejected. Cross-layer coupling; every DB schema
  change breaks a frontend test; the frontend test suite ends up caring about SQL. Fragile.
- **Shared state via test DB fixtures only (no harness API).** Rejected. Playwright cannot
  introspect async event arrival through Inngest; it needs a live read path to know when graph
  mutations have actually landed.
- **Bake the harness into the existing dashboard API with a special header.** Rejected. Keeps
  surface concentrated but loses the environment-variable gate and makes a future prod deployment
  harder to reason about. Separate module is the right abstraction.
- **Return `RunSnapshotDto` from the read endpoint.** Rejected. `RunSnapshotDto` is a large,
  frequently-evolving DTO sized for the frontend. Asserting against it in tests would make tests
  brittle to frontend schema changes. A purpose-built narrow DTO is the correct abstraction.
- **Use `GET /runs/{run_id}` (existing endpoint) for Playwright backend assertions.** Rejected.
  That endpoint requires a full populated run (definition, workers, evaluation rows). The harness
  read endpoint works with a seed-only row and returns a shape that is explicit about what it
  guarantees.

## Open questions

- Which module owns `TestRunStateDto`, `ergon_core/core/api/` or
  `ergon_core/core/persistence/`? **Decision:** `ergon_core/core/api/test_harness.py` — the
  harness is an API surface, and the DTO is an explicitly stable wire shape rather than an
  internal persistence type. Not moving it.
- Should the harness expose a WebSocket to watch live mutations, or is polling sufficient? Polling
  in the first cut; revisit if a smoke ends up flaky waiting for events.
- What is the retention policy for test-run rows created via the seed endpoint? Auto-purge on
  `reset` (implemented). A periodic sweeper in CI (e.g. a CI job that runs `reset` with no body
  at the end of every workflow) is a follow-up.
- Should `seed_run` accept a list of `RunGraphNode` records so the read endpoint returns a
  populated `graph_nodes` list for tests that don't run the full pipeline? Not in v1 — the
  integration smoke runs the real pipeline and then asserts. If a pure-fixture path is needed for
  offline assertions, add it in a follow-up.

## On acceptance

When this RFC moves from `active/` to `accepted/`, also:
  - Update `docs/architecture/07_testing.md` section 6 to reflect the landed routes and their
    exact paths, and confirm the write-gating mechanism.
  - Update `docs/architecture/01_public_api.md` extension points section to list the harness
    router under "test-only extension points — not part of the public API contract."
  - Link the implementation plan in
    `docs/superpowers/plans/2026-04-??-test-harness-endpoints.md`.
  - Mark `TEST_HARNESS_SECRET` as a required CI secret in the repository's CI runbook.
