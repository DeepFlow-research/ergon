# Finish Built-ins, CLI, And E2E Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the Ergon built-ins, CLI, and e2e refactor after the core public API and test-support facade have stabilized, while avoiding private core internals that may continue moving.

**Architecture:** Treat `ergon_core.api`, core service/facade DTOs, `ergon_core.test_support`, HTTP `/api/test/*`, and application read models as the stable boundary. Production built-ins own benchmark-specific workers/rubrics/sandboxes; CLI commands validate explicit slugs and call core facades; e2e tests assert black-box runtime behavior and use test-support constants rather than private repository methods.

**Tech Stack:** Python, pytest, FastAPI test harness endpoints, Playwright, Inngest, E2B, `ergon_core.test_support`, `ergon_builtins.registry`, `ergon_cli`.

---

## Current Working Assumptions

- Core runtime behavior is stable: the canonical smoke topology, resource counts, task states, communication threads, and evaluation outcomes are still expected to match existing e2e assertions.
- Core internal layout has changed substantially. Tests should not import private repository modules or persistence models unless there is no stable public/test-support read helper yet.
- `ergon_core.test_support` is stable and may be imported by unit/integration/e2e host-side test code.
- The API process, not the host e2e process, should register smoke fixtures via startup plugin/environment.
- Built-ins and CLI work may proceed as long as it stays on public API/service boundaries and avoids core repository implementation files.

## E2E Behavior That Should Remain True

These expected values are derived from stable smoke fixture constants and should remain hard assertions unless `ergon_core.test_support.smoke_fixtures` changes intentionally.

```text
Happy path:
- 12 total tasks: 1 root + 9 direct subtasks + 2 nested subtasks
- 10 leaf tasks
- direct level-1 slugs match EXPECTED_SUBTASK_SLUGS
- nested level-2 slugs match NESTED_LINE_SLUGS
- l_2 is non-leaf; l_2_a and l_2_b are children of l_2
- all nodes complete
- 20 task artifact resources: 10 benchmark artifacts + 10 probe_*.json
- no worker_output resources; final assistant messages stay on executions
- 26 context events: parent 3 + recursive 3 + 10 leaves x 2
- 2 root evaluations, both score 1.0, created after root execution completion
- final score is 1.0
- one smoke-completion thread with 11 ordered messages

Sad path:
- l_2 fails
- l_3 is blocked, never starts, and has no execution attempts
- root does not complete
- independent leaves complete
- exactly one partial_*.md artifact persists from l_2
- at least one pre-failure partial wc WAL/probe entry exists
- smoke-completion thread has 7 messages
- l_2 and l_3 do not send completion messages
- final score is None or 0.0
```

Benchmark-specific artifact assertions should also remain:

```text
MiniF2F:
- 10 proof_*.lean resources
- each proof contains "theorem smoke_trivial" and ":="

SWE-Bench:
- 10 patch_*.py resources
- each patch parses as Python and defines add()

ResearchRubrics:
- report/probe artifacts and dashboard-visible resource panels match the shared smoke assertions
```

## File Responsibility Map

Built-ins:

- `ergon_builtins/ergon_builtins/registry.py`: merged public registry surface.
- `ergon_builtins/ergon_builtins/registry_core.py`: always-importable benchmarks/workers/evaluators/sandboxes/model backends.
- `ergon_builtins/ergon_builtins/registry_data.py`: `[data]` benchmark registrations.
- `ergon_builtins/ergon_builtins/benchmarks/*/worker_factory.py`: benchmark-owned worker factories or benchmark-owned re-export surfaces.
- `ergon_builtins/ergon_builtins/shared/`: generic worker, criteria, model, prompt import surfaces.

CLI:

- `ergon_cli/ergon_cli/main.py`: parser contract only.
- `ergon_cli/ergon_cli/commands/experiment.py`: thin command handler for `experiment define/run/show/list`.
- `ergon_cli/ergon_cli/commands/benchmark.py`: `list`, `setup`, and `run` wrapper behavior.
- `ergon_cli/ergon_cli/discovery/__init__.py`: registry list helpers.
- Future target: `ergon_cli/ergon_cli/services/*_facade.py` if command handlers remain too stateful.

E2E:

- `tests/e2e/_submit.py`: black-box cohort submission client for `/api/test/write/cohort`.
- `tests/e2e/_read_contracts.py`: stable read-model wrapper for run snapshots.
- `tests/e2e/_asserts.py`: behavior assertions; should import test-support constants and stable read helpers.
- `tests/e2e/test_{researchrubrics,minif2f,swebench}_smoke.py`: per-benchmark e2e drivers.
- `ergon-dashboard/tests/e2e/*.smoke.spec.ts`: dashboard assertions.

Stable core/test-support surfaces:

- `ergon_core.api`
- `ergon_core.test_support`
- `ergon_core.core.application.read_models.*`, if accepted as the application-level read facade
- `/api/test/*` HTTP endpoints

Private core surfaces to avoid in new e2e code:

- `ergon_core.core.persistence.*` models and queries
- `ergon_core.core.runtime.tasks.repository`
- `ergon_core.core.runtime.evaluation.persistence`
- Inngest child payload modules
- repository method names or table-specific access patterns

## Task 1: Freeze And Document The Stable E2E Boundary

**Files:**
- Modify: `docs/superpowers/plans/2026-04-28-ergon-e2e-refactor-test-plan.md`
- Test: `tests/unit/architecture/test_public_api_boundaries.py`

- [ ] **Step 1: Add a “stable e2e boundary” section to the e2e plan**

Add this section near the existing `Fixture Residency Rules` section:

```markdown
## Stable E2E Boundary After Core Layout Refactor

Core behavior is stable, but private repository and persistence modules may move.
E2E code should use only:

- HTTP endpoints under `/api/test/*`
- `ergon_core.test_support`
- public core API objects from `ergon_core.api`
- application read-model facades, not private repository methods

The existing smoke behavior assertions remain valid:

- happy runs complete the 12-node graph
- sad runs fail `l_2` and block `l_3`
- happy runs produce 20 task resources and 26 context events
- happy root produces two score-1.0 evaluations
- sad runs produce one partial artifact and seven completion messages
```

- [ ] **Step 2: Add or update a boundary test**

Add/extend a test in `tests/unit/architecture/test_public_api_boundaries.py`:

```python
from pathlib import Path


def test_e2e_tests_do_not_import_private_core_repositories() -> None:
    e2e_dir = Path("tests/e2e")
    forbidden = (
        "ergon_core.core.persistence.",
        "ergon_core.core.runtime.tasks.repository",
        "ergon_core.core.runtime.evaluation.persistence",
        "ergon_core.core.runtime.inngest.",
    )
    offenders: list[tuple[str, str]] = []
    for path in e2e_dir.rglob("*.py"):
        text = path.read_text()
        for needle in forbidden:
            if needle in text:
                offenders.append((str(path), needle))
    assert not offenders
```

- [ ] **Step 3: Run the boundary test and confirm failure before cleanup**

Run:

```bash
uv run pytest tests/unit/architecture/test_public_api_boundaries.py::test_e2e_tests_do_not_import_private_core_repositories -q
```

Expected before cleanup: fail with current `tests/e2e/_asserts.py` private persistence imports.

## Task 2: Update E2E Submission To Explicit Runtime Choices

**Files:**
- Modify: `tests/e2e/_submit.py`
- Modify: `tests/e2e/test_researchrubrics_smoke.py`
- Modify: `tests/e2e/test_minif2f_smoke.py`
- Modify: `tests/e2e/test_swebench_smoke.py`
- Test: `tests/unit/smoke_base/test_e2e_smoke_driver_pairs.py`

- [ ] **Step 1: Add a unit test for explicit e2e submission payloads**

Create or update `tests/unit/smoke_base/test_e2e_smoke_driver_pairs.py`:

```python
from tests.e2e._submit import build_cohort_payload


def test_build_cohort_payload_includes_explicit_runtime_choices() -> None:
    payload = build_cohort_payload(
        benchmark_slug="minif2f",
        slots=[("minif2f-smoke-worker", "minif2f-smoke-criterion")],
        cohort_key="ci-smoke-minif2f",
        sandbox_slug="minif2f",
        dependency_extras=("none",),
        model="openai:gpt-4o",
    )

    assert payload["benchmark_slug"] == "minif2f"
    assert payload["sandbox_slug"] == "minif2f"
    assert payload["dependency_extras"] == ["none"]
    assert payload["model"] == "openai:gpt-4o"
    assert payload["slots"] == [
        {
            "worker_slug": "minif2f-smoke-worker",
            "evaluator_slug": "minif2f-smoke-criterion",
        }
    ]
```

- [ ] **Step 2: Implement `build_cohort_payload()`**

In `tests/e2e/_submit.py`, add:

```python
def build_cohort_payload(
    *,
    benchmark_slug: str,
    slots: list[tuple[str, str]],
    cohort_key: str,
    sandbox_slug: str,
    dependency_extras: tuple[str, ...],
    model: str = "openai:gpt-4o",
) -> dict:
    return {
        "benchmark_slug": benchmark_slug,
        "slots": [
            {"worker_slug": worker, "evaluator_slug": evaluator}
            for worker, evaluator in slots
        ],
        "cohort_key": cohort_key,
        "sandbox_slug": sandbox_slug,
        "dependency_extras": list(dependency_extras),
        "model": model,
    }
```

- [ ] **Step 3: Route `submit_cohort()` through the payload builder**

Change `submit_cohort()` signature to accept explicit fields:

```python
async def submit_cohort(
    *,
    benchmark_slug: str,
    slots: list[tuple[str, str]],
    cohort_key: str,
    sandbox_slug: str,
    dependency_extras: tuple[str, ...],
    model: str = "openai:gpt-4o",
    timeout: int = 300,
) -> list[UUID]:
    payload = build_cohort_payload(
        benchmark_slug=benchmark_slug,
        slots=slots,
        cohort_key=cohort_key,
        sandbox_slug=sandbox_slug,
        dependency_extras=dependency_extras,
        model=model,
    )
    async with httpx.AsyncClient(base_url=_api_base(), timeout=30.0) as client:
        response = await client.post("/api/test/write/cohort", json=payload)
        ...
```

- [ ] **Step 4: Update each e2e driver call**

For `tests/e2e/test_minif2f_smoke.py`:

```python
run_ids = await submit_cohort(
    benchmark_slug=ENV,
    slots=[(worker, criterion) for _, worker, criterion in smoke_slots],
    cohort_key=cohort_key,
    sandbox_slug=ENV,
    dependency_extras=("none",),
    timeout=PER_RUN_TIMEOUT,
)
```

For `tests/e2e/test_swebench_smoke.py`:

```python
run_ids = await submit_cohort(
    benchmark_slug=ENV,
    slots=[(worker, criterion) for _, worker, criterion in smoke_slots],
    cohort_key=cohort_key,
    sandbox_slug=ENV,
    dependency_extras=("none",),
    timeout=PER_RUN_TIMEOUT,
)
```

For `tests/e2e/test_researchrubrics_smoke.py`:

```python
run_ids = await submit_cohort(
    benchmark_slug=ENV,
    slots=[(worker, criterion) for _, worker, criterion in smoke_slots],
    cohort_key=cohort_key,
    sandbox_slug=ENV,
    dependency_extras=("none",),
    timeout=PER_RUN_TIMEOUT,
)
```

Smoke fixtures replace production benchmark loaders, so e2e smoke should use `("none",)` unless the API harness explicitly requires package extras to test onboarding messaging.

- [ ] **Step 5: Run unit payload test**

Run:

```bash
uv run pytest tests/unit/smoke_base/test_e2e_smoke_driver_pairs.py -q
```

Expected: pass.

## Task 3: Replace Private E2E Reads With Test-Support Or Application Read Models

**Files:**
- Modify: `tests/e2e/_asserts.py`
- Modify: `tests/e2e/_read_contracts.py`
- Optional create: `ergon_core/ergon_core/test_support/e2e_read_helpers.py`
- Test: `tests/unit/smoke_base/test_e2e_read_helpers.py`

- [ ] **Step 1: Inventory direct private imports in `_asserts.py`**

Search:

```bash
rg "ergon_core.core.persistence|sqlmodel|select\\(" tests/e2e/_asserts.py
```

Expected current private access areas:

- graph node rows for temporal ordering
- `RunResource` rows for blob/artifact assertions
- `RunTaskEvaluation` rows for evaluation timestamp assertions
- sandbox WAL/event rows

- [ ] **Step 2: Keep `require_run_snapshot()` as the primary read path**

`tests/e2e/_read_contracts.py` may keep:

```python
from ergon_core.core.application.read_models.models import RunSnapshotDto
from ergon_core.core.application.read_models.runs import RunReadService
```

Do not import private repository classes in e2e drivers. If `RunReadService` moves, fix this wrapper only.

- [ ] **Step 3: Add test-support helpers only for data not exposed in snapshots**

If WAL/resource byte paths/evaluation timestamps are not exposed through `RunSnapshotDto`, create `ergon_core/ergon_core/test_support/e2e_read_helpers.py`:

```python
"""Stable test-support reads for e2e assertions."""

from pathlib import Path
from uuid import UUID

from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import (
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
    SandboxCommandWalEntry,
    SandboxEvent,
)
from sqlmodel import select


def list_run_resources(run_id: UUID) -> list[RunResource]:
    with get_session() as session:
        return list(session.exec(select(RunResource).where(RunResource.run_id == run_id)).all())


def read_resource_bytes(resource: RunResource) -> bytes:
    return Path(resource.file_path).read_bytes()


def list_sandbox_command_wal(run_id: UUID) -> list[SandboxCommandWalEntry]:
    with get_session() as session:
        return list(
            session.exec(
                select(SandboxCommandWalEntry).where(SandboxCommandWalEntry.run_id == run_id),
            ).all()
        )


def list_sandbox_events(run_id: UUID) -> list[SandboxEvent]:
    with get_session() as session:
        return list(session.exec(select(SandboxEvent).where(SandboxEvent.run_id == run_id)).all())


def list_root_evaluation_rows(run_id: UUID) -> tuple[RunTaskExecution | None, list[RunTaskEvaluation]]:
    # Implementation may use the current core layout internally.
    # E2E tests should import this function, not the private models directly.
    ...
```

If the core agent has already created stable equivalents under `ergon_core.test_support`, use those instead of adding this file.

- [ ] **Step 4: Move `_asserts.py` imports to stable helper functions**

Change `tests/e2e/_asserts.py` so private persistence imports are replaced by:

```python
from ergon_core.test_support.e2e_read_helpers import (
    list_root_evaluation_rows,
    list_run_resources,
    list_sandbox_command_wal,
    list_sandbox_events,
    read_resource_bytes,
)
```

Keep these direct test-support imports:

```python
from ergon_core.test_support.smoke_fixtures.smoke_base.constants import EXPECTED_SUBTASK_SLUGS
from ergon_core.test_support.smoke_fixtures.smoke_base.leaf_base import BaseSmokeLeafWorker
from ergon_core.test_support.smoke_fixtures.smoke_base.recursive import (
    NESTED_LINE_SLUGS,
    RecursiveSmokeWorkerBase,
)
from ergon_core.test_support.smoke_fixtures.smoke_base.worker_base import SmokeWorkerBase
```

- [ ] **Step 5: Re-run the boundary test**

Run:

```bash
uv run pytest tests/unit/architecture/test_public_api_boundaries.py::test_e2e_tests_do_not_import_private_core_repositories -q
```

Expected after cleanup: pass.

## Task 4: Finish Built-ins Registry And Factory Contracts

**Files:**
- Modify: `ergon_builtins/ergon_builtins/registry_core.py`
- Modify: `ergon_builtins/ergon_builtins/registry_data.py`
- Modify/create: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/worker_factory.py`
- Modify/create: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/worker_factory.py`
- Modify: `tests/unit/registry/test_builtin_pairings.py`
- Modify: `tests/unit/registry/test_react_factories.py`

- [ ] **Step 1: Verify explicit pairing table**

`tests/unit/registry/test_builtin_pairings.py` must contain registered pairings:

```python
PAIRINGS = [
    ("minif2f", "minif2f-react", "minif2f-rubric", "minif2f", ("none",)),
    ("swebench-verified", "swebench-react", "swebench-rubric", "swebench-verified", ("none",)),
    ("gdpeval", "gdpeval-react", "gdpeval-staged-rubric", "gdpeval", ("ergon-builtins[data]",)),
    ("researchrubrics", "researchrubrics-researcher", "researchrubrics-rubric", "researchrubrics", ("ergon-builtins[data]",)),
    ("researchrubrics-vanilla", "researchrubrics-researcher", "researchrubrics-rubric", "researchrubrics-vanilla", ("ergon-builtins[data]",)),
]
```

Use `("none",)` for e2e smoke replacement submissions, but keep production pairing documentation accurate for production data benchmarks.

- [ ] **Step 2: Register final evaluator slugs**

`registry_core.py` should expose both during migration:

```python
EVALUATORS = {
    "staged-rubric": StagedRubric,
    "gdpeval-staged-rubric": StagedRubric,
    ...
}
```

`registry_data.py` should expose:

```python
EVALUATORS = {
    "research-rubric": ResearchRubricsRubric,
    "researchrubrics-rubric": ResearchRubricsRubric,
}
```

- [ ] **Step 3: Keep benchmark-owned worker factory surfaces**

Required files:

```text
ergon_builtins/ergon_builtins/benchmarks/minif2f/worker_factory.py
ergon_builtins/ergon_builtins/benchmarks/swebench_verified/worker_factory.py
ergon_builtins/ergon_builtins/benchmarks/gdpeval/worker_factory.py
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/worker_factory.py
```

`researchrubrics/worker_factory.py` may re-export existing worker classes until a later physical move.

- [ ] **Step 4: Run registry tests**

Run:

```bash
uv run pytest tests/unit/registry/test_builtin_pairings.py tests/unit/registry/test_react_factories.py -q
```

Expected: pass.

## Task 5: Finish CLI Contract And Wrapper Behavior

**Files:**
- Modify: `ergon_cli/ergon_cli/main.py`
- Modify: `ergon_cli/ergon_cli/commands/experiment.py`
- Modify: `ergon_cli/ergon_cli/commands/benchmark.py`
- Modify: `tests/unit/cli/test_experiment_cli.py`
- Modify: `tests/unit/cli/test_benchmark_setup.py`

- [ ] **Step 1: Keep explicit define args required**

Parser requirements:

```text
ergon experiment define <benchmark>
  --worker <worker>
  --model <backend:model>
  --evaluator <evaluator>
  --sandbox <sandbox>
  --extras <extra-or-none>
```

Test with:

```bash
uv run pytest tests/unit/cli/test_experiment_cli.py::test_experiment_define_requires_explicit_runtime_choices -q
```

- [ ] **Step 2: Keep `benchmark run` as define-plus-run wrapper**

`benchmark run` should parse the same explicit fields:

```text
ergon benchmark run <benchmark>
  --limit 1
  --worker <worker>
  --model <backend:model>
  --evaluator <evaluator>
  --sandbox <sandbox>
  --extras <extra-or-none>
```

If `ExperimentLaunchService.wait/timeout_seconds` is not implemented, do not expose `--timeout` or `--no-wait` on `benchmark run`. The wrapper should submit and print run IDs, not pretend to block.

- [ ] **Step 3: Keep `benchmark setup` success hint explicit**

Expected hint shape:

```text
ergon benchmark run <slug> --limit 1 --worker <worker> --model <model> --evaluator <evaluator> --sandbox <slug> --extras none
```

Regression test:

```python
def test_setup_success_hint_uses_explicit_runtime_choices(...):
    rc = setup_benchmark(_make_args())
    out = capsys.readouterr().out
    assert "--worker" in out
    assert "--evaluator" in out
    assert "--sandbox" in out
    assert "--extras" in out
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
uv run pytest tests/unit/cli/test_experiment_cli.py tests/unit/cli/test_benchmark_setup.py -q
```

Expected: pass.

## Task 6: Align `/api/test/write/cohort` With Explicit Test Harness Contract

**Files:**
- Modify: `ergon_core/ergon_core/core/api/test_harness.py` or the current stable test harness module if moved
- Modify: `tests/integration/smokes/test_smoke_harness.py`
- Modify: `tests/e2e/_submit.py`

- [ ] **Step 1: Ensure request DTO accepts explicit sandbox/extras**

The stable test harness write request should accept:

```python
class SubmitCohortRequest(BaseModel):
    benchmark_slug: str
    slots: list[CohortSlotRequest]
    cohort_key: str
    sandbox_slug: str | None = None
    dependency_extras: tuple[str, ...] = ("none",)
    model: str = "openai:gpt-4o"
    limit: int = 1
```

- [ ] **Step 2: Ensure the harness uses the same define/run service path**

The handler should pass:

```python
ExperimentDefineRequest(
    benchmark_slug=body.benchmark_slug,
    cohort_id=cohort.id,
    limit=body.limit,
    default_model_target=body.model,
    default_worker_team={"primary": slot.worker_slug},
    default_evaluator_slug=slot.evaluator_slug,
    sandbox_slug=body.sandbox_slug or body.benchmark_slug,
    dependency_extras=body.dependency_extras,
    metadata={"source": "test-harness"},
)
```

If the core facade DTO names differ after the core refactor, adapt to the stable facade shape rather than private repositories.

- [ ] **Step 3: Add integration assertion**

In `tests/integration/smokes/test_smoke_harness.py`, assert the write endpoint accepts a payload with `sandbox_slug` and `dependency_extras` and returns run IDs.

- [ ] **Step 4: Run smoke harness integration test**

Run:

```bash
uv run pytest tests/integration/smokes/test_smoke_harness.py -q
```

Expected: pass if stack dependencies for integration are available; otherwise skip should be environment-gated.

## Task 7: Preserve E2E Runtime Assertions While Updating Access Paths

**Files:**
- Modify: `tests/e2e/_asserts.py`
- Modify: `tests/e2e/test_researchrubrics_smoke.py`
- Modify: `tests/e2e/test_minif2f_smoke.py`
- Modify: `tests/e2e/test_swebench_smoke.py`
- Modify: `ergon-dashboard/tests/e2e/*.smoke.spec.ts`

- [ ] **Step 1: Keep the behavioral assertions hard**

Do not weaken these assertions:

```python
assert snapshot.total_tasks == 12
assert snapshot.total_leaf_tasks == 10
assert len(probes) == 10
assert len(resources) == 20
assert event_count == 26
assert len(evaluations) == 2
assert scores == [1.0, 1.0]
assert len(msgs) == 11
```

Sad path:

```python
assert by_slug["l_2"].status == FAILED
assert by_slug["l_3"].status == BLOCKED
assert by_slug["l_3"].started_at is None
assert len(msgs) == 7
```

- [ ] **Step 2: Update imports only**

Replace any private core imports with:

```python
from tests.e2e._read_contracts import require_run_snapshot
from ergon_core.test_support.smoke_fixtures.smoke_base.constants import EXPECTED_SUBTASK_SLUGS
```

And, where direct DB access is still needed:

```python
from ergon_core.test_support.e2e_read_helpers import ...
```

- [ ] **Step 3: Keep dashboard assertions aligned**

Playwright specs should assert visible behavior:

```text
- run status is completed/failed as appropriate
- all expected task nodes appear
- failed l_2 and blocked l_3 are visible on sad path
- resource/evaluation panels render when expected
```

Do not assert private API response shapes unless the dashboard API marks them public/stable.

## Task 8: Run The Non-E2E Verification Gate

**Files:**
- No code changes unless tests fail.

- [ ] **Step 1: Run focused unit/integration tests**

Run:

```bash
uv run pytest \
  tests/unit/registry/test_react_factories.py \
  tests/unit/registry/test_builtin_pairings.py \
  tests/unit/cli/test_experiment_cli.py \
  tests/unit/cli/test_benchmark_setup.py \
  tests/unit/smoke_base/test_e2e_smoke_driver_pairs.py \
  tests/unit/architecture/test_public_api_boundaries.py \
  tests/integration/smokes/test_smoke_harness.py \
  -q
```

Expected: pass or environment-gated integration skip. Any import failure from `tests/e2e` is a blocker.

- [ ] **Step 2: Run e2e collection without executing live stack**

Run:

```bash
uv run pytest tests/e2e --collect-only -q
```

Expected: collection succeeds. This catches stale import paths without needing the stack.

- [ ] **Step 3: Run lint diagnostics on touched test/docs paths**

Use IDE lints for:

```text
tests/e2e/
tests/unit/registry/
tests/unit/cli/
tests/unit/smoke_base/
docs/superpowers/plans/
```

Expected: no new code-specific diagnostics. Environment import-resolution warnings are non-blocking only if pytest confirms imports.

## Task 9: Full E2E Execution Gate

**Files:**
- No code changes unless runtime evidence fails.

- [ ] **Step 1: Verify stack env**

Required environment:

```text
ENABLE_TEST_HARNESS=1
ENABLE_SMOKE_FIXTURES=1
ERGON_STARTUP_PLUGINS=ergon_core.test_support.smoke_fixtures:register_smoke_fixtures
ERGON_API_BASE_URL=http://127.0.0.1:9000
TEST_HARNESS_SECRET=<configured secret if required>
E2B_API_KEY=<available for real sandbox e2e>
```

- [ ] **Step 2: Run one smoke leg first**

Run:

```bash
uv run pytest tests/e2e/test_minif2f_smoke.py -q -s
```

Expected:

- one happy run reaches `completed`
- one sad run reaches `failed`
- all hard assertions pass
- Playwright spec completes or captures failure screenshots

- [ ] **Step 3: Run all smoke legs**

Run:

```bash
uv run pytest tests/e2e -q -s
```

Expected:

- ResearchRubrics, MiniF2F, and SWE-Bench each submit happy/sad cohorts
- happy runs pass graph/resource/turn/evaluation/dashboard assertions
- sad runs pass blocked/failure/partial-artifact assertions

## Task 10: Review And Handoff To Real-LLM Canaries

**Files:**
- Modify only if review finds issues.

- [ ] **Step 1: Request code review**

Send reviewer scope:

```text
Review built-ins, CLI, and e2e refactor completion.
Check that:
- no benchmark profiles/default pairings remain
- CLI requires explicit worker/model/evaluator/sandbox/extras
- e2e uses HTTP/test-support/read-model boundaries
- runtime behavior assertions remain hard
- no private core repository imports remain in e2e tests
```

- [ ] **Step 2: Fix Critical and Important review findings**

Follow review feedback with tests for each fix.

- [ ] **Step 3: Decide real-LLM canary timing**

Only after e2e smoke is green, run or schedule:

```bash
ERGON_REAL_LLM=1 uv run pytest tests/real_llm -q -s
```

If real-LLM tests still use stale CLI paths, update them to the same explicit runtime choice contract before running.

## Completion Criteria

- `tests/e2e --collect-only` succeeds without private core import failures.
- `tests/unit/architecture/test_public_api_boundaries.py` confirms e2e tests do not import private core repository/runtime internals.
- `tests/unit/registry/test_builtin_pairings.py` covers all documented production benchmark pairings.
- CLI parser tests prove explicit arguments are required.
- `/api/test/write/cohort` accepts explicit sandbox/extras and uses the same define/run facade path.
- Full e2e smoke suite preserves existing behavior assertions:
  - 12 tasks, 10 leaves, 20 resources, 26 turns, 2 root evaluations on happy path
  - `l_2` failed, `l_3` blocked, 7 completion messages on sad path
- Code review has no unresolved Critical or Important findings.

