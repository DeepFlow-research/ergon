---
status: active
opened: 2026-04-18
author: deepflow-research
architecture_refs: [docs/architecture/07_testing.md]
supersedes: []
superseded_by: null
---

# RFC: Testing posture reset — retire `tests/state/`, merge into real-infrastructure integration tier

## 1. Problem

### 1.1 Current state

`tests/state/` contains **37 test files** (40 items counting `conftest.py`,
`factories.py`, `mocks.py`). Every test in this directory runs against an
in-memory SQLite engine constructed in `tests/state/conftest.py:18`:

```python
# tests/state/conftest.py:18
e = create_engine("sqlite://", connect_args={"check_same_thread": False})
```

A module-scoped engine is shared; each test gets a per-test transaction that
is rolled back on teardown (`tests/state/conftest.py:22-30`). No Inngest
runtime is involved. Service classes are called directly.

Production runs on the exact opposite stack:

- Real Postgres 15 with advisory locks, row-level isolation, typed JSON
  columns, `listen/notify` — all absent from SQLite.
- Service-class methods invoked as bodies of Inngest functions triggered by
  `inngest.TriggerEvent`, not via direct Python calls.
- Alembic-managed schema; SQLite cannot exercise migration edge cases.

When a `tests/state/` test passes it proves the service class behaves
correctly in a setup that does not match production.

### 1.2 Affected files (exhaustive)

The 37 test files break into three categories. Classification is based on
what infrastructure they actually exercise:

**pure** — no SQLite session, no DB round-trip; tests pure Python logic
(Pydantic models, validators, pure functions, CLI I/O, registry keys).
These belong in `tests/unit/` unchanged:

| File | What it tests |
|---|---|
| `test_type_invariants.py` | Enum/Literal field rejection at construction time |
| `test_env_writer.py` | `.env` file writer pure I/O (tmp_path) |
| `test_event_schema_phase0.py` | Pydantic model construction for event DTOs |
| `test_generation_turn_build.py` | `_build_turns()` pure function on `GenerationTurn` |
| `test_llm_judge_runtime_injection.py` | `EvaluationContext` pure construction + DI |
| `test_onboard_profile.py` | `OnboardProfile.required_keys()` pure logic |
| `test_onboard_wizard.py` | Onboard wizard with monkeypatched I/O (no DB) |
| `test_research_rubrics_benchmark.py` | Registry key lookup (no DB) |
| `test_research_rubrics_workers.py` | Worker instantiation + tool set with mocks |
| `test_subtask_lifecycle_toolkit.py` | Toolkit tool-count assertion (pure) |
| `test_criteria_do_not_spawn_sandboxes.py` | Static lint on source files (xfail) |

**graph** — uses the SQLite session fixture to exercise repository or
service semantics; must be rewritten against real Postgres + Inngest:

| File | What it tests |
|---|---|
| `test_propagation.py` | DAG propagation invariants via `propagation.py` |
| `test_propagation_graph_native.py` | `*_by_node` helpers, `on_task_completed_by_node` |
| `test_propagation_reactivation.py` | CANCELLED managed subtask re-activation |
| `test_graph_repository.py` | `WorkflowGraphRepository` structural invariants |
| `test_graph_mutation_listener.py` | Listener callbacks on graph operations |
| `test_graph_toolkit.py` | `ResearchGraphToolkit` six tools with run-scoping |
| `test_delegation_scenario.py` | 8-step delegation scenario (add/cancel/replace/complete) |
| `test_manager_dag_scenario.py` | 15-step manager DAG (diamond, chain, leaf, cancel, restart) |
| `test_dep_failure_cascade.py` | Static vs dynamic dep-failure cascade |
| `test_conditional_status_writes.py` | `only_if_not_terminal` guard — race condition invariant |
| `test_restart_and_invalidation.py` | Restart + downstream invalidation cascade |
| `test_context_event_repository.py` | `ContextEventRepository` append + sequence counter |
| `test_context_assembly.py` | `assemble_pydantic_ai_messages` against DB rows |
| `test_context_rl_extraction.py` | RL trajectory extraction from `RunContextEvent` rows |
| `test_incremental_persistence.py` | `GenerationTurnRepository` turn persistence, listeners |
| `test_thread_execution_link.py` | `ThreadMessage.task_execution_id` FK + query |
| `test_workflow_finalization.py` | Score aggregation edge cases (None-scored evals) |
| `test_task_management_service.py` | `TaskManagementService` subtask lifecycle |
| `test_task_inspection_service.py` | `TaskInspectionService` read-only queries |
| `test_task_cleanup_service.py` | `TaskCleanupService` idempotent execution cancellation |
| `test_subtask_cancellation_service.py` | `SubtaskCancellationService` recursive cascade |
| `test_plan_subtasks.py` | Batch subtask creation + dependency validation |
| `test_prepare_dual_path.py` | `TaskExecutionService.prepare()` graph-native vs definition path |
| `test_rollout_batch_state.py` | `RolloutBatch`/`RolloutBatchRun` durable state across sessions |
| `test_run_resource_log.py` | Append-only `RunResource` log, schema + query semantics |
| `test_sandbox_resource_publisher.py` | `SandboxResourcePublisher` blob writes + dedup |
| `test_research_rubrics_toolkit.py` | `ResearchRubricsToolkit` + sandbox manager with DB |

**review** — single files that warrant individual review before placement:

| File | Notes |
|---|---|
| `test_research_rubrics_toolkit.py` | Uses fake `AsyncSandbox` stub + SQLite session; classify as graph |

**addendum (2026-04-21) — files added to `tests/state/` after initial RFC classification:**

Six files landed in `tests/state/` after this RFC was first drafted (via PRs #11, #13, #14, #15, and earlier). Classification below based on `session` fixture usage and factory imports:

| File | Classification | Rationale |
|---|---|---|
| `test_benchmark_contract.py` | **pure → unit** | Zero `session` fixture references; tests ABC contract shape |
| `test_criterion_runtime_di.py` | **pure → unit** | DI container construction assertions; no DB round-trip |
| `test_sandbox_event_sink_activation.py` | **pure → unit** | Process-level class setter activation check; uses `RecordingSandboxEventSink` fixture, no DB |
| `test_dashboard_emitter_wiring.py` | **graph → integration** | 13 `session: Session` references across 8 test classes; exercises emitter wiring through real services |
| `test_resource_content_api.py` | **graph → integration** | 17 session references; exercises REST API against DB |
| `test_legacy_wal_absent.py` | **graph → integration** | Uses `session` fixture to probe schema via `pg_tables` / `sqlite_master` — a sentinel test that belongs on the real Postgres tier post-reset |

Updated totals: **14 pure** (→ `tests/unit/`), **30 graph** (→ `tests/integration/`), 44 total files in `tests/state/`.

### 1.3 CI shape today

`ci-fast.yml` has three jobs:

- `lint-and-type-check` (timeout 5 min) — runs `ruff`, `ty`, `slopcop`, `xenon`.
- `frontend-checks` (timeout 5 min) — `eslint`, `tsc`.
- `unit-tests` (timeout 5 min) — `uv run pytest tests/state -v --cov … --cov-report=xml:coverage.xml` with `ERGON_DATABASE_URL=sqlite:///test.db`.
- `integration-tests` (timeout 10 min) — `uv run pytest tests/integration -v --timeout=120` with `ERGON_DATABASE_URL=sqlite:///test_integration.db`.

`tests/integration/` today (`test_full_lifecycle.py`, `test_full_lifecycle_with_eval.py`,
`test_researchrubrics_e2e.py`) also uses SQLite and calls services directly —
the same anti-pattern as `tests/state/`.

`package.json` scripts:

```json
"test:be:fast": "pnpm run test:be:state",
"test:be:state": "uv run pytest tests/state -q",
"test:be:integration": "uv run pytest tests/integration -v",
"test:be:all": "pnpm run test:be:state && pnpm run test:be:integration"
```

There is no `tests/unit/` directory. There is no PR path that runs tests
against real Postgres. `e2e-benchmarks.yml` triggers only on `feature/*`
or `workflow_dispatch`.

### 1.4 Related bug

`docs/bugs/open/2026-04-18-ci-docker-caching.md` — Docker layer caching is
not configured in `e2e-benchmarks.yml` or `docker-compose.ci.yml`. Once the
integration tier lands on the PR path (this RFC), every PR will pay a full
Docker rebuild. The fix (Buildx layer cache + `cache_from`/`cache_to` in
compose + pinned image digests) must land in the same PR as or before PR 2
of this RFC's implementation plan. **This RFC does not fix the bug** — it
names the dependency and blocks PR 2 on the bug being resolved first.

---

## 2. Proposal

Collapse `tests/state/` and the current `tests/integration/` into a single
real-infrastructure integration tier. Introduce a pure-logic `tests/unit/`
tier. Retire the SQLite-backed fast tier.

### 2.1 New tier taxonomy

| Tier | Location | Infra | CI trigger |
|---|---|---|---|
| Unit | `tests/unit/` | None — no I/O, no fixtures | Every PR (`ci-fast.yml`) |
| Integration | `tests/integration/` | Real Postgres 15 + real Inngest dev server (Docker) | Every PR (`ci-fast.yml`) |
| E2E | `tests/e2e/` | Full Docker stack + optional real E2B | `feature/*` + `workflow_dispatch` |

Tier boundaries remain path-based, not marker-based, as required by
`docs/architecture/07_testing.md §4`.

### 2.2 What moves where

1. The 11 **pure** `tests/state/` files move to `tests/unit/` with no
   behavior change. Their SQLite `session` fixture dependency is absent —
   any that accidentally import it will be caught at collection time.
2. The 27 **graph** `tests/state/` files are rewritten to use the new
   `tests/integration/conftest.py` Postgres + Inngest fixtures. Service
   calls that were direct now go through the Inngest event API
   (or are wrapped in the existing service interfaces with a real session).
3. The three existing `tests/integration/` files (`test_full_lifecycle.py`,
   `test_full_lifecycle_with_eval.py`, `test_researchrubrics_e2e.py`) are
   reviewed in the same pass — they follow the same direct-service-call
   pattern against SQLite and are rewritten or deleted accordingly.
4. `tests/state/` directory and its `conftest.py` / `factories.py` /
   `mocks.py` are deleted after migration is complete.

### 2.3 Integration tier Docker stack

The integration tier reuses the existing `docker-compose.ci.yml` stack
(Postgres 15, Inngest dev server, FastAPI app):

```yaml
# docker-compose.ci.yml (excerpt, not modified by this RFC)
postgres:
  image: postgres:15
  ports: ["5433:5432"]
  environment: {POSTGRES_USER: ergon, POSTGRES_PASSWORD: ci_test, POSTGRES_DB: ergon}

inngest-dev:
  image: inngest/inngest:latest
  command: inngest dev --no-discovery -u http://api:9000/api/inngest
  ports: ["8289:8288"]
```

The integration tests connect to this stack via the same environment
variables already used in `e2e-benchmarks.yml`:

```
ERGON_DATABASE_URL=postgresql://ergon:ci_test@localhost:5433/ergon
INNGEST_API_BASE_URL=http://localhost:8289
INNGEST_DEV=1
INNGEST_EVENT_KEY=dev
```

### 2.4 `@pytest.mark.slow` decision

The `slow` marker is already registered in `pyproject.toml`:

```toml
# pyproject.toml (line from [tool.pytest.ini_options])
markers = [
    "slow: marks tests as slow (deselect with '-m not slow')",
    ...
]
```

It is not used in any test today. Under this RFC it is available but not
mandated. Individual integration tests that take >30 s may be tagged
`@pytest.mark.slow`; the CI workflow runs all integration tests regardless.
The marker is for local developer ergonomics only (`pytest -m "not slow"`).

---

## 3. Architecture overview

### 3.1 Test-tier taxonomy

```
tests/
├── unit/                   ← NEW directory
│   ├── conftest.py         ← new; no fixtures needed today (placeholder)
│   └── test_*.py           ← pure: Pydantic, validators, pure functions
│
├── integration/            ← RENAMED scope (replaces state/ + old integration/)
│   ├── conftest.py         ← REPLACED: Postgres + Inngest fixtures
│   ├── smokes/             ← NEW subdirectory (companion RFC)
│   │   └── test_<slug>_smoke.py
│   └── test_*.py           ← graph/service: real Postgres, real Inngest
│
└── e2e/                    ← DELETED in PR 4; rebuilt under companion RFC
    ├── conftest.py         ← deleted
    └── test_*.py           ← deleted (full Docker + optional E2B tier to be
                              redesigned from scratch under companion RFC
                              `2026-04-21-e2e-smoke-coverage-rewrite.md`)
```

### 3.2 Decision rule for each tier

```
Pure function / validator / Pydantic model / registry key?
    yes → tests/unit/   (no I/O, no fixtures)
    no  → next

Exercises graph or persistence semantics?
    yes → tests/integration/   (real Postgres + real Inngest)
    no  → next

Needs sandbox / full E2B stack?
    yes → tests/e2e/   (Docker, feature-branch CI only)
```

### 3.3 What "integration" means post-reset

A test in `tests/integration/` must:
- Connect to real Postgres via `ERGON_DATABASE_URL`.
- Not use `create_engine("sqlite://", ...)`.
- Not call `SQLModel.metadata.create_all()` inline (schema is managed by
  the app startup or Alembic).
- Fire events via the Inngest HTTP API or call service methods that will
  eventually be called the same way by Inngest.
- Assert state via `RunGraphNode.status` and `RunGraphMutation` rows —
  never via direct DB writes.

---

## 4. Type / interface definitions

### 4.1 `tests/unit/conftest.py`

Placeholder — no shared fixtures needed today. The file must exist to
make `tests/unit/` a pytest-discoverable package.

```python
# tests/unit/conftest.py
"""Shared fixtures for unit tests.

Unit tests have no I/O; this file is a placeholder so pytest
discovers tests/unit/ as a package. Do not add I/O fixtures here.
"""
```

### 4.2 `tests/integration/conftest.py` (replacement)

Replaces the current `tests/integration/conftest.py` (which has no fixtures
of its own — only `__pycache__/` and test files). The new version provides
the Postgres session fixture and an Inngest event helper used by all
integration tests.

```python
# tests/integration/conftest.py
"""Shared fixtures for integration tests.

Requires a live Docker stack (postgres + inngest-dev + api).
Set ERGON_DATABASE_URL=postgresql://ergon:ci_test@localhost:5433/ergon
and INNGEST_API_BASE_URL=http://localhost:8289 before running.

Skips automatically when ERGON_DATABASE_URL is absent or points
at SQLite, so unit-test-only runs are unaffected.
"""

from __future__ import annotations

import os

import pytest
from ergon_core.core.persistence.shared.db import get_engine
from sqlmodel import Session, text


@pytest.fixture(scope="session", autouse=True)
def _require_postgres() -> None:
    url = os.environ.get("ERGON_DATABASE_URL", "")
    if not url or url.startswith("sqlite"):
        pytest.skip(
            "Integration tests require ERGON_DATABASE_URL pointing at a "
            "live Postgres instance. Run with docker-compose.ci.yml."
        )


@pytest.fixture(scope="session")
def pg_engine():
    """SQLAlchemy engine connected to the test Postgres instance."""
    return get_engine()


@pytest.fixture
def pg_session(pg_engine):
    """Session with per-test rollback against real Postgres.

    Uses SAVEPOINT so the outer transaction can be rolled back cleanly
    even if the code under test calls session.commit().
    """
    connection = pg_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    nested = connection.begin_nested()

    yield session

    session.close()
    if nested.is_active:
        nested.rollback()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="session")
def inngest_base_url() -> str:
    """Base URL for the Inngest dev server."""
    return os.environ.get("INNGEST_API_BASE_URL", "http://localhost:8289")
```

### 4.3 `tests/integration/factories.py`

The Postgres-compatible equivalent of `tests/state/factories.py`. The
factory helpers construct the same topology shapes (flat, chain, diamond)
but commit within the provided session so the new `pg_session` fixture can
roll them back. No new models introduced.

```python
# tests/integration/factories.py
"""Topology builders for integration tests.

Same shapes as tests/state/factories.py, but targeting real Postgres
via the pg_session fixture.
"""

from uuid import UUID, uuid4

from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskDependency,
)
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from sqlmodel import Session


def seed_flat_tasks(
    session: Session,
    n: int = 3,
) -> tuple[UUID, UUID, list[UUID]]:
    """n independent tasks, no dependencies. Returns (def_id, inst_id, task_ids)."""
    def_id = uuid4()
    inst_id = uuid4()
    session.add(ExperimentDefinition(id=def_id, benchmark_type="test"))
    session.add(
        ExperimentDefinitionInstance(
            id=inst_id, experiment_definition_id=def_id, instance_key="inst-0"
        )
    )
    task_ids: list[UUID] = []
    for i in range(n):
        tid = uuid4()
        session.add(
            ExperimentDefinitionTask(
                id=tid,
                experiment_definition_id=def_id,
                task_key=f"task-{i}",
                worker_binding_key="stub",
            )
        )
        task_ids.append(tid)
    session.flush()
    return def_id, inst_id, task_ids


def seed_run(session: Session, def_id: UUID) -> UUID:
    run_id = uuid4()
    session.add(
        RunRecord(
            id=run_id,
            experiment_definition_id=def_id,
            status=RunStatus.RUNNING,
        )
    )
    session.flush()
    return run_id


def seed_chain(
    session: Session,
    length: int = 3,
) -> tuple[UUID, UUID, list[UUID]]:
    """Linear chain: task[0] → task[1] → … → task[length-1]."""
    def_id, inst_id, task_ids = seed_flat_tasks(session, length)
    for i in range(length - 1):
        session.add(
            ExperimentDefinitionTaskDependency(
                task_id=task_ids[i + 1],
                depends_on_task_id=task_ids[i],
            )
        )
    session.flush()
    return def_id, inst_id, task_ids


def seed_diamond(
    session: Session,
) -> tuple[UUID, UUID, list[UUID]]:
    """Diamond: A → B, A → C, B → D, C → D."""
    def_id, inst_id, task_ids = seed_flat_tasks(session, 4)
    a, b, c, d = task_ids
    for dep in [(b, a), (c, a), (d, b), (d, c)]:
        session.add(
            ExperimentDefinitionTaskDependency(
                task_id=dep[0], depends_on_task_id=dep[1]
            )
        )
    session.flush()
    return def_id, inst_id, task_ids
```

---

## 5. Full implementations

### 5.1 `tests/unit/conftest.py`

Complete file shown in §4.1.

### 5.2 `tests/integration/conftest.py`

Complete file shown in §4.2.

### 5.3 `tests/integration/factories.py`

Complete file shown in §4.3.

### 5.4 Pattern for rewritten graph tests

Each `tests/state/test_<name>.py` that is classified **graph** must be
rewritten to use `pg_session` instead of `session`, and `seed_*` from
`tests.integration.factories` instead of `tests.state.factories`.
The assertion logic is unchanged — tests still assert `RunGraphNode.status`
and `RunGraphMutation` rows. The infrastructure under them is real.

Example rewrite of the import + fixture pattern:

```python
# Before (tests/state/test_propagation.py header):
from tests.state.factories import seed_chain, seed_diamond, seed_flat_tasks, seed_run
# session: Session  (from state/conftest.py — SQLite, per-test rollback)

# After (tests/integration/test_propagation.py header):
from tests.integration.factories import seed_chain, seed_diamond, seed_flat_tasks, seed_run
# pg_session: Session  (from integration/conftest.py — Postgres, per-test SAVEPOINT rollback)
```

No other changes to test logic are required for the pure-repository and
propagation tests. Tests that previously mocked `get_session()` or patched
`engine` must be updated to use the `pg_session` fixture directly.

---

## 6. Exact diffs for modified files

### 6.1 `pyproject.toml` — add `tests/unit` to testpaths, remove `state` from coverage

```diff
 [tool.pytest.ini_options]
 asyncio_mode = "auto"
-testpaths = ["tests"]
+testpaths = ["tests/unit", "tests/integration", "tests/e2e"]
 timeout = 600
 markers = [
     "slow: marks tests as slow (deselect with '-m not slow')",
     "e2e: end-to-end tests requiring full Docker stack",
     "integration: integration tests requiring a database but no Docker stack",
 ]
```

### 6.2 `package.json` — retire `test:be:state`, add `test:be:unit`, redefine `test:be:fast`

```diff
-    "test:be:state": "uv run pytest tests/state -q",
-    "test:be:coverage": "uv run pytest tests/state tests/integration --cov=ergon_core --cov=ergon_builtins --cov-report=term-missing --cov-report=xml:coverage.xml",
-    "test:be:integration": "uv run pytest tests/integration -v",
-    "test:be:all": "pnpm run test:be:state && pnpm run test:be:integration",
+    "test:be:unit": "uv run pytest tests/unit -q",
+    "test:be:coverage": "uv run pytest tests/unit tests/integration --cov=ergon_core --cov=ergon_builtins --cov-report=term-missing --cov-report=xml:coverage.xml",
+    "test:be:integration": "uv run pytest tests/integration -v",
+    "test:be:all": "pnpm run test:be:unit && pnpm run test:be:integration",
     "test:be:e2e": "uv run pytest tests/e2e -v",
-    "test:be:fast": "pnpm run test:be:state"
+    "test:be:fast": "pnpm run test:be:unit"
```

### 6.3 `.github/workflows/ci-fast.yml` — replace `unit-tests` job, add Docker to `integration-tests`

```diff
   unit-tests:
-    name: "Unit + state tests (Python)"
+    name: "Unit tests (Python)"
     runs-on: ubuntu-latest
     timeout-minutes: 5
     needs: lint-and-type-check
     steps:
       - uses: actions/checkout@v4
       - uses: astral-sh/setup-uv@v4
         with:
           python-version: "3.13"
       - name: Install project
         run: uv sync --frozen --all-packages --group dev
-      - name: Run fast test suites with coverage
-        env:
-          ERGON_DATABASE_URL: "sqlite:///test.db"
-        run: uv run pytest tests/state -v --cov=ergon_core --cov=ergon_builtins --cov-report=xml:coverage.xml
+      - name: Run unit tests
+        run: uv run pytest tests/unit -v --cov=ergon_core --cov=ergon_builtins --cov-report=xml:coverage.xml
       - name: Upload coverage report
         uses: actions/upload-artifact@v4
         with:
           name: coverage-report
           path: coverage.xml

   integration-tests:
     name: "Integration tests (Python)"
     runs-on: ubuntu-latest
-    timeout-minutes: 10
+    timeout-minutes: 20
     needs: lint-and-type-check
     steps:
       - uses: actions/checkout@v4
+
+      - name: Start CI stack
+        run: docker compose -f docker-compose.ci.yml up -d --build --wait
+        timeout-minutes: 10
+
+      - name: Wait for Inngest sync
+        run: |
+          for i in $(seq 1 30); do
+            curl -sf http://localhost:8289/v1/events/test > /dev/null 2>&1 && break
+            sleep 2
+          done
+          sleep 5
+
       - uses: astral-sh/setup-uv@v4
         with:
           python-version: "3.13"
       - name: Install project
         run: uv sync --frozen --all-packages --group dev
+
       - name: Run integration tests
         env:
-          ERGON_DATABASE_URL: "sqlite:///test_integration.db"
-        run: uv run pytest tests/integration -v --timeout=120
+          ERGON_DATABASE_URL: postgresql://ergon:ci_test@localhost:5433/ergon
+          INNGEST_API_BASE_URL: http://localhost:8289
+          INNGEST_DEV: "1"
+          INNGEST_EVENT_KEY: dev
+        run: uv run pytest tests/integration -v --timeout=300
+
+      - name: Dump API logs on failure
+        if: failure()
+        run: docker compose -f docker-compose.ci.yml logs api --tail 100
+
+      - name: Teardown
+        if: always()
+        run: docker compose -f docker-compose.ci.yml down -v
```

**Dependency:** The `integration-tests` job change (adding Docker to the PR
path) must not land until `docs/bugs/open/2026-04-18-ci-docker-caching.md`
is fixed. Without Docker layer caching, every PR would pay a full image
rebuild (~3–5 min), making the 20 min timeout likely to be breached.
This is the hard sequencing constraint between PR 2 and the caching bug fix.

---

## 7. Package structure

### 7.1 `tests/unit/__init__.py`

Does not need to exist — pytest discovers packages by `testpaths`, not
by `__init__.py`. No `__init__.py` needed for `tests/unit/`.

### 7.2 Deletion: `tests/state/`

The entire `tests/state/` directory is deleted at the end of the migration
(PR 3 or PR 4 depending on sequencing). No replacement package needed —
the content is distributed to `tests/unit/` and `tests/integration/`.

### 7.3 Preservation: `tests/state/factories.py` logic

`tests/state/factories.py` contains `seed_flat_tasks`, `seed_run`,
`seed_chain`, `seed_diamond`. These functions are reproduced in
`tests/integration/factories.py` (§4.3). The state versions are deleted
with `tests/state/`.

---

## 8. Implementation order

Phased into four PRs. Each PR must leave CI green before the next lands.
"CI green" means all jobs in `ci-fast.yml` pass.

### PR 1 — Unit tier scaffold + pure test migration (no CI change)

| Step | What | Files touched |
|---|---|---|
| 1 | Create `tests/unit/` directory | ADD `tests/unit/conftest.py` |
| 2 | Move 11 **pure** files from `tests/state/` to `tests/unit/` | MOVE 11 files (see §1.2 "pure" table) |
| 3 | Update imports in moved files: `from tests.state.factories` → remove (pure tests don't use factories) | MODIFY moved files that import `factories` (verify none do) |
| 4 | Update `pyproject.toml` testpaths to include `tests/unit` | MODIFY `pyproject.toml` |
| 5 | Update `ci-fast.yml` unit-tests job: replace `tests/state` run with `tests/unit` run (no Docker yet) | MODIFY `.github/workflows/ci-fast.yml` |
| 6 | Update `package.json`: add `test:be:unit`, redefine `test:be:fast` | MODIFY `package.json` |
| 7 | Verify `tests/state` still runs in `test:be:state` (not removed yet — keeps CI green during transition) | no change |

**PR 1 acceptance gate:** `pnpm run test:be:unit` passes. `pnpm run test:be:state` still passes. `ci-fast.yml` unit-tests job runs `tests/unit/`.

### PR 2 — Docker caching bug fix (prerequisite for PR 3)

| Step | What | Files touched |
|---|---|---|
| 1 | Fix `docs/bugs/open/2026-04-18-ci-docker-caching.md` | MODIFY `.github/workflows/e2e-benchmarks.yml`, `docker-compose.ci.yml` |
| 2 | Add Buildx cache to `ci-fast.yml` `integration-tests` job (cache step only, still uses SQLite) | MODIFY `.github/workflows/ci-fast.yml` |

**PR 2 acceptance gate:** `e2e-benchmarks.yml` wall-clock drops measurably on repeat runs. Before/after measurement required in PR description.

### PR 3 — Integration tier rewrite (real Postgres + Inngest)

| Step | What | Files touched |
|---|---|---|
| 1 | Replace `tests/integration/conftest.py` with Postgres + Inngest fixture version | MODIFY `tests/integration/conftest.py` |
| 2 | Add `tests/integration/factories.py` | ADD `tests/integration/factories.py` |
| 3 | Rewrite the 3 existing integration files (`test_full_lifecycle.py`, `test_full_lifecycle_with_eval.py`, `test_researchrubrics_e2e.py`) against real Postgres | MODIFY 3 files |
| 4 | Move + rewrite 27 **graph** files from `tests/state/` to `tests/integration/` | MOVE+MODIFY 27 files |
| 5 | Update `ci-fast.yml` `integration-tests` job: add Docker compose startup, switch env vars to Postgres | MODIFY `.github/workflows/ci-fast.yml` |
| 6 | Raise `integration-tests` timeout to 20 min | MODIFY `.github/workflows/ci-fast.yml` |
| 7 | Update `package.json` coverage script to cover `tests/unit tests/integration` | MODIFY `package.json` |

**PR 3 acceptance gate:** All 27 rewritten tests pass against Postgres in CI. `integration-tests` job is green. `tests/state/` still exists (delete in PR 4).

### PR 4 — Tombstone `tests/state/` + `tests/e2e/`, update architecture docs

| Step | What | Files touched |
|---|---|---|
| 1 | Delete `tests/state/` | DELETE `tests/state/` (entire directory) |
| 2 | Delete `tests/e2e/` for a clean slate — retired tier is rebuilt from scratch under companion RFC `2026-04-21-e2e-smoke-coverage-rewrite.md` | DELETE `tests/e2e/` (entire directory) |
| 3 | Remove `test:be:state`, `test:be:e2e`, and `test:be:all` state references from `package.json` | MODIFY `package.json` |
| 4 | Remove `tests/e2e/` from `pyproject.toml` `testpaths` and `ci-fast.yml` / `e2e-benchmarks.yml`; deactivate `e2e-benchmarks.yml` (keep file, gate with `if: false` or a workflow-disabled sentinel until the companion RFC restores it) | MODIFY `pyproject.toml`, `.github/workflows/ci-fast.yml`, `.github/workflows/e2e-benchmarks.yml` |
| 5 | Update `pyproject.toml` testpaths: remove any implicit `tests` catch-all | MODIFY `pyproject.toml` |
| 6 | Update `docs/architecture/07_testing.md`: remove "under development" hedges, state new invariants as current, remove fast-tier invariant, note that e2e tier is temporarily absent pending companion RFC, update code map | MODIFY `docs/architecture/07_testing.md` |
| 7 | Mark related bugs as fixed if resolved in parallel | MODIFY relevant bug files |

**PR 4 acceptance gate:** `tests/state/` and `tests/e2e/` do not exist. `ci-fast.yml` all jobs green. `test:be:fast` runs `tests/unit/` only. `e2e-benchmarks.yml` is dormant (does not schedule or run) until the companion e2e-rewrite RFC lands.

**Coverage-gap note:** Between PR 4 landing and the companion e2e-rewrite RFC's first PR landing, main has **zero end-to-end coverage** for the CLI → Inngest → sandbox pipeline. This is an intentional clean-slate tradeoff chosen over gradual displacement. Integration tier (real Postgres + real Inngest) catches most regressions in this window; CLI-surface regressions will not be caught until the companion RFC lands its first smoke.

---

## 9. File map

### ADD

| File | Purpose |
|---|---|
| `tests/unit/conftest.py` | Placeholder conftest for unit tier; no fixtures |
| `tests/integration/factories.py` | Postgres-compatible topology builders (flat, chain, diamond, run) |

### MOVE (pure → unit, no content change)

| From | To |
|---|---|
| `tests/state/test_type_invariants.py` | `tests/unit/test_type_invariants.py` |
| `tests/state/test_env_writer.py` | `tests/unit/test_env_writer.py` |
| `tests/state/test_event_schema_phase0.py` | `tests/unit/test_event_schema_phase0.py` |
| `tests/state/test_generation_turn_build.py` | `tests/unit/test_generation_turn_build.py` |
| `tests/state/test_llm_judge_runtime_injection.py` | `tests/unit/test_llm_judge_runtime_injection.py` |
| `tests/state/test_onboard_profile.py` | `tests/unit/test_onboard_profile.py` |
| `tests/state/test_onboard_wizard.py` | `tests/unit/test_onboard_wizard.py` |
| `tests/state/test_research_rubrics_benchmark.py` | `tests/unit/test_research_rubrics_benchmark.py` |
| `tests/state/test_research_rubrics_workers.py` | `tests/unit/test_research_rubrics_workers.py` |
| `tests/state/test_subtask_lifecycle_toolkit.py` | `tests/unit/test_subtask_lifecycle_toolkit.py` |
| `tests/state/test_criteria_do_not_spawn_sandboxes.py` | `tests/unit/test_criteria_do_not_spawn_sandboxes.py` |

### MOVE + REWRITE (graph → integration, fixtures updated)

| From | To |
|---|---|
| `tests/state/test_propagation.py` | `tests/integration/test_propagation.py` |
| `tests/state/test_propagation_graph_native.py` | `tests/integration/test_propagation_graph_native.py` |
| `tests/state/test_propagation_reactivation.py` | `tests/integration/test_propagation_reactivation.py` |
| `tests/state/test_graph_repository.py` | `tests/integration/test_graph_repository.py` |
| `tests/state/test_graph_mutation_listener.py` | `tests/integration/test_graph_mutation_listener.py` |
| `tests/state/test_graph_toolkit.py` | `tests/integration/test_graph_toolkit.py` |
| `tests/state/test_delegation_scenario.py` | `tests/integration/test_delegation_scenario.py` |
| `tests/state/test_manager_dag_scenario.py` | `tests/integration/test_manager_dag_scenario.py` |
| `tests/state/test_dep_failure_cascade.py` | `tests/integration/test_dep_failure_cascade.py` |
| `tests/state/test_conditional_status_writes.py` | `tests/integration/test_conditional_status_writes.py` |
| `tests/state/test_restart_and_invalidation.py` | `tests/integration/test_restart_and_invalidation.py` |
| `tests/state/test_context_event_repository.py` | `tests/integration/test_context_event_repository.py` |
| `tests/state/test_context_assembly.py` | `tests/integration/test_context_assembly.py` |
| `tests/state/test_context_rl_extraction.py` | `tests/integration/test_context_rl_extraction.py` |
| `tests/state/test_incremental_persistence.py` | `tests/integration/test_incremental_persistence.py` |
| `tests/state/test_thread_execution_link.py` | `tests/integration/test_thread_execution_link.py` |
| `tests/state/test_workflow_finalization.py` | `tests/integration/test_workflow_finalization.py` |
| `tests/state/test_task_management_service.py` | `tests/integration/test_task_management_service.py` |
| `tests/state/test_task_inspection_service.py` | `tests/integration/test_task_inspection_service.py` |
| `tests/state/test_task_cleanup_service.py` | `tests/integration/test_task_cleanup_service.py` |
| `tests/state/test_subtask_cancellation_service.py` | `tests/integration/test_subtask_cancellation_service.py` |
| `tests/state/test_plan_subtasks.py` | `tests/integration/test_plan_subtasks.py` |
| `tests/state/test_prepare_dual_path.py` | `tests/integration/test_prepare_dual_path.py` |
| `tests/state/test_rollout_batch_state.py` | `tests/integration/test_rollout_batch_state.py` |
| `tests/state/test_run_resource_log.py` | `tests/integration/test_run_resource_log.py` |
| `tests/state/test_sandbox_resource_publisher.py` | `tests/integration/test_sandbox_resource_publisher.py` |
| `tests/state/test_research_rubrics_toolkit.py` | `tests/integration/test_research_rubrics_toolkit.py` |

### MODIFY

| File | Changes |
|---|---|
| `pyproject.toml` | `testpaths`: replace `["tests"]` with explicit tier paths; see §6.1 |
| `package.json` | Add `test:be:unit`; redefine `test:be:fast` = unit only; update coverage targets; see §6.2 |
| `.github/workflows/ci-fast.yml` | Unit-tests job runs `tests/unit/`; integration-tests job adds Docker compose stack + Postgres env vars + extended timeout; see §6.3 |
| `tests/integration/conftest.py` | Replace empty file with Postgres + Inngest fixtures; see §4.2 |
| `tests/integration/test_full_lifecycle.py` | Rewrite to use `pg_session` and real Inngest |
| `tests/integration/test_full_lifecycle_with_eval.py` | Rewrite to use `pg_session` and real Inngest |
| `tests/integration/test_researchrubrics_e2e.py` | Rewrite to use `pg_session` and real Inngest |

### DELETE (PR 4)

| File/Directory | Reason |
|---|---|
| `tests/state/` (entire directory) | Replaced by `tests/unit/` + `tests/integration/` |
| `tests/e2e/` (entire directory) | Retired for clean-slate rebuild under companion RFC `2026-04-21-e2e-smoke-coverage-rewrite.md`. `e2e-benchmarks.yml` is disabled (not deleted) in the same PR so the companion RFC can restore it without re-creating the workflow file. |

---

## 10. Testing approach

### 10.1 How the reset itself is verified

The posture reset is structural, not behavioral — it is verified by the
test suite continuing to pass under the new infrastructure, not by new
tests.

Specific checkpoints:

1. **PR 1:** `pnpm run test:be:unit` passes. All 11 moved files collect and pass. No
   regressions in moved pure tests (they have no changed logic).

2. **PR 3:** All 27 rewritten graph tests pass against real Postgres in CI.
   If a test fails under Postgres that passed under SQLite, that is a
   pre-existing bug being surfaced — it must be fixed in the same PR or
   promoted to a bug report and the test `xfail`'d with a reference.

3. **PR 4:** After `tests/state/` is deleted, `pytest tests/state` produces
   "no tests ran" (or a collection error — either is acceptable). No
   existing test path regresses.

### 10.2 Coverage continuity

Coverage is currently measured over `tests/state/` only. After the reset:

- `test:be:coverage` runs over `tests/unit tests/integration`.
- No coverage threshold is enforced (see `docs/architecture/07_testing.md §7`).
- The coverage artifact uploaded to CI is updated in PR 1 to include `tests/unit/`.

### 10.3 Postgres-specific invariants exposed by rewrite

The following `tests/state/` test classes are likely to surface real bugs
when run against Postgres, because SQLite silently allows behaviors that
Postgres rejects:

- `test_conditional_status_writes.py` — `only_if_not_terminal` guard uses
  a conditional update; behavior under concurrent Postgres connections may
  differ from SQLite's single-writer model.
- `test_rollout_batch_state.py` — mentions "durable rollout batch state in
  PG" in its docstring; the SQLite run was arguably always wrong for this
  test.
- `test_sandbox_resource_publisher.py` — blob dedup via DB uniqueness
  constraint; SQLite vs Postgres constraint error types differ.

Any failures in these tests during PR 3 are expected and must be resolved
before PR 3 merges.

---

## 11. Trace / observability impact

Minimal. No production code changes. The only observability impact is:

- Coverage XML artifacts (`coverage.xml`) produced by the CI `unit-tests`
  job change scope from `tests/state/` to `tests/unit/`. The artifact name
  is unchanged (`coverage-report`).
- Span attributes in `worker_execute_fn` are unchanged.
- No new metrics, logs, or traces are introduced.

---

## 12. Risks and mitigations

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Rewritten graph tests fail against Postgres due to SQLite-masked bugs | PR 3 blocked; discovered bugs require fixes | Medium | Surface is expected. Treat each failure as a bug found, not a regression introduced. Fix or `xfail` with reference. |
| Docker rebuild cost makes integration-tests CI job exceed 20 min timeout | PRs blocked | High if caching not fixed first | Hard sequencing: PR 3 must not land before PR 2 (caching bug fix). |
| `pg_session` SAVEPOINT rollback doesn't work for all service calls | Per-test isolation breaks; tests pollute each other | Low | SAVEPOINT rollback is the standard pattern for Postgres test isolation. Already used in `tests/e2e/conftest.py` session fixture. |
| Test collection failures when `tests/state/` imports appear in `tests/unit/` | Unit tests fail to collect | Low | Pure files don't import `tests.state.factories`. Verified by inspection during §1.2 classification. |
| Dropping coverage from 37 state tests + 3 integration → 11 unit tests temporarily (between PR 1 and PR 3) | Reduced coverage signal | Medium | Acceptable for the duration of the transition. PR 3 restores full coverage across all 38 integration tests. |
| `test_criteria_do_not_spawn_sandboxes.py` xfail status changes under move | If criterion DI RFC lands before this RFC, test passes and xfail is now a failure | Low | Check xfail status at migration time; remove `xfail` if the criterion-runtime-di RFC has landed. |
| Inngest event delivery ordering is non-deterministic | Graph-state assertions flaky if tests poll too fast | Medium | Integration tests must use explicit waits or `pytest-timeout`-guarded polling. Existing `tests/e2e/` pattern (Inngest sync wait) is the model. |
| `tests/state/mocks.py` has shared mock objects referenced by graph files | Moves to `tests/integration/` required | Low | Audit during PR 3: move `mocks.py` to `tests/integration/mocks.py` if any rewritten file imports it. |

---

## 13. Invariants affected

References to `docs/architecture/07_testing.md`:

- **§4 fast-tier invariant** — "The fast tier must stay fast enough to be the
  'ready for review' gate. If it needs Docker, Postgres, or an Inngest
  runtime, it does not belong in the fast tier." — **this invariant is
  replaced.** Post-reset, the "ready for review" gate includes integration
  tests that DO need Docker and Postgres. The invariant becomes: the PR
  gate runs in under 20 minutes wall-clock; Docker caching makes this
  feasible.

- **§4 "tier boundaries are filesystem paths"** — preserved unchanged.

- **§4 "state tests assert against service-class return values … never
  direct DB writes"** — superseded by the deletion of the state tier. The
  surviving invariant is: integration tests assert via `RunGraphNode.status`
  and `RunGraphMutation` rows, never via direct DB writes. Applies to both
  `tests/integration/` and `tests/e2e/`.

- **§6 "fast-tier state tests that skip Inngest when production does not"**
  anti-pattern — **this anti-pattern is closed** by the reset.

- **§7 "per-benchmark smoke pattern"** — companion RFC
  `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md` introduces
  `tests/integration/smokes/`. That RFC must land after this one
  establishes the real-infrastructure integration tier; the smokes depend on
  `tests/integration/conftest.py` providing the Postgres + Inngest fixtures.

- **§7 "test-harness endpoints"** — companion RFC
  `docs/rfcs/active/2026-04-18-test-harness-endpoints.md`. Depends on
  this RFC for the Docker-on-every-PR setup.

---

## 14. Alternatives considered

- **Keep the current state/integration split.** Rejected. The divergence
  between the test setup and the production setup is precisely the bug
  this RFC is trying to close. Keeping the split preserves a false signal.

- **Hybrid: SQLite for some tests, Postgres for others.** Rejected. Two
  patterns, two sets of fixture helpers, two mental models for when each
  applies. Ongoing dual-maintenance cost with no clean boundary.

- **Leave `tests/state/` in place and add a new integration tier on top.**
  Rejected. Adds surface without removing the broken signal. The 37 state
  files would continue to claim green on code paths that don't match
  production, and any reviewer seeing a test pass would still have to ask
  which tier produced the signal.

- **Keep `tests/state/` but replace SQLite with Postgres in conftest.**
  Rejected. This changes the infrastructure without changing the anti-pattern
  of bypassing Inngest. Tests would still call service classes directly,
  skipping the event-driven path that production uses. The directory name
  would be misleading ("state" tests running against Postgres + Inngest is
  an oxymoron). Renaming is the cheaper path anyway once all tests are
  reclassified.

- **Add `@pytest.mark.integration` to all graph tests and keep them in
  `tests/state/`**. Rejected. Architecture doc §4 states tier boundaries
  are paths, not markers. Keeping graph tests in `tests/state/` with a
  marker violates that invariant and leaves the misleading directory name
  in place.

---

## 15. Open questions

- Do we add a `@pytest.mark.slow` marker so developers can opt into a fast
  local dev loop that skips integration tests on each save? The marker is
  already registered but unused. Decision deferred: any test author who
  wants it can add it to their test; the CI workflow ignores it.

- What is the acceptable CI wall-clock budget for a PR? 5 minutes was the
  fast-tier target. Post-reset: 20 minutes is the proposed timeout for the
  integration-tests job. Adjust based on actual measurements from the first
  run of PR 3.

- Do we parallelize integration tests by spinning up one Postgres + Inngest
  stack per worker, or share a single stack across workers with schema
  namespacing? Current answer: single shared stack, per-test SAVEPOINT
  rollback for isolation. Schema namespacing is left for a future RFC if
  parallelism becomes a bottleneck.

- `tests/state/mocks.py` — does any rewritten file import it? Audit
  required at PR 3 time. If so, copy to `tests/integration/mocks.py`.

---

## 16. On acceptance

When this RFC moves from `active/` to `accepted/`, also:
  - Update `docs/architecture/07_testing.md` to remove the "target posture —
    not yet executed" framing and state the new invariants as current.
    Remove the fast-tier invariant. Update the code map table (§2) to show
    `tests/unit/` and the new `tests/integration/` scope.
  - Update `docs/architecture/07_testing.md §6` anti-patterns: remove the
    "fast-tier state tests that skip Inngest" entry (closed).
  - Close `docs/bugs/open/2026-04-18-ci-docker-caching.md` if it was fixed
    as part of PR 2 of this plan.
  - Link the audit + rewrite tracking in
    `docs/superpowers/plans/2026-04-??-testing-posture-reset.md`.
