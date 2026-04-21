---
status: active
opened: 2026-04-18
author: deepflow-research
architecture_refs: [docs/architecture/06_builtins.md, docs/architecture/07_testing.md]
supersedes: []
superseded_by: null
---

# RFC: `FixedDelegationStubWorker` and canonical per-benchmark smoke pattern

## Problem

Every benchmark should have a CI smoke that deterministically exercises the full
pipeline: configuration loads from the registry, events propagate through Inngest,
evaluators fire, data lands in Postgres, the worker transitions to a terminal status,
and the frontend renders the resulting run.

Today we have nine benchmarks and three ad-hoc stub workers:

| File | `type_slug` | Problem |
|---|---|---|
| `ergon_builtins/workers/baselines/stub_worker.py:12` | `stub-worker` | Generic flat output; no subgraph shape; does not exercise delegation paths |
| `ergon_builtins/workers/baselines/smoke_test_worker.py:18` | `smoke-test-worker` | Requires a real E2B sandbox; useless for benchmarks with no sandbox dependency |
| `ergon_builtins/workers/research_rubrics/stub_worker.py:46` | `researchrubrics-stub` | Benchmark-specific; not reusable across benchmarks |

None of the three stubs are wired into a Playwright assertion path; none enforce a
subgraph shape; there is no "every benchmark has a smoke" invariant. The result:
graph-propagation regressions, persistence regressions, and frontend-rendering
regressions can all land silently because no single test asserts on all four at once
per benchmark.

Architecture doc `docs/architecture/06_builtins.md §4` already has:
> Every benchmark MUST ship a stub worker that exercises the graph propagation and
> eval pipeline without external LLM or sandbox dependencies. Enforcement is weak
> today: stub-worker coverage lags the registered benchmark set.

Architecture doc `docs/architecture/07_testing.md §7` has:
> A per-benchmark smoke pattern at `tests/integration/smokes/test_<slug>_smoke.py`,
> using a shared fixed-delegation stub worker to exercise a complex-enough subgraph.

This RFC makes those documented aspirations concrete.

## Proposal

1. Add `FixedDelegationStubWorker` at
   `ergon_builtins/workers/stubs/fixed_delegation_stub_worker.py`. Its `.execute()`
   deterministically emits six `GenerationTurn` objects that represent a manager
   delegating to three leaf workers in a fan-out / fan-in subgraph: `subtask_a`,
   `subtask_b`, `subtask_c` → `join`. The subgraph shape is hard-coded and
   parameterless; determinism is the point.
2. Add `FixedLeafStubWorker` at
   `ergon_builtins/workers/stubs/fixed_leaf_stub_worker.py` for static-DAG benchmarks
   (no manager). Emits one `GenerationTurn` with deterministic text.
3. Add a `stubs/` subpackage and register both new workers in `registry_core.py`.
4. Canonical smoke test location: `tests/integration/smokes/test_<slug>_smoke.py`.
   One file per benchmark. Each file drives the benchmark with the appropriate stub
   worker, runs against real Postgres + real Inngest (no sandbox), and asserts:
   - Graph mutations land in Postgres (all nodes `COMPLETED`).
   - Evaluator fires and criteria produce a score.
   - The FastAPI dashboard API returns the expected run shape.
   - Playwright renders the expected view (via test-harness endpoints from the
     companion RFC `docs/rfcs/active/2026-04-18-test-harness-endpoints.md`).
5. CI wiring: smokes run on every PR as part of the integration tier (real Postgres +
   real Inngest dev server; no E2B).
6. A discovery test `tests/integration/smokes/test_smoke_coverage.py` walks the
   benchmark registry and asserts a matching smoke file exists for every slug. This
   enforces the new invariant at CI time.

**Not included in this RFC:** in-memory sandbox fake. Per
`docs/architecture/07_testing.md §7`, the first pass uses real E2B for tests that
actually need a sandbox, and stubbed-sandbox otherwise. This RFC addresses the
no-sandbox path only.

**Dependency on `docs/rfcs/active/2026-04-18-test-harness-endpoints.md`:** the
Playwright step in each smoke file requires the test-harness FastAPI mount
(`/api/test/read/*`). The backend DB-assertion steps do not require it. PRs 1–2 land
without Playwright; PR 3 adds the frontend assertion once the harness endpoints exist.

## Architecture overview

### Before

```
benchmark slug → worker_type → WORKERS[worker_type]
                                    │
                                    ▼
                         (ad-hoc stub OR no stub)
                                    │
                    no shared smoke shape; no invariant
```

### After

```
benchmark slug → worker_type → WORKERS[worker_type]
                                    │
                              ┌─────┴─────┐
                  delegation   │           │  leaf-only
                  benchmark    ▼           ▼
               FixedDelegationStubWorker  FixedLeafStubWorker
                              │
                 deterministic 6-turn execute()
                   fan-out: subtask_a / _b / _c
                   fan-in:  join
                              │
                              ▼
              tests/integration/smokes/test_<slug>_smoke.py
                              │
                ┌─────────────┼──────────────┐
                ▼             ▼              ▼
         Postgres nodes  evaluator score  dashboard API
                                               │
                                               ▼
                                        Playwright view
                                   (requires harness endpoints RFC)
```

### Data flow within `FixedDelegationStubWorker.execute()`

```
execute(task, context)
  │
  ├─ yield Turn 0: UserPromptPart("Delegating to subtask_a")
  │                + ToolCallPart(tool_name="add_subtask", args={task_key: "subtask_a"})
  ├─ yield Turn 1: ToolReturnPart(tool_name="add_subtask", content="ok: subtask_a")
  │                + ToolCallPart(tool_name="add_subtask", args={task_key: "subtask_b"})
  ├─ yield Turn 2: ToolReturnPart(tool_name="add_subtask", content="ok: subtask_b")
  │                + ToolCallPart(tool_name="add_subtask", args={task_key: "subtask_c"})
  ├─ yield Turn 3: ToolReturnPart(tool_name="add_subtask", content="ok: subtask_c")
  │                + TextPart("Waiting for subtasks...")
  ├─ yield Turn 4: TextPart("Subtasks complete. Synthesizing...")
  └─ yield Turn 5: TextPart("Final synthesis: FixedDelegationStubWorker output")
                   ← this is what get_output() reads
```

Turn structure uses the same `GenerationTurn`, `ToolCallPart`, `ToolReturnPart`,
`TextPart`, and `UserPromptPart` types already imported by every worker (see
`ergon_core/ergon_core/api/generation.py`). No new types are introduced.

## Type / interface definitions

No new public types. Both new workers implement the existing `Worker` ABC from
`ergon_core/ergon_core/api/worker.py:19`.

```python
# ergon_builtins/ergon_builtins/workers/stubs/__init__.py

from ergon_builtins.workers.stubs.fixed_delegation_stub_worker import (
    FixedDelegationStubWorker,
)
from ergon_builtins.workers.stubs.fixed_leaf_stub_worker import FixedLeafStubWorker

__all__ = ["FixedDelegationStubWorker", "FixedLeafStubWorker"]
```

## Full implementations

### `FixedDelegationStubWorker`

```python
# ergon_builtins/ergon_builtins/workers/stubs/fixed_delegation_stub_worker.py
"""Canonical CI stub worker for delegation-style benchmarks.

Deterministically emits six GenerationTurn objects that represent a manager
delegating to three subtasks (fan-out) followed by a synthesis (fan-in).
No LLM calls. No sandbox. No randomness.

Use with benchmarks that exercise the manager → subtask delegation path
(e.g. ``delegation-smoke``, future manager-style benchmarks).
"""

from collections.abc import AsyncGenerator
from typing import ClassVar

from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import (
    GenerationTurn,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

_STUB_SUBTASK_KEYS = ("subtask_a", "subtask_b", "subtask_c")


class FixedDelegationStubWorker(Worker):
    """Deterministic stub for delegation-style benchmarks.

    Emits six turns with a hard-coded fan-out / fan-in subgraph shape.
    The ToolCallPart / ToolReturnPart pairs exercise the turn-persistence
    path and the dashboard rendering path without requiring a live model.
    """

    type_slug: ClassVar[str] = "fixed-delegation-stub"

    def __init__(
        self,
        *,
        name: str = "fixed-delegation-stub",
        model: str | None = None,
    ) -> None:
        super().__init__(name=name, model=model)

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        # Turn 0 — first subtask delegation
        yield GenerationTurn(
            messages_in=[UserPromptPart(content=f"Task: {task.description}")],
            response_parts=[
                ToolCallPart(
                    tool_name="add_subtask",
                    tool_call_id="call_0",
                    args={"task_key": _STUB_SUBTASK_KEYS[0], "description": "Stub sub-task A"},
                )
            ],
        )
        # Turn 1 — second subtask delegation
        yield GenerationTurn(
            messages_in=[
                ToolReturnPart(
                    tool_call_id="call_0",
                    tool_name="add_subtask",
                    content=f"ok: {_STUB_SUBTASK_KEYS[0]}",
                )
            ],
            response_parts=[
                ToolCallPart(
                    tool_name="add_subtask",
                    tool_call_id="call_1",
                    args={"task_key": _STUB_SUBTASK_KEYS[1], "description": "Stub sub-task B"},
                )
            ],
        )
        # Turn 2 — third subtask delegation
        yield GenerationTurn(
            messages_in=[
                ToolReturnPart(
                    tool_call_id="call_1",
                    tool_name="add_subtask",
                    content=f"ok: {_STUB_SUBTASK_KEYS[1]}",
                )
            ],
            response_parts=[
                ToolCallPart(
                    tool_name="add_subtask",
                    tool_call_id="call_2",
                    args={"task_key": _STUB_SUBTASK_KEYS[2], "description": "Stub sub-task C"},
                )
            ],
        )
        # Turn 3 — all subtasks spawned; begin wait
        yield GenerationTurn(
            messages_in=[
                ToolReturnPart(
                    tool_call_id="call_2",
                    tool_name="add_subtask",
                    content=f"ok: {_STUB_SUBTASK_KEYS[2]}",
                )
            ],
            response_parts=[TextPart(content="All subtasks spawned. Waiting for results.")],
        )
        # Turn 4 — subtasks "complete"; begin synthesis
        yield GenerationTurn(
            response_parts=[TextPart(content="Subtask results received. Synthesizing.")],
        )
        # Turn 5 — final synthesis (this is what get_output() reads)
        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        f"FixedDelegationStubWorker synthesis for {task.task_key}: "
                        f"sub-tasks {', '.join(_STUB_SUBTASK_KEYS)} completed successfully."
                    )
                )
            ],
        )
```

### `FixedLeafStubWorker`

```python
# ergon_builtins/ergon_builtins/workers/stubs/fixed_leaf_stub_worker.py
"""Canonical CI stub worker for leaf-task (non-delegation) benchmarks.

Emits one deterministic GenerationTurn with no tool calls.
No LLM calls. No sandbox. No randomness.

Use with static-DAG benchmarks that have no manager (e.g. ``smoke-test``,
``minif2f`` when run in stub mode, ``swebench-verified`` when run in stub mode).
"""

from collections.abc import AsyncGenerator
from typing import ClassVar

from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn, TextPart, UserPromptPart


class FixedLeafStubWorker(Worker):
    """Deterministic stub for leaf-task benchmarks.

    Emits a single turn with hard-coded output text. The output text
    is stable across runs so evaluator scores are reproducible in CI.
    """

    type_slug: ClassVar[str] = "fixed-leaf-stub"

    def __init__(
        self,
        *,
        name: str = "fixed-leaf-stub",
        model: str | None = None,
    ) -> None:
        super().__init__(name=name, model=model)

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        yield GenerationTurn(
            messages_in=[UserPromptPart(content=f"Task: {task.description}")],
            response_parts=[
                TextPart(
                    content=f"FixedLeafStubWorker output for task {task.task_key}."
                )
            ],
        )
```

### Discovery test

```python
# tests/integration/smokes/test_smoke_coverage.py
"""Invariant: every registered benchmark must have a smoke test file.

Walks BENCHMARKS (always-available + data-extra) and asserts a matching
``tests/integration/smokes/test_<slug>_smoke.py`` file exists.
Fails CI the moment a benchmark ships without a smoke test.
"""

from pathlib import Path

import pytest
from ergon_builtins.registry_core import BENCHMARKS as CORE_BENCHMARKS

SMOKES_DIR = Path(__file__).parent

# Data-extra benchmarks may not be installed in every CI environment.
# The discovery test only covers core benchmarks unless data extras are
# present. The import guard keeps this test in the fast tier.
try:
    from ergon_builtins.registry_data import BENCHMARKS as DATA_BENCHMARKS
except ImportError:
    DATA_BENCHMARKS = {}  # type: ignore[assignment]

ALL_SLUGS = list({**CORE_BENCHMARKS, **DATA_BENCHMARKS}.keys())


@pytest.mark.parametrize("slug", ALL_SLUGS)
def test_smoke_file_exists(slug: str) -> None:
    """Each benchmark slug must have tests/integration/smokes/test_<slug>_smoke.py."""
    slug_underscored = slug.replace("-", "_")
    expected = SMOKES_DIR / f"test_{slug_underscored}_smoke.py"
    assert expected.exists(), (
        f"Benchmark '{slug}' has no smoke test. "
        f"Expected: {expected}. "
        f"Add tests/integration/smokes/test_{slug_underscored}_smoke.py and wire it "
        f"with FixedDelegationStubWorker (delegation) or FixedLeafStubWorker (leaf)."
    )
```

### First smoke: `delegation-smoke`

```python
# tests/integration/smokes/test_delegation_smoke_smoke.py
"""Smoke test for the delegation-smoke benchmark.

Exercises: config load → workflow init → fixed-delegation-stub execute (6 turns) →
evaluator score → run COMPLETED → dashboard API shape.

Infrastructure: real Postgres, real Inngest dev server (Docker stack).
No E2B sandbox required.
"""

import pytest
from ergon_builtins.benchmarks.delegation_smoke.benchmark import DelegationSmokeBenchmark
from ergon_builtins.evaluators.rubrics.stub_rubric import StubRubric
from ergon_builtins.workers.stubs.fixed_delegation_stub_worker import FixedDelegationStubWorker
from ergon_core.api import Experiment
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution
from ergon_core.core.runtime.services.run_service import create_run
from ergon_core.core.runtime.services.workflow_initialization_service import (
    WorkflowInitializationService,
)
from sqlmodel import select

from tests.e2e.conftest import run_benchmark


class TestDelegationSmokeSmoke:
    """delegation-smoke benchmark with FixedDelegationStubWorker."""

    def test_run_completes(self) -> None:
        result = run_benchmark(
            "delegation-smoke",
            worker="fixed-delegation-stub",
            evaluator="stub-rubric",
            cohort="ci-smoke",
        )
        assert result.returncode == 0, (
            f"CLI exited {result.returncode}:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "Status:     completed" in result.stdout

    def test_all_executions_completed(self) -> None:
        run_benchmark(
            "delegation-smoke",
            worker="fixed-delegation-stub",
            evaluator="stub-rubric",
            cohort="ci-smoke-exec",
        )
        with get_session() as session:
            latest_run = session.exec(
                select(RunRecord).order_by(RunRecord.created_at.desc()).limit(1)  # type: ignore[union-attr]
            ).first()
            assert latest_run is not None
            assert latest_run.status == RunStatus.COMPLETED
            executions = list(
                session.exec(
                    select(RunTaskExecution).where(RunTaskExecution.run_id == latest_run.id)
                ).all()
            )
            assert len(executions) >= 1
            for ex in executions:
                assert ex.status == TaskExecutionStatus.COMPLETED

    def test_six_turns_persisted(self) -> None:
        """FixedDelegationStubWorker emits exactly 6 turns; all must persist."""
        from ergon_core.core.persistence.context.repository import ContextEventRepository

        run_benchmark(
            "delegation-smoke",
            worker="fixed-delegation-stub",
            evaluator="stub-rubric",
            cohort="ci-smoke-turns",
        )
        with get_session() as session:
            latest_run = session.exec(
                select(RunRecord).order_by(RunRecord.created_at.desc()).limit(1)  # type: ignore[union-attr]
            ).first()
            assert latest_run is not None
            executions = list(
                session.exec(
                    select(RunTaskExecution).where(RunTaskExecution.run_id == latest_run.id)
                ).all()
            )
            assert len(executions) == 1
            repo = ContextEventRepository()
            events = repo.get_for_execution(session, executions[0].id)
        # 6 turns × ≥1 context event each
        assert len(events) >= 6, (
            f"Expected ≥6 context events from 6 turns, got {len(events)}"
        )

    def test_evaluator_score(self) -> None:
        from ergon_core.core.persistence.telemetry.models import RunTaskEvaluation

        run_benchmark(
            "delegation-smoke",
            worker="fixed-delegation-stub",
            evaluator="stub-rubric",
            cohort="ci-smoke-eval",
        )
        with get_session() as session:
            latest_run = session.exec(
                select(RunRecord).order_by(RunRecord.created_at.desc()).limit(1)  # type: ignore[union-attr]
            ).first()
            assert latest_run is not None
            evals = list(
                session.exec(
                    select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == latest_run.id)
                ).all()
            )
        assert len(evals) > 0, "Expected at least one evaluation"
        for ev in evals:
            assert ev.score is not None

    def test_dashboard_api_run_shape(self) -> None:
        """FastAPI /api/runs/<id> returns expected run shape after benchmark completes."""
        import httpx

        result = run_benchmark(
            "delegation-smoke",
            worker="fixed-delegation-stub",
            evaluator="stub-rubric",
            cohort="ci-smoke-api",
        )
        assert result.returncode == 0
        with get_session() as session:
            latest_run = session.exec(
                select(RunRecord).order_by(RunRecord.created_at.desc()).limit(1)  # type: ignore[union-attr]
            ).first()
            assert latest_run is not None
            run_id = str(latest_run.id)

        # Requires the API to be running (Docker stack).
        import os
        api_base = os.environ.get("ERGON_API_URL", "http://localhost:8000")
        resp = httpx.get(f"{api_base}/api/runs/{run_id}", timeout=10)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert "tasks" in body
```

### Second smoke: `smoke-test`

```python
# tests/integration/smokes/test_smoke_test_smoke.py
"""Smoke test for the smoke-test benchmark using FixedLeafStubWorker.

smoke-test is a leaf-only benchmark (no manager); uses FixedLeafStubWorker.
"""

import pytest
from tests.e2e.conftest import run_benchmark
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunRecord
from sqlmodel import select


class TestSmokeTestSmoke:
    def test_run_completes(self) -> None:
        result = run_benchmark(
            "smoke-test",
            worker="fixed-leaf-stub",
            evaluator="stub-rubric",
            cohort="ci-smoke",
        )
        assert result.returncode == 0
        assert "Status:     completed" in result.stdout

    def test_run_status_completed_in_db(self) -> None:
        run_benchmark(
            "smoke-test",
            worker="fixed-leaf-stub",
            evaluator="stub-rubric",
            cohort="ci-smoke-db",
        )
        with get_session() as session:
            latest_run = session.exec(
                select(RunRecord).order_by(RunRecord.created_at.desc()).limit(1)  # type: ignore[union-attr]
            ).first()
            assert latest_run is not None
            assert latest_run.status == RunStatus.COMPLETED
```

## Exact diffs for modified files

### `ergon_builtins/ergon_builtins/registry_core.py`

Add two imports and two `WORKERS` entries:

```diff
+from ergon_builtins.workers.stubs.fixed_delegation_stub_worker import (
+    FixedDelegationStubWorker,
+)
+from ergon_builtins.workers.stubs.fixed_leaf_stub_worker import FixedLeafStubWorker
 from ergon_builtins.workers.baselines.manager_researcher_worker import ManagerResearcherWorker
 ...

 WORKERS: dict[str, type[Worker]] = {
     "stub-worker": StubWorker,
     "training-stub": TrainingStubWorker,
     "smoke-test-worker": SmokeTestWorker,
     "react-v1": ReActWorker,
     "minif2f-react": MiniF2FReActWorker,
     "swebench-react": SWEBenchReActWorker,
     "manager-researcher": ManagerResearcherWorker,
     "researcher": StubWorker,
     "researchrubrics-stub": StubResearchRubricsWorker,
+    "fixed-delegation-stub": FixedDelegationStubWorker,
+    "fixed-leaf-stub": FixedLeafStubWorker,
 }
```

Current `WORKERS` dict is at
`ergon_builtins/ergon_builtins/registry_core.py:54`. The new entries are added
at lines 63–64 (relative to current file).

### `ergon_builtins/ergon_builtins/workers/__init__.py`

```diff
 from ergon_builtins.workers.baselines.react_worker import ReActWorker
 from ergon_builtins.workers.baselines.stub_worker import StubWorker
+from ergon_builtins.workers.stubs.fixed_delegation_stub_worker import (
+    FixedDelegationStubWorker,
+)
+from ergon_builtins.workers.stubs.fixed_leaf_stub_worker import FixedLeafStubWorker

-__all__ = ["ReActWorker", "StubWorker"]
+__all__ = [
+    "FixedDelegationStubWorker",
+    "FixedLeafStubWorker",
+    "ReActWorker",
+    "StubWorker",
+]
```

Current `__init__.py` is at
`ergon_builtins/ergon_builtins/workers/__init__.py:1–4`.

## Package structure

New subpackage:

```
ergon_builtins/ergon_builtins/workers/stubs/
    __init__.py
    fixed_delegation_stub_worker.py
    fixed_leaf_stub_worker.py
```

`__init__.py` contents shown above in "Type / interface definitions".

New test directory:

```
tests/integration/smokes/
    __init__.py                         (empty)
    test_smoke_coverage.py
    test_delegation_smoke_smoke.py
    test_smoke_test_smoke.py
    test_minif2f_smoke.py               (PR 2 — stub only, no Lean sandbox)
    test_swebench_verified_smoke.py     (PR 2)
    test_researchrubrics_smoke_smoke.py (PR 2 — uses StubResearchRubricsWorker / existing path)
    test_gdpeval_smoke.py               (PR 2 — data-extra, gated by import guard)
    test_delegation_smoke_smoke.py      (already above, PR 1)
```

Each file in the `smokes/` directory follows the same four-assertion pattern
(run completes, executions COMPLETED, evaluator score, dashboard API shape).
The discovery test (`test_smoke_coverage.py`) fails fast if a file is missing.

## Implementation order

| Step | What | Files touched | PR |
|---|---|---|---|
| 1 | Add `stubs/` subpackage with `__init__.py` (empty init, just the package) | ADD `ergon_builtins/workers/stubs/__init__.py` | 1 |
| 2 | Implement `FixedDelegationStubWorker` with 6-turn `execute()` | ADD `ergon_builtins/workers/stubs/fixed_delegation_stub_worker.py` | 1 |
| 3 | Implement `FixedLeafStubWorker` with 1-turn `execute()` | ADD `ergon_builtins/workers/stubs/fixed_leaf_stub_worker.py` | 1 |
| 4 | Register both slugs in `registry_core.py`; update `workers/__init__.py` | MODIFY `registry_core.py`, MODIFY `workers/__init__.py` | 1 |
| 5 | Unit tests: both workers determinism, turn count, tool call shapes | ADD `tests/state/test_stub_workers.py` | 1 |
| 6 | Add `tests/integration/smokes/__init__.py` | ADD (empty) | 1 |
| 7 | Add discovery test (`test_smoke_coverage.py`) — initially skips missing files | ADD `tests/integration/smokes/test_smoke_coverage.py` | 1 |
| 8 | First smoke: `delegation-smoke` with `FixedDelegationStubWorker` | ADD `tests/integration/smokes/test_delegation_smoke_smoke.py` | 1 |
| 9 | Second smoke: `smoke-test` with `FixedLeafStubWorker` | ADD `tests/integration/smokes/test_smoke_test_smoke.py` | 1 |
| 10 | Smoke: `minif2f` (stub mode, no sandbox) + `swebench-verified` (stub mode) | ADD 2 smoke files | 2 |
| 11 | Smoke: `researchrubrics-smoke` (reuse `StubResearchRubricsWorker`), `researchrubrics`, `gdpeval` (data-extra, import-gated) | ADD 3 smoke files | 2 |
| 12 | Make discovery test hard-fail (remove skip guard) once all 9 benchmarks covered | MODIFY `test_smoke_coverage.py` | 2 |
| 13 | Delete `StubWorker`, `SmokeTestWorker`, `StubResearchRubricsWorker` and remove from registry — only after every benchmark migrated | MODIFY registry; DELETE 3 files | 3 |
| 14 | Playwright step in each smoke file (requires test-harness endpoints RFC) | MODIFY all 9 smoke files | 3 |

PRs 1 and 2 can run in CI without Playwright. PR 3 depends on the test-harness
endpoints RFC; it is the only PR that requires the companion RFC to have landed.

## File map

### ADD

| File | Purpose |
|---|---|
| `ergon_builtins/ergon_builtins/workers/stubs/__init__.py` | Package init; re-exports both stub workers |
| `ergon_builtins/ergon_builtins/workers/stubs/fixed_delegation_stub_worker.py` | `FixedDelegationStubWorker` — 6-turn deterministic delegation stub |
| `ergon_builtins/ergon_builtins/workers/stubs/fixed_leaf_stub_worker.py` | `FixedLeafStubWorker` — 1-turn deterministic leaf stub |
| `tests/state/test_stub_workers.py` | Unit tests for turn count, tool call shapes, determinism |
| `tests/integration/smokes/__init__.py` | Empty package init |
| `tests/integration/smokes/test_smoke_coverage.py` | Discovery test: every benchmark MUST have a smoke file |
| `tests/integration/smokes/test_delegation_smoke_smoke.py` | Smoke: `delegation-smoke` |
| `tests/integration/smokes/test_smoke_test_smoke.py` | Smoke: `smoke-test` |
| `tests/integration/smokes/test_minif2f_smoke.py` | Smoke: `minif2f` (stub mode) |
| `tests/integration/smokes/test_swebench_verified_smoke.py` | Smoke: `swebench-verified` (stub mode) |
| `tests/integration/smokes/test_researchrubrics_smoke_smoke.py` | Smoke: `researchrubrics-smoke` |
| `tests/integration/smokes/test_researchrubrics_smoke.py` | Smoke: `researchrubrics` (data-extra) |
| `tests/integration/smokes/test_gdpeval_smoke.py` | Smoke: `gdpeval` (data-extra) |

### MODIFY

| File | Changes |
|---|---|
| `ergon_builtins/ergon_builtins/registry_core.py` | Import `FixedDelegationStubWorker`, `FixedLeafStubWorker`; add `"fixed-delegation-stub"` and `"fixed-leaf-stub"` to `WORKERS` dict |
| `ergon_builtins/ergon_builtins/workers/__init__.py` | Import and re-export both new workers; extend `__all__` |

## Testing approach

### Unit tests (`tests/state/test_stub_workers.py`)

```python
# tests/state/test_stub_workers.py
"""Unit tests for FixedDelegationStubWorker and FixedLeafStubWorker.

These run in the fast tier: no Postgres, no Inngest, no sandbox.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from ergon_core.api.generation import TextPart, ToolCallPart, ToolReturnPart
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext


def _task(task_key: str = "test-task") -> BenchmarkTask:
    return BenchmarkTask(
        task_key=task_key,
        instance_key="default",
        description="A deterministic test task.",
    )


def _context() -> WorkerContext:
    return WorkerContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sbx-test",
    )


async def _collect_turns(worker, task, context):
    turns = []
    async for turn in worker.execute(task, context=context):
        turns.append(turn)
    return turns


class TestFixedDelegationStubWorker:
    def test_emits_exactly_six_turns(self) -> None:
        from ergon_builtins.workers.stubs.fixed_delegation_stub_worker import (
            FixedDelegationStubWorker,
        )

        worker = FixedDelegationStubWorker()
        turns = asyncio.run(_collect_turns(worker, _task(), _context()))
        assert len(turns) == 6

    def test_turns_zero_through_two_contain_tool_calls(self) -> None:
        from ergon_builtins.workers.stubs.fixed_delegation_stub_worker import (
            FixedDelegationStubWorker,
        )

        worker = FixedDelegationStubWorker()
        turns = asyncio.run(_collect_turns(worker, _task(), _context()))
        for i in range(3):
            assert any(isinstance(p, ToolCallPart) for p in turns[i].response_parts), (
                f"Turn {i} should contain a ToolCallPart"
            )

    def test_turns_one_through_three_contain_tool_returns(self) -> None:
        from ergon_builtins.workers.stubs.fixed_delegation_stub_worker import (
            FixedDelegationStubWorker,
        )

        worker = FixedDelegationStubWorker()
        turns = asyncio.run(_collect_turns(worker, _task(), _context()))
        for i in range(1, 4):
            assert any(isinstance(p, ToolReturnPart) for p in turns[i].messages_in), (
                f"Turn {i} should contain a ToolReturnPart in messages_in"
            )

    def test_final_turn_contains_text_part(self) -> None:
        from ergon_builtins.workers.stubs.fixed_delegation_stub_worker import (
            FixedDelegationStubWorker,
        )

        worker = FixedDelegationStubWorker()
        turns = asyncio.run(_collect_turns(worker, _task(), _context()))
        assert any(isinstance(p, TextPart) for p in turns[-1].response_parts)

    def test_output_is_deterministic(self) -> None:
        """Two executions of the same worker produce identical last-turn text."""
        from ergon_builtins.workers.stubs.fixed_delegation_stub_worker import (
            FixedDelegationStubWorker,
        )

        task = _task("t1")
        turns_a = asyncio.run(_collect_turns(FixedDelegationStubWorker(), task, _context()))
        turns_b = asyncio.run(_collect_turns(FixedDelegationStubWorker(), task, _context()))
        last_a = [p for p in turns_a[-1].response_parts if isinstance(p, TextPart)][0].content
        last_b = [p for p in turns_b[-1].response_parts if isinstance(p, TextPart)][0].content
        assert last_a == last_b

    def test_type_slug(self) -> None:
        from ergon_builtins.workers.stubs.fixed_delegation_stub_worker import (
            FixedDelegationStubWorker,
        )

        assert FixedDelegationStubWorker.type_slug == "fixed-delegation-stub"


class TestFixedLeafStubWorker:
    def test_emits_exactly_one_turn(self) -> None:
        from ergon_builtins.workers.stubs.fixed_leaf_stub_worker import FixedLeafStubWorker

        worker = FixedLeafStubWorker()
        turns = asyncio.run(_collect_turns(worker, _task(), _context()))
        assert len(turns) == 1

    def test_turn_contains_text_part(self) -> None:
        from ergon_builtins.workers.stubs.fixed_leaf_stub_worker import FixedLeafStubWorker

        worker = FixedLeafStubWorker()
        turns = asyncio.run(_collect_turns(worker, _task(), _context()))
        assert any(isinstance(p, TextPart) for p in turns[0].response_parts)

    def test_output_is_deterministic(self) -> None:
        from ergon_builtins.workers.stubs.fixed_leaf_stub_worker import FixedLeafStubWorker

        task = _task("t2")
        turns_a = asyncio.run(_collect_turns(FixedLeafStubWorker(), task, _context()))
        turns_b = asyncio.run(_collect_turns(FixedLeafStubWorker(), task, _context()))
        text_a = [p for p in turns_a[0].response_parts if isinstance(p, TextPart)][0].content
        text_b = [p for p in turns_b[0].response_parts if isinstance(p, TextPart)][0].content
        assert text_a == text_b

    def test_type_slug(self) -> None:
        from ergon_builtins.workers.stubs.fixed_leaf_stub_worker import FixedLeafStubWorker

        assert FixedLeafStubWorker.type_slug == "fixed-leaf-stub"


class TestRegistryEntries:
    def test_both_slugs_in_workers_registry(self) -> None:
        from ergon_builtins.registry_core import WORKERS
        from ergon_builtins.workers.stubs.fixed_delegation_stub_worker import (
            FixedDelegationStubWorker,
        )
        from ergon_builtins.workers.stubs.fixed_leaf_stub_worker import FixedLeafStubWorker

        assert WORKERS["fixed-delegation-stub"] is FixedDelegationStubWorker
        assert WORKERS["fixed-leaf-stub"] is FixedLeafStubWorker
```

### Integration tests (per benchmark smoke)

Pattern described above in "Full implementations". Each smoke file in
`tests/integration/smokes/` follows the four-assertion pattern:
1. CLI exits 0 and prints `Status:     completed`.
2. All `RunTaskExecution` rows are `COMPLETED` in Postgres.
3. At least one `RunTaskEvaluation` row with a non-null score.
4. `GET /api/runs/<id>` returns `{"status": "completed", "tasks": [...]}`.

The Playwright step (assertion 5) is added in PR 3 after the test-harness
endpoints RFC lands.

### Contract test (enforced in PR 2)

`tests/integration/smokes/test_smoke_coverage.py` is the enforcement
mechanism for the new invariant. It parametrizes over every key in
`BENCHMARKS` (core + data-extra) and asserts the matching smoke file exists.
In PR 1 this test is written but does not yet fail — the initially-missing
files are listed with `pytest.xfail` marks. In PR 2, once all nine files
exist, the xfail marks are removed and the test becomes a hard gate.

## Trace / observability impact

No new spans. No new span attributes. Both stub workers emit `GenerationTurn`
objects through the existing persistence path in `worker_execute_fn`
(`ergon_core/ergon_core/core/runtime/inngest/worker_execute.py`), which
already emits a `worker.execute` span with `turn_count` in its attributes.

`FixedDelegationStubWorker` produces `turn_count=6` and `FixedLeafStubWorker`
produces `turn_count=1`. These are observable in the existing telemetry
span without any code change.

The `ToolCallPart` / `ToolReturnPart` pairs in `FixedDelegationStubWorker`
turns propagate through the dashboard emitter's `on_context_event` listener,
which means the dashboard will render tool-call cards for the stub worker.
This is deliberate — it exercises the dashboard rendering path for tool calls
without a live model.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Discovery test runs before all 9 smokes exist | Hard CI failure on PR 1 | Use `pytest.xfail` marks for unwritten slugs in PR 1; remove marks in PR 2 after all 9 files land |
| `FixedDelegationStubWorker` emits `ToolCallPart` with `tool_name="add_subtask"` — evaluators that check tool call names may misfire | False evaluator failures | Smoke evaluators are `StubRubric` / `StubCriterion` only; they do not inspect tool call content. Real evaluators are never used in smokes. |
| Six turns increases DB write volume in smoke CI | Marginal Postgres load increase | Six turns is identical to a real manager worker run. CI database is ephemeral; no production impact. |
| Slug collision with future real `fixed-delegation-stub` worker | Registry overwrite | Slugs are prefixed `fixed-*` to signal fixture use. Architecture doc invariant: `type_slug` MUST NOT change after it has run in a persisted dataset (doc §4). The smoke slug is never used in any persisted dataset outside CI. |
| Deleting ad-hoc stubs in PR 3 breaks code that imports them | ImportError | Audit call sites before PR 3: `grep -r "StubWorker\|SmokeTestWorker\|StubResearchRubricsWorker"` across `tests/` and `ergon_builtins/`. Update imports to new slugs. The `WORKERS` dict entries are kept until all callers migrate. |
| Playwright step depends on an unmerged RFC | Broken step in PR 3 | The Playwright step is guarded by an environment variable `ENABLE_TEST_HARNESS`. If the harness is not running, the step is skipped with a clear message. PR 3 is not merged until the harness RFC has landed. |

## Invariants affected

From `docs/architecture/06_builtins.md`:

- **Existing §4 invariant (strengthen):** "Every benchmark MUST ship a stub worker
  that exercises the graph propagation and eval pipeline without external LLM or
  sandbox dependencies." This RFC makes that invariant machine-enforceable: the
  discovery test fails CI immediately when a benchmark ships without a smoke.
  Architecture doc must be updated on acceptance to note: enforced by
  `tests/integration/smokes/test_smoke_coverage.py`.

- **New §4 invariant (add):** "The canonical stub worker for CI smokes is
  `FixedDelegationStubWorker` (type slug `fixed-delegation-stub`) for
  delegation-style benchmarks and `FixedLeafStubWorker` (type slug
  `fixed-leaf-stub`) for leaf-only benchmarks. Ad-hoc stubs without a smoke test
  are an anti-pattern."

- **Existing §6 anti-pattern (extend):** "Adding a benchmark without a stub worker"
  is already listed. Add: "Adding a benchmark without a matching smoke test at
  `tests/integration/smokes/test_<slug>_smoke.py`." Both conditions are now
  enforced by the same discovery test.

From `docs/architecture/07_testing.md`:

- **New §4 invariant (add):** "Every benchmark must have a smoke at
  `tests/integration/smokes/test_<slug>_smoke.py`. The discovery test
  `test_smoke_coverage.py` enforces this gate in the integration tier."

- **Existing §7 follow-up (close):** "A per-benchmark smoke pattern at
  `tests/integration/smokes/test_<slug>_smoke.py`, using a shared
  fixed-delegation stub worker to exercise a complex-enough subgraph." This RFC
  implements that follow-up; mark closed on acceptance.

## Alternatives considered

- **One stub + per-benchmark parametrize.** Rejected. Different benchmarks need
  different subgraph shapes to exercise their specific wiring (static-DAG benchmarks
  need a leaf pattern; manager-style benchmarks need delegation). A single
  parametrized stub smears that distinction.
- **Keep the three ad-hoc stubs.** Rejected. Nine benchmarks, three stubs,
  inconsistent coverage. Adds a new coverage gap every time a benchmark ships.
- **One smoke per class of benchmark (delegation / static-DAG / eval-only) rather
  than per benchmark.** Rejected. Regressions tend to be benchmark-specific (a
  wiring bug in one benchmark's registry entry is not caught by a smoke on a sibling
  benchmark). Per-benchmark is the level that matches the failure mode.
- **In-memory sandbox fake.** Rejected. Per `docs/architecture/07_testing.md §7`,
  tests that need sandbox behavior use real E2B against a pre-warmed template. A fake
  is an unnecessary maintenance surface. The new stubs avoid the sandbox entirely
  for the benchmarks that don't need one.
- **Extend `StubWorker` with an optional turn-count parameter.** Rejected. Adds
  complexity to a file that already carries a "TEST FIXTURE ONLY" warning. The new
  stubs are clean, standalone, purpose-built; they communicate intent through their
  names and type slugs.

## Open questions

- How does `FixedDelegationStubWorker` interact with benchmarks that have no manager
  (leaf tasks only)? Current answer: `FixedLeafStubWorker` handles static-DAG
  benchmarks. The discovery test accepts either.
- Is the subgraph shape (3 subtasks, fan-out + fan-in across 6 turns) rich enough to
  catch propagation regressions, or do we need a deeper graph? Answer deferred until
  the first regressions are caught; the shape can be extended without breaking the
  turn-count unit test (update the constant in the test).
- Does the Playwright assertion run in the same Python test invocation (via subprocess)
  or in a separate CI job that consumes the BE state via the test-harness API? Probably
  subprocess for atomicity. Decision deferred to the test-harness endpoints RFC.

## On acceptance

When this RFC moves from `active/` to `accepted/`, also:
  - Update `docs/architecture/06_builtins.md` §4 to add the smoke-test invariant and
    mark `FixedDelegationStubWorker` / `FixedLeafStubWorker` as the canonical extension
    point for CI stubs. Add the anti-pattern entry for "benchmark without a smoke file".
  - Update `docs/architecture/07_testing.md` §4 (invariants) to add the per-benchmark
    smoke invariant; close the §7 follow-up for "per-benchmark smoke pattern".
  - Link the rollout plan in
    `docs/superpowers/plans/2026-04-??-fixed-delegation-stub-worker.md`.
