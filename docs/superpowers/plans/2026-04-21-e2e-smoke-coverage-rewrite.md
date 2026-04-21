# E2E Smoke Coverage Rewrite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the retired `tests/e2e/` tier with three canonical per-env smoke tests (researchrubrics, minif2f, swebench-verified) built on a shared multi-agent smoke-worker pattern, plus a backend test-harness router, Playwright frontend assertions, and on-PR inline screenshot delivery.

**Architecture:** Shared `CanonicalSmokeWorker` spawns a hardcoded 9-subtask graph (diamond + line + 2 singletons) via `add_subtask`; per-env `SmokeSubworker` leaves write an env file + run a bash probe; per-env `SmokeCriterion` verifies structure + content. Python pytest drives the CLI + asserts Postgres record-log, invokes Playwright as a subprocess for dashboard assertion. Screenshots upload to orphan `screenshots/pr-{N}` ref; PR comment inlines them on pass AND fail. Parallel CI matrix with 5-min budget per env on every PR.

**Tech Stack:** Python 3.13 (pytest, httpx, sqlmodel, FastAPI), TypeScript (Playwright, Next.js), Docker Compose, GitHub Actions, `gh` CLI, UV workspace, pnpm.

**Canonical references:**
- Spec: `docs/rfcs/active/2026-04-21-e2e-smoke-coverage-rewrite.md`
- Superseded-but-absorbed spec: `docs/rfcs/active/2026-04-18-test-harness-endpoints.md` (full harness router implementation lives here verbatim)
- Parent project RFC (prerequisites): `docs/rfcs/active/2026-04-18-testing-posture-reset.md`

**Prerequisites gating:**
- **PR 1 of this plan** can land any time after the RFC itself is merged. It does not touch `tests/e2e/`.
- **PR 2–4 of this plan** require these reset-RFC PRs to have merged first:
  - Reset RFC PR 2 (Docker layer caching) — required for 5-min CI budget.
  - Reset RFC PR 3 (`tests/integration/` real-Postgres infrastructure) — the pytest driver reuses this stack.
  - Reset RFC PR 4 (`tests/e2e/` deleted) — clean slate.
- If any of those haven't landed when you reach PR 2 of this plan, pause and escalate.

---

## File structure overview

### Python production code (added)

| File | Purpose |
|---|---|
| `ergon_builtins/ergon_builtins/workers/stubs/__init__.py` | Package marker (new subdir) |
| `ergon_builtins/ergon_builtins/workers/stubs/smoke_subworker.py` | `SmokeSubworker` Protocol + `SubworkerResult` dataclass |
| `ergon_builtins/ergon_builtins/workers/stubs/base_smoke_leaf.py` | `BaseSmokeLeafWorker` — shared glue from subworker to resource publish |
| `ergon_builtins/ergon_builtins/workers/stubs/canonical_smoke_worker.py` | `CanonicalSmokeWorker` + `EXPECTED_SUBTASK_KEYS` constant |
| `ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py` | `SmokeCriterionBase` abstract + 3 env-specific subclasses |
| `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/smoke_subworker.py` | `ResearchRubricsSmokeSubworker` + `ResearchRubricsSmokeLeafWorker` |
| `ergon_builtins/ergon_builtins/benchmarks/minif2f/smoke_subworker.py` | `MiniF2FSmokeSubworker` + `MiniF2FSmokeLeafWorker` |
| `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/smoke_subworker.py` | `SweBenchSmokeSubworker` + `SweBenchSmokeLeafWorker` |
| `ergon_core/ergon_core/core/api/test_harness.py` | FastAPI `/api/test/*` router (absorbed from superseded RFC) |

### Python production code (modified)

| File | Change |
|---|---|
| `ergon_builtins/ergon_builtins/registry_core.py` | Register `canonical-smoke`, 3 env leaf workers, 3 env criteria |
| `ergon_cli/ergon_cli/composition/__init__.py` | Add `smoke-leaf` binding for 3 env compositions |
| `ergon_core/ergon_core/core/api/app.py` | Conditional `include_router(test_harness_router)` gated on `ENABLE_TEST_HARNESS=1` |
| `docker-compose.ci.yml` | Add `ENABLE_TEST_HARNESS=1` + `TEST_HARNESS_SECRET=ci-secret` to api env |

### Python tests (added)

| File | Purpose |
|---|---|
| `tests/unit/test_canonical_smoke_worker.py` | Unit: registry entries exist, topology constant correct |
| `tests/unit/test_smoke_criterion.py` | Unit: structural assertions + per-env content assertions against a fake context |
| `tests/unit/test_test_harness.py` | Unit: harness gate on env var, secret header check, schema stability |
| `tests/integration/smokes/test_smoke_harness.py` | Integration: seed → read → reset round-trip against real Postgres |
| `tests/e2e/conftest.py` | Finalizer + `run_benchmark` + `wait_for_terminal` helpers |
| `tests/e2e/test_researchrubrics_smoke.py` | Canonical smoke pytest for researchrubrics |
| `tests/e2e/test_minif2f_smoke.py` | Canonical smoke pytest for minif2f |
| `tests/e2e/test_swebench_verified_smoke.py` | Canonical smoke pytest for swebench-verified |

### TypeScript (added)

| File | Purpose |
|---|---|
| `ergon-dashboard/tests/helpers/testHarnessClient.ts` | `BackendHarnessClient` class (distinct from existing `harnessClient.ts`) |
| `ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts` | Playwright spec for researchrubrics |
| `ergon-dashboard/tests/e2e/minif2f.smoke.spec.ts` | Playwright spec for minif2f |
| `ergon-dashboard/tests/e2e/swebench-verified.smoke.spec.ts` | Playwright spec for swebench-verified |

### TypeScript (modified)

| File | Change |
|---|---|
| `ergon-dashboard/playwright.config.ts` | `screenshot: "only-on-failure"` → `"on"` |

### CI (added)

| File | Purpose |
|---|---|
| `.github/workflows/e2e-benchmarks.yml` | Parallel per-env matrix with 5-min budget + screenshot-ref cleanup |

### Docs (modified on PR 4)

| File | Change |
|---|---|
| `docs/architecture/06_builtins.md` | Rewrite §4 invariant for `SmokeSubworker`/`SmokeCriterion` contract |
| `docs/architecture/07_testing.md` | Update §2 code map + §3 trigger policy + §4 new invariant |
| `docs/architecture/05_dashboard.md` | Add canonical-smoke invariant |
| `docs/architecture/01_public_api.md` | Add "Test-only extension points" section |

### RFC moves

| On PR | From | To |
|---|---|---|
| PR 1 merge | `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md` | `docs/rfcs/rejected/` |
| PR 1 merge | `docs/rfcs/active/2026-04-18-test-harness-endpoints.md` | `docs/rfcs/rejected/` |
| PR 4 merge | `docs/rfcs/active/2026-04-21-e2e-smoke-coverage-rewrite.md` | `docs/rfcs/accepted/` |

---

## Task 0 — Confirm prerequisites and set up PR 1 branch

**Files:** none (environment check).

- [ ] **Step 0.1: Verify workspace builds cleanly**

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
uv sync --all-packages --group dev
pnpm install --frozen-lockfile
pnpm run check:fast
```

Expected: all checks pass. If they don't, stop — the baseline must be green before starting.

- [ ] **Step 0.2: Verify the RFC is merged on main**

```bash
git fetch origin main
git log --oneline origin/main -3 | grep -F "e2e smoke coverage rewrite"
```

Expected: the RFC commit (`d256059` or its equivalent) is visible on `origin/main`.

- [ ] **Step 0.3: Create PR 1 feature branch**

```bash
git checkout main
git pull origin main
git checkout -b feature/smoke-shared-infra
```

Expected: on `feature/smoke-shared-infra`, clean working tree.

---

# PR 1 — Shared smoke worker infrastructure + `/api/test/*` harness + close superseded RFCs

**PR branch:** `feature/smoke-shared-infra`

**Goal:** All reusable infrastructure lands, no env-specific smoke wiring yet, no CI workflow. End state: `CanonicalSmokeWorker`, `BaseSmokeLeafWorker`, `SmokeSubworker` Protocol, `SmokeCriterionBase`, and `/api/test/*` router are all registered, unit-tested, and importable. Two superseded RFCs are moved to `rejected/`.

**PR 1 acceptance gate:** `pnpm run check:fast` + all unit tests + one integration test for the harness pass; superseded RFCs are in `rejected/` with `superseded_by` frontmatter set; `/api/test/read/run/{id}/state` returns a 404 when `ENABLE_TEST_HARNESS` is unset and a valid DTO (or 404-by-run-id) when set.

---

## Task 1 — `SmokeSubworker` Protocol + `SubworkerResult` dataclass

**Files:**
- Create: `ergon_builtins/ergon_builtins/workers/stubs/__init__.py`
- Create: `ergon_builtins/ergon_builtins/workers/stubs/smoke_subworker.py`
- Test: `tests/unit/test_smoke_subworker_protocol.py`

- [ ] **Step 1.1: Write the failing test for Protocol conformance**

```python
# tests/unit/test_smoke_subworker_protocol.py
"""Contract test: anything claiming to be a SmokeSubworker must pass runtime_checkable."""

from ergon_builtins.workers.stubs.smoke_subworker import (
    SmokeSubworker,
    SubworkerResult,
)


def test_subworker_result_is_frozen() -> None:
    r = SubworkerResult(file_path="/tmp/x", probe_stdout="1\n", probe_exit_code=0)
    try:
        r.file_path = "/tmp/y"  # type: ignore[misc]
    except Exception as e:
        assert isinstance(e, Exception)
    else:
        raise AssertionError("SubworkerResult must be frozen")


def test_minimal_async_class_satisfies_protocol() -> None:
    class OK:
        async def work(self, node_id: str, sandbox):  # noqa: ANN001
            return SubworkerResult("/tmp/x", "out", 0)

    assert isinstance(OK(), SmokeSubworker)


def test_missing_work_method_fails_protocol_check() -> None:
    class Bad:
        pass

    assert not isinstance(Bad(), SmokeSubworker)
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_smoke_subworker_protocol.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'ergon_builtins.workers.stubs'`.

- [ ] **Step 1.3: Create package marker**

```python
# ergon_builtins/ergon_builtins/workers/stubs/__init__.py
"""Canonical smoke worker infrastructure shared across environments."""
```

- [ ] **Step 1.4: Write the Protocol + dataclass**

```python
# ergon_builtins/ergon_builtins/workers/stubs/smoke_subworker.py
"""Env-agnostic leaf worker Protocol for canonical smoke runs.

The parent CanonicalSmokeWorker spawns 9 subtasks via add_subtask; each subtask
resolves to a leaf worker via the composition binding `smoke-leaf`. That leaf
worker wraps a SmokeSubworker instance (one concrete class per env) whose sole
job is to prove the sandbox is correctly set up for that environment:

  1. Write a deterministic, well-known file into the sandbox.
  2. Run a bash probe against it (compile / parse / count lines / etc.).
  3. Return both so the criterion can assert on them.

MUST NOT call an LLM. MUST NOT make network calls. MUST complete in under 20s
under normal sandbox conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ergon_core.core.providers.sandbox.manager import AsyncSandbox


@dataclass(frozen=True)
class SubworkerResult:
    """Return payload from one SmokeSubworker.work() call."""

    file_path: str
    probe_stdout: str
    probe_exit_code: int


@runtime_checkable
class SmokeSubworker(Protocol):
    """The pluggable env-specific leaf."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        ...
```

- [ ] **Step 1.5: Run tests to verify pass**

```bash
uv run pytest tests/unit/test_smoke_subworker_protocol.py -v
```

Expected: PASS 3/3.

- [ ] **Step 1.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/workers/stubs/__init__.py \
        ergon_builtins/ergon_builtins/workers/stubs/smoke_subworker.py \
        tests/unit/test_smoke_subworker_protocol.py
git commit -m "feat(smoke): SmokeSubworker Protocol + SubworkerResult"
```

---

## Task 2 — `BaseSmokeLeafWorker` (shared glue)

**Files:**
- Create: `ergon_builtins/ergon_builtins/workers/stubs/base_smoke_leaf.py`
- Test: `tests/unit/test_base_smoke_leaf.py`

- [ ] **Step 2.1: Write failing test with a fake subworker**

```python
# tests/unit/test_base_smoke_leaf.py
"""BaseSmokeLeafWorker: delegates to subworker_cls, publishes resource, returns WorkerResult."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ergon_builtins.workers.stubs.base_smoke_leaf import BaseSmokeLeafWorker
from ergon_builtins.workers.stubs.smoke_subworker import SubworkerResult


class _FakeSubworker:
    async def work(self, node_id, sandbox):  # noqa: ANN001
        return SubworkerResult(
            file_path=f"/tmp/{node_id}.txt",
            probe_stdout="ok\n",
            probe_exit_code=0,
        )


class _LeafForTest(BaseSmokeLeafWorker):
    subworker_cls = _FakeSubworker  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_leaf_publishes_resource_and_returns_success() -> None:
    sandbox = MagicMock()
    ctx = SimpleNamespace(
        task_key="d_root",
        acquire_sandbox=AsyncMock(return_value=sandbox),
        publish_resource=AsyncMock(),
    )

    leaf = _LeafForTest()
    result = await leaf.execute(ctx)

    assert result.success is True
    ctx.publish_resource.assert_awaited_once()
    kwargs = ctx.publish_resource.await_args.kwargs
    assert kwargs["path"] == "/tmp/d_root.txt"
    assert kwargs["metadata"]["probe_exit_code"] == 0


@pytest.mark.asyncio
async def test_leaf_returns_failure_when_probe_nonzero() -> None:
    class _FailSubworker:
        async def work(self, node_id, sandbox):  # noqa: ANN001
            return SubworkerResult("/tmp/x", "err", 1)

    class _FailLeaf(BaseSmokeLeafWorker):
        subworker_cls = _FailSubworker  # type: ignore[assignment]

    ctx = SimpleNamespace(
        task_key="l_1",
        acquire_sandbox=AsyncMock(return_value=MagicMock()),
        publish_resource=AsyncMock(),
    )
    result = await _FailLeaf().execute(ctx)
    assert result.success is False
```

- [ ] **Step 2.2: Run — expect module-missing**

```bash
uv run pytest tests/unit/test_base_smoke_leaf.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 2.3: Implement `BaseSmokeLeafWorker`**

```python
# ergon_builtins/ergon_builtins/workers/stubs/base_smoke_leaf.py
"""Shared glue between any SmokeSubworker and the resource-publish pipeline."""

from __future__ import annotations

from typing import ClassVar

from ergon_core.api import Worker, WorkerContext, WorkerResult
from ergon_core.core.persistence.telemetry.models import RunResourceKind

from ergon_builtins.workers.stubs.smoke_subworker import SmokeSubworker


class BaseSmokeLeafWorker(Worker):
    """Subclasses set `subworker_cls: type[SmokeSubworker]`.

    Runtime flow:
      1. Acquire sandbox from ctx.
      2. Instantiate subworker_cls, call .work().
      3. Publish a RunResource with the file + probe stdout/exit-code as metadata.
      4. Return WorkerResult(success=(exit_code == 0)).

    The subworker is constructed per-execute so it can hold per-call state if needed.
    """

    subworker_cls: ClassVar[type[SmokeSubworker]]

    async def execute(self, ctx: WorkerContext) -> WorkerResult:
        sandbox = await ctx.acquire_sandbox()
        subworker = self.subworker_cls()
        result = await subworker.work(node_id=ctx.task_key, sandbox=sandbox)

        await ctx.publish_resource(
            kind=RunResourceKind.ARTIFACT,
            path=result.file_path,
            metadata={
                "probe_stdout": result.probe_stdout,
                "probe_exit_code": result.probe_exit_code,
            },
        )
        return WorkerResult(success=result.probe_exit_code == 0)
```

- [ ] **Step 2.4: Confirm `Worker`, `WorkerContext`, `WorkerResult`, `RunResourceKind` import paths exist**

```bash
uv run python -c "from ergon_core.api import Worker, WorkerContext, WorkerResult; from ergon_core.core.persistence.telemetry.models import RunResourceKind; print('ok')"
```

Expected: `ok`. If any import fails, search `ergon_core/` for the correct module path and adjust.

- [ ] **Step 2.5: Run tests**

```bash
uv run pytest tests/unit/test_base_smoke_leaf.py -v
```

Expected: PASS 2/2.

- [ ] **Step 2.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/workers/stubs/base_smoke_leaf.py \
        tests/unit/test_base_smoke_leaf.py
git commit -m "feat(smoke): BaseSmokeLeafWorker publishes resource + returns success"
```

---

## Task 3 — `CanonicalSmokeWorker` + `EXPECTED_SUBTASK_KEYS`

**Files:**
- Create: `ergon_builtins/ergon_builtins/workers/stubs/canonical_smoke_worker.py`
- Test: `tests/unit/test_canonical_smoke_worker.py`

- [ ] **Step 3.1: Write failing test for topology**

```python
# tests/unit/test_canonical_smoke_worker.py
"""CanonicalSmokeWorker: declares hardcoded 9-subtask topology via add_subtask."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ergon_builtins.workers.stubs.canonical_smoke_worker import (
    EXPECTED_SUBTASK_KEYS,
    CanonicalSmokeWorker,
)


def test_expected_keys_constant_shape() -> None:
    assert EXPECTED_SUBTASK_KEYS == (
        "d_root", "d_left", "d_right", "d_join",
        "l_1", "l_2", "l_3",
        "s_a", "s_b",
    )
    assert len(EXPECTED_SUBTASK_KEYS) == 9
    assert len(set(EXPECTED_SUBTASK_KEYS)) == 9


@pytest.mark.asyncio
async def test_execute_calls_add_subtask_nine_times_with_correct_deps() -> None:
    issued_ids: list[str] = []
    calls: list[dict] = []

    async def fake_add_subtask(**kwargs):
        handle_id = f"handle-{kwargs['task_key']}"
        issued_ids.append(handle_id)
        calls.append(kwargs)
        return handle_id

    completed_results = [
        SimpleNamespace(task_key=k, status="completed") for k in EXPECTED_SUBTASK_KEYS
    ]

    ctx = SimpleNamespace(
        add_subtask=fake_add_subtask,
        wait_all=AsyncMock(return_value=completed_results),
        emit_turn=AsyncMock(),
    )

    result = await CanonicalSmokeWorker().execute(ctx)

    assert len(calls) == 9
    by_key = {c["task_key"]: c for c in calls}
    assert by_key["d_root"]["depends_on"] == []
    assert by_key["d_left"]["depends_on"] == ["handle-d_root"]
    assert by_key["d_right"]["depends_on"] == ["handle-d_root"]
    assert sorted(by_key["d_join"]["depends_on"]) == [
        "handle-d_left", "handle-d_right",
    ]
    assert by_key["l_1"]["depends_on"] == []
    assert by_key["l_2"]["depends_on"] == ["handle-l_1"]
    assert by_key["l_3"]["depends_on"] == ["handle-l_2"]
    assert by_key["s_a"]["depends_on"] == []
    assert by_key["s_b"]["depends_on"] == []
    for c in calls:
        assert c["worker"] == "smoke-leaf"
    assert result.success is True
```

- [ ] **Step 3.2: Run — expect module-missing**

```bash
uv run pytest tests/unit/test_canonical_smoke_worker.py -v
```

Expected: FAIL with import error.

- [ ] **Step 3.3: Implement the worker**

```python
# ergon_builtins/ergon_builtins/workers/stubs/canonical_smoke_worker.py
"""Canonical smoke parent worker.

Always spawns the same 9-subtask graph regardless of env:

    Diamond (4):           Line (3):           Singletons (2):
          d_root           l_1 → l_2 → l_3          s_a    s_b
          /     \
      d_left   d_right
          \     /
          d_join

Determinism is the point: a graph regression either surfaces identically in
every env's smoke, or doesn't exist. Subtask work is env-specific via the
composition binding `smoke-leaf`.
"""

from __future__ import annotations

from ergon_core.api import Worker, WorkerContext, WorkerResult
from ergon_core.core.persistence.shared.enums import TaskStatus

EXPECTED_SUBTASK_KEYS: tuple[str, ...] = (
    "d_root", "d_left", "d_right", "d_join",
    "l_1", "l_2", "l_3",
    "s_a", "s_b",
)


class CanonicalSmokeWorker(Worker):
    """Shared parent for every env's canonical smoke."""

    async def execute(self, ctx: WorkerContext) -> WorkerResult:
        d_root = await ctx.add_subtask(
            task_key="d_root", worker="smoke-leaf", depends_on=[],
        )
        d_left = await ctx.add_subtask(
            task_key="d_left", worker="smoke-leaf", depends_on=[d_root],
        )
        d_right = await ctx.add_subtask(
            task_key="d_right", worker="smoke-leaf", depends_on=[d_root],
        )
        d_join = await ctx.add_subtask(
            task_key="d_join", worker="smoke-leaf", depends_on=[d_left, d_right],
        )

        l_1 = await ctx.add_subtask(
            task_key="l_1", worker="smoke-leaf", depends_on=[],
        )
        l_2 = await ctx.add_subtask(
            task_key="l_2", worker="smoke-leaf", depends_on=[l_1],
        )
        l_3 = await ctx.add_subtask(
            task_key="l_3", worker="smoke-leaf", depends_on=[l_2],
        )

        s_a = await ctx.add_subtask(
            task_key="s_a", worker="smoke-leaf", depends_on=[],
        )
        s_b = await ctx.add_subtask(
            task_key="s_b", worker="smoke-leaf", depends_on=[],
        )

        results = await ctx.wait_all(
            [d_root, d_left, d_right, d_join, l_1, l_2, l_3, s_a, s_b]
        )

        summary = "\n".join(f"{r.task_key}: {r.status}" for r in results)
        await ctx.emit_turn(text=summary)

        all_completed = all(
            getattr(r.status, "name", r.status) in ("COMPLETED", "completed")
            or r.status == TaskStatus.COMPLETED
            for r in results
        )
        return WorkerResult(success=all_completed)
```

- [ ] **Step 3.4: Run tests**

```bash
uv run pytest tests/unit/test_canonical_smoke_worker.py -v
```

Expected: PASS 2/2.

- [ ] **Step 3.5: Commit**

```bash
git add ergon_builtins/ergon_builtins/workers/stubs/canonical_smoke_worker.py \
        tests/unit/test_canonical_smoke_worker.py
git commit -m "feat(smoke): CanonicalSmokeWorker with hardcoded 9-node diamond+line+singletons topology"
```

---

## Task 4 — `SmokeCriterionBase` abstract + 3 env subclasses (skeletons only)

This task lands the abstract + stub subclasses; per-env content assertions land in PRs 2–4 alongside their env subworkers. Leaving the subclass bodies as `raise NotImplementedError` keeps wiring visible now without committing to env-specific content assertions before the env subworker exists.

**Files:**
- Create: `ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py`
- Test: `tests/unit/test_smoke_criterion.py`

- [ ] **Step 4.1: Write failing test for structural assertions**

```python
# tests/unit/test_smoke_criterion.py
"""SmokeCriterionBase: shared structural asserts; subclass fills env content assert."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from ergon_builtins.evaluators.criteria.smoke_criterion import (
    SmokeCriterionBase,
)
from ergon_builtins.workers.stubs.canonical_smoke_worker import EXPECTED_SUBTASK_KEYS


@dataclass
class _FakeResource:
    task_key: str
    id: str
    content_hash: str
    metadata: dict
    content: bytes = b""


class _PassthroughCriterion(SmokeCriterionBase):
    async def _verify_env_content(self, ctx) -> None:  # noqa: ANN001
        return


def _ctx_with_full_graph_and_resources() -> SimpleNamespace:
    nodes = [SimpleNamespace(task_key="ROOT", level=0)]
    nodes += [
        SimpleNamespace(task_key=k, level=1) for k in EXPECTED_SUBTASK_KEYS
    ]
    resources = [
        _FakeResource(
            task_key=k, id=f"r-{k}", content_hash="h",
            metadata={"probe_exit_code": 0, "probe_stdout": "ok\n"},
        )
        for k in EXPECTED_SUBTASK_KEYS
    ]
    return SimpleNamespace(
        graph_nodes=nodes,
        resources=SimpleNamespace(all=lambda: resources),
    )


@pytest.mark.asyncio
async def test_criterion_passes_with_canonical_graph_and_resources() -> None:
    score = await _PassthroughCriterion().evaluate(_ctx_with_full_graph_and_resources())
    assert score.value == 1.0


@pytest.mark.asyncio
async def test_criterion_fails_when_graph_shape_differs() -> None:
    ctx = _ctx_with_full_graph_and_resources()
    ctx.graph_nodes = ctx.graph_nodes[:-1]  # drop s_b
    score = await _PassthroughCriterion().evaluate(ctx)
    assert score.value == 0.0
    assert "graph shape" in score.reason.lower()


@pytest.mark.asyncio
async def test_criterion_fails_when_resource_count_wrong() -> None:
    ctx = _ctx_with_full_graph_and_resources()
    ctx.resources = SimpleNamespace(all=lambda: list(ctx.resources.all())[:-1])
    score = await _PassthroughCriterion().evaluate(ctx)
    assert score.value == 0.0
    assert "9 resources" in score.reason


@pytest.mark.asyncio
async def test_criterion_fails_when_probe_nonzero() -> None:
    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    resources[0].metadata["probe_exit_code"] = 1
    ctx.resources = SimpleNamespace(all=lambda: resources)
    score = await _PassthroughCriterion().evaluate(ctx)
    assert score.value == 0.0
    assert "probe" in score.reason.lower()


@pytest.mark.asyncio
async def test_verify_env_content_is_abstract() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        SmokeCriterionBase as Base,
    )

    class Subclass(Base):
        pass

    with pytest.raises(NotImplementedError):
        await Subclass()._verify_env_content(SimpleNamespace())
```

- [ ] **Step 4.2: Run — expect module-missing**

```bash
uv run pytest tests/unit/test_smoke_criterion.py -v
```

Expected: FAIL with import error.

- [ ] **Step 4.3: Implement the abstract base + env subclasses**

```python
# ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py
"""Shared smoke criterion: structural + probe checks; env subclass adds content."""

from __future__ import annotations

from ergon_core.api import Criterion, CriterionContext, Score

from ergon_builtins.workers.stubs.canonical_smoke_worker import EXPECTED_SUBTASK_KEYS


class SmokeCriterionBase(Criterion):
    async def evaluate(self, ctx: CriterionContext) -> Score:
        try:
            self._assert_graph_shape(ctx)
            self._assert_resources_present(ctx)
            self._assert_probes_succeeded(ctx)
            await self._verify_env_content(ctx)
        except AssertionError as e:
            return Score(value=0.0, reason=f"smoke criterion failed: {e}")
        return Score(value=1.0, reason="canonical smoke passed")

    def _assert_graph_shape(self, ctx: CriterionContext) -> None:
        actual = {n.task_key for n in ctx.graph_nodes if n.level > 0}
        expected = set(EXPECTED_SUBTASK_KEYS)
        assert actual == expected, (
            f"graph shape mismatch: actual={sorted(actual)} expected={sorted(expected)}"
        )

    def _assert_resources_present(self, ctx: CriterionContext) -> None:
        resources = list(ctx.resources.all())
        assert len(resources) == 9, f"expected 9 resources, got {len(resources)}"
        for r in resources:
            assert r.content_hash, f"resource {r.id} has empty content hash"

    def _assert_probes_succeeded(self, ctx: CriterionContext) -> None:
        for r in ctx.resources.all():
            exit_code = r.metadata.get("probe_exit_code")
            assert exit_code == 0, (
                f"probe for {r.task_key} exited {exit_code}, stdout={r.metadata.get('probe_stdout', '')!r}"
            )

    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        raise NotImplementedError(
            "Subclasses must implement env-specific content verification"
        )


class ResearchRubricsSmokeCriterion(SmokeCriterionBase):
    """Populated in PR 2 when the researchrubrics subworker lands."""

    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        raise NotImplementedError("populated in PR 2")


class MiniF2FSmokeCriterion(SmokeCriterionBase):
    """Populated in PR 3."""

    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        raise NotImplementedError("populated in PR 3")


class SweBenchSmokeCriterion(SmokeCriterionBase):
    """Populated in PR 4."""

    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        raise NotImplementedError("populated in PR 4")
```

- [ ] **Step 4.4: Confirm `Criterion`, `CriterionContext`, `Score` import path**

```bash
uv run python -c "from ergon_core.api import Criterion, CriterionContext, Score; print('ok')"
```

Expected: `ok`. If not, grep `ergon_core/` for the correct re-export path and adjust.

- [ ] **Step 4.5: Run tests**

```bash
uv run pytest tests/unit/test_smoke_criterion.py -v
```

Expected: PASS 5/5.

- [ ] **Step 4.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py \
        tests/unit/test_smoke_criterion.py
git commit -m "feat(smoke): SmokeCriterionBase with structural + probe checks; 3 env subclass stubs"
```

---

## Task 5 — Register shared infra in `registry_core.py`

**Files:**
- Modify: `ergon_builtins/ergon_builtins/registry_core.py`
- Test: `tests/unit/test_registry_core_smoke_entries.py`

- [ ] **Step 5.1: Write failing test**

```python
# tests/unit/test_registry_core_smoke_entries.py
"""Registry includes the shared canonical-smoke entries after PR 1."""

from ergon_builtins.registry_core import EVALUATORS, WORKERS


def test_canonical_smoke_worker_registered() -> None:
    from ergon_builtins.workers.stubs.canonical_smoke_worker import (
        CanonicalSmokeWorker,
    )

    assert WORKERS["canonical-smoke"] is CanonicalSmokeWorker


def test_env_smoke_criteria_registered() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        MiniF2FSmokeCriterion,
        ResearchRubricsSmokeCriterion,
        SweBenchSmokeCriterion,
    )

    assert EVALUATORS["researchrubrics-smoke-rubric"] is ResearchRubricsSmokeCriterion
    assert EVALUATORS["minif2f-smoke-rubric"] is MiniF2FSmokeCriterion
    assert EVALUATORS["swebench-smoke-rubric"] is SweBenchSmokeCriterion
```

- [ ] **Step 5.2: Run — expect KeyError**

```bash
uv run pytest tests/unit/test_registry_core_smoke_entries.py -v
```

Expected: FAIL with `KeyError: 'canonical-smoke'`.

- [ ] **Step 5.3: Wire registry entries**

Add these imports at the top of `ergon_builtins/ergon_builtins/registry_core.py`, grouped with the existing evaluator / worker imports:

```python
from ergon_builtins.evaluators.criteria.smoke_criterion import (
    MiniF2FSmokeCriterion,
    ResearchRubricsSmokeCriterion,
    SweBenchSmokeCriterion,
)
from ergon_builtins.workers.stubs.canonical_smoke_worker import CanonicalSmokeWorker
```

Add these entries to the existing dicts (insert before the closing `}`):

```python
# In WORKERS
    "canonical-smoke": CanonicalSmokeWorker,
```

```python
# In EVALUATORS
    "researchrubrics-smoke-rubric": ResearchRubricsSmokeCriterion,
    "minif2f-smoke-rubric": MiniF2FSmokeCriterion,
    "swebench-smoke-rubric": SweBenchSmokeCriterion,
```

Do **not** add leaf-worker entries yet; those land per-env in PRs 2–4.

- [ ] **Step 5.4: Run tests**

```bash
uv run pytest tests/unit/test_registry_core_smoke_entries.py -v
```

Expected: PASS 2/2.

- [ ] **Step 5.5: Run existing contract test to confirm no regression**

```bash
uv run pytest tests/unit/test_benchmark_contract.py -v 2>/dev/null || echo "(contract test doesn't exist yet — fine)"
```

Expected: green or "doesn't exist" (the contract test lands in the testing-posture-reset RFC's PR 1).

- [ ] **Step 5.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/registry_core.py \
        tests/unit/test_registry_core_smoke_entries.py
git commit -m "feat(smoke): register canonical-smoke worker + 3 env smoke-criterion entries"
```

---

## Task 6 — `/api/test/*` harness router: state DTO + read endpoint

This task and Task 7 implement the router described in detail in `docs/rfcs/active/2026-04-18-test-harness-endpoints.md` §4–5 (absorbed verbatim into this RFC). If any ambiguity arises, defer to the superseded RFC's implementation spec — it is more detailed than the summary in the new RFC.

**Files:**
- Create: `ergon_core/ergon_core/core/api/test_harness.py`
- Test: `tests/unit/test_test_harness.py`

- [ ] **Step 6.1: Write failing test for read-endpoint schema**

```python
# tests/unit/test_test_harness.py
"""Test-harness router: conditional mount, read DTO shape, write-gate secret."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app_with_harness(*, enabled: bool, secret: str | None = "ci-secret") -> FastAPI:
    app = FastAPI()
    prev_enable = os.environ.get("ENABLE_TEST_HARNESS")
    prev_secret = os.environ.get("TEST_HARNESS_SECRET")
    try:
        os.environ["ENABLE_TEST_HARNESS"] = "1" if enabled else "0"
        if secret is not None:
            os.environ["TEST_HARNESS_SECRET"] = secret
        else:
            os.environ.pop("TEST_HARNESS_SECRET", None)

        if enabled:
            from ergon_core.core.api.test_harness import router
            app.include_router(router)
    finally:
        if prev_enable is None:
            os.environ.pop("ENABLE_TEST_HARNESS", None)
        else:
            os.environ["ENABLE_TEST_HARNESS"] = prev_enable
        if prev_secret is None:
            os.environ.pop("TEST_HARNESS_SECRET", None)
        else:
            os.environ["TEST_HARNESS_SECRET"] = prev_secret
    return app


def test_read_endpoint_returns_404_for_unknown_run_id() -> None:
    app = _build_app_with_harness(enabled=True)
    client = TestClient(app)
    resp = client.get(f"/api/test/read/run/{uuid4()}/state")
    assert resp.status_code == 404


def test_read_endpoint_unmounted_when_disabled() -> None:
    app = _build_app_with_harness(enabled=False)
    client = TestClient(app)
    resp = client.get(f"/api/test/read/run/{uuid4()}/state")
    assert resp.status_code == 404  # unmounted = route doesn't exist
```

- [ ] **Step 6.2: Run — expect module-missing**

```bash
uv run pytest tests/unit/test_test_harness.py -v
```

Expected: FAIL with import error.

- [ ] **Step 6.3: Implement the router with read endpoint only (write endpoints land in Task 7)**

```python
# ergon_core/ergon_core/core/api/test_harness.py
"""Test-only FastAPI router exposing narrow DTOs for Playwright/backend tests.

Gates:
  - Router is only mounted when ENABLE_TEST_HARNESS=1 (caller-side in app.py).
  - Write endpoints additionally require the `X-Test-Secret` header to match
    TEST_HARNESS_SECRET. Absence of the env var = 500 (distinct from 401 bad
    secret) so misconfiguration is distinguishable from auth failure.

Wire-shape stability: these DTOs are used by Playwright. Additive-only schema —
never remove or rename a field without coordinating a TS helper update.
"""

from __future__ import annotations

import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
)

router = APIRouter(prefix="/api/test", tags=["test-harness"])


class TestGraphNodeDto(BaseModel):
    task_key: str
    level: int
    status: str
    parent_task_key: str | None


class TestEvaluationDto(BaseModel):
    score: float
    reason: str


class TestGraphMutationDto(BaseModel):
    sequence: int
    mutation_type: str
    target_task_key: str | None


class TestRunStateDto(BaseModel):
    run_id: UUID
    status: str
    graph_nodes: list[TestGraphNodeDto]
    mutations: list[TestGraphMutationDto]
    evaluations: list[TestEvaluationDto]
    resource_count: int


def _require_secret(
    x_test_secret: Annotated[str | None, Header(alias="X-Test-Secret")],
) -> None:
    configured = os.environ.get("TEST_HARNESS_SECRET")
    if configured is None:
        # Distinguishable from 401: the server is misconfigured.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TEST_HARNESS_SECRET not configured",
        )
    if x_test_secret != configured:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


@router.get("/read/run/{run_id}/state", response_model=TestRunStateDto)
def read_run_state(run_id: UUID) -> TestRunStateDto:
    with Session(get_engine()) as s:
        run = s.exec(select(RunRecord).where(RunRecord.id == run_id)).first()
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")

        nodes = s.exec(
            select(RunGraphNode).where(RunGraphNode.run_id == run_id)
        ).all()
        node_by_id = {n.id: n for n in nodes}
        node_dtos = [
            TestGraphNodeDto(
                task_key=n.task_key,
                level=n.level,
                status=getattr(n.status, "value", str(n.status)),
                parent_task_key=(
                    node_by_id[n.parent_id].task_key
                    if getattr(n, "parent_id", None) and n.parent_id in node_by_id
                    else None
                ),
            )
            for n in nodes
        ]

        muts = s.exec(
            select(RunGraphMutation)
            .where(RunGraphMutation.run_id == run_id)
            .order_by(RunGraphMutation.sequence)
        ).all()
        mut_dtos = [
            TestGraphMutationDto(
                sequence=m.sequence,
                mutation_type=str(m.mutation_type),
                target_task_key=(
                    node_by_id[m.target_id].task_key
                    if getattr(m, "target_id", None) and m.target_id in node_by_id
                    else None
                ),
            )
            for m in muts
        ]

        evals = s.exec(
            select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
        ).all()
        eval_dtos = [
            TestEvaluationDto(score=float(e.score), reason=e.reason or "")
            for e in evals
        ]

        resource_count = s.exec(
            select(RunResource).where(RunResource.run_id == run_id)
        ).all()

        return TestRunStateDto(
            run_id=run_id,
            status=getattr(run.status, "value", str(run.status)),
            graph_nodes=node_dtos,
            mutations=mut_dtos,
            evaluations=eval_dtos,
            resource_count=len(resource_count),
        )
```

Note: if field names on `RunRecord`/`RunGraphNode`/`RunGraphMutation`/`RunTaskEvaluation`/`RunResource` differ from those used above (e.g. `status`, `parent_id`, `run_id`, `target_id`, `sequence`, `score`), adjust the field access. The list above is the RFC's declared contract — the model definitions live under `ergon_core/core/persistence/`. Grep before guessing:

```bash
uv run python -c "from ergon_core.core.persistence.graph.models import RunGraphNode; print([f for f in RunGraphNode.__fields__])"
uv run python -c "from ergon_core.core.persistence.graph.models import RunGraphMutation; print([f for f in RunGraphMutation.__fields__])"
uv run python -c "from ergon_core.core.persistence.telemetry.models import RunRecord, RunResource, RunTaskEvaluation; print([f for f in RunRecord.__fields__], [f for f in RunResource.__fields__], [f for f in RunTaskEvaluation.__fields__])"
```

- [ ] **Step 6.4: Run tests**

```bash
uv run pytest tests/unit/test_test_harness.py -v
```

Expected: PASS 2/2.

- [ ] **Step 6.5: Commit**

```bash
git add ergon_core/ergon_core/core/api/test_harness.py \
        tests/unit/test_test_harness.py
git commit -m "feat(harness): /api/test/read/run/{id}/state router with TestRunStateDto"
```

---

## Task 7 — `/api/test/*` write endpoints (seed + reset) with secret gating

**Files:**
- Modify: `ergon_core/ergon_core/core/api/test_harness.py`
- Modify: `tests/unit/test_test_harness.py`

- [ ] **Step 7.1: Extend tests for the write endpoints**

Append to `tests/unit/test_test_harness.py`:

```python
def test_seed_requires_secret_header() -> None:
    app = _build_app_with_harness(enabled=True, secret="ci-secret")
    client = TestClient(app)
    resp = client.post("/api/test/write/run/seed", json={})
    assert resp.status_code == 401


def test_seed_returns_500_when_secret_env_missing() -> None:
    app = _build_app_with_harness(enabled=True, secret=None)
    client = TestClient(app)
    resp = client.post(
        "/api/test/write/run/seed",
        json={},
        headers={"X-Test-Secret": "anything"},
    )
    assert resp.status_code == 500


def test_reset_requires_secret_header() -> None:
    app = _build_app_with_harness(enabled=True, secret="ci-secret")
    client = TestClient(app)
    resp = client.post("/api/test/write/reset", json={})
    assert resp.status_code == 401
```

- [ ] **Step 7.2: Run — expect missing routes**

```bash
uv run pytest tests/unit/test_test_harness.py -v
```

Expected: FAIL 3 new tests (404 instead of 401/500).

- [ ] **Step 7.3: Extend the router with write endpoints**

Append to `ergon_core/ergon_core/core/api/test_harness.py`:

```python
class SeedRunRequest(BaseModel):
    cohort: str
    status: str = "completed"
    task_keys: list[str] = []


class ResetRequest(BaseModel):
    cohort_prefix: str = "ci-smoke-"


@router.post("/write/run/seed", status_code=201)
def seed_run(
    body: SeedRunRequest,
    x_test_secret: Annotated[str | None, Header(alias="X-Test-Secret")] = None,
) -> dict:
    _require_secret(x_test_secret)
    with Session(get_engine()) as s:
        run = RunRecord(
            cohort=body.cohort,
            status=body.status,
            metadata={"_test_seeded": True},
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
        stale = s.exec(
            select(RunRecord).where(RunRecord.cohort.startswith(body.cohort_prefix))
        ).all()
        for r in stale:
            if (r.metadata or {}).get("_test_seeded"):
                s.delete(r)
        s.commit()
    return None
```

If `RunRecord` does not support `metadata` as a free-form dict, introspect with:

```bash
uv run python -c "from ergon_core.core.persistence.telemetry.models import RunRecord; print([f for f in RunRecord.__fields__])"
```

…and adjust the seed/reset discriminator (e.g. prefix the cohort with `_test_` and filter by cohort instead).

- [ ] **Step 7.4: Run tests**

```bash
uv run pytest tests/unit/test_test_harness.py -v
```

Expected: PASS 5/5.

- [ ] **Step 7.5: Commit**

```bash
git add ergon_core/ergon_core/core/api/test_harness.py \
        tests/unit/test_test_harness.py
git commit -m "feat(harness): /api/test/write/{run/seed,reset} with X-Test-Secret gate"
```

---

## Task 8 — Mount harness router conditionally in `app.py`

**Files:**
- Modify: `ergon_core/ergon_core/core/api/app.py`
- Test: `tests/unit/test_app_mounts_harness_conditionally.py`

- [ ] **Step 8.1: Locate the app-factory function**

```bash
uv run python -c "from ergon_core.core.api.app import app; print(type(app))"
```

If `app` is a module-level FastAPI instance, patching via env-var requires importlib reloading in the test. If there's a `create_app()` factory, prefer invoking it with the env var set.

- [ ] **Step 8.2: Write failing test**

```python
# tests/unit/test_app_mounts_harness_conditionally.py
"""app.py mounts /api/test/* iff ENABLE_TEST_HARNESS=1 at import time."""

import importlib
import os
from uuid import uuid4

from fastapi.testclient import TestClient


def _reload_app_with(env_value: str | None):
    prev = os.environ.get("ENABLE_TEST_HARNESS")
    try:
        if env_value is None:
            os.environ.pop("ENABLE_TEST_HARNESS", None)
        else:
            os.environ["ENABLE_TEST_HARNESS"] = env_value
        import ergon_core.core.api.app as app_mod
        importlib.reload(app_mod)
        return app_mod.app
    finally:
        if prev is None:
            os.environ.pop("ENABLE_TEST_HARNESS", None)
        else:
            os.environ["ENABLE_TEST_HARNESS"] = prev


def test_harness_unmounted_when_env_absent() -> None:
    app = _reload_app_with(None)
    client = TestClient(app)
    resp = client.get(f"/api/test/read/run/{uuid4()}/state")
    assert resp.status_code == 404


def test_harness_mounted_when_env_set() -> None:
    app = _reload_app_with("1")
    client = TestClient(app)
    resp = client.get(f"/api/test/read/run/{uuid4()}/state")
    # With no DB seeded, the handler either raises 404 (unknown run_id) or 500
    # if Postgres is unreachable from the unit-test env. Either proves the route
    # is mounted.
    assert resp.status_code in (404, 500)
```

- [ ] **Step 8.3: Run — expect FAIL on the mounted case**

```bash
uv run pytest tests/unit/test_app_mounts_harness_conditionally.py -v
```

- [ ] **Step 8.4: Modify `app.py` to mount the router conditionally**

Read `ergon_core/ergon_core/core/api/app.py` to find where other routers are included. Add at the end of the router-wiring block:

```python
# Test-only harness: mounted in CI + local-e2e only.
if os.environ.get("ENABLE_TEST_HARNESS") == "1":
    from ergon_core.core.api.test_harness import router as _test_harness_router
    app.include_router(_test_harness_router)
```

Ensure `import os` is present at the top of `app.py`.

- [ ] **Step 8.5: Run tests**

```bash
uv run pytest tests/unit/test_app_mounts_harness_conditionally.py -v
```

Expected: PASS 2/2.

- [ ] **Step 8.6: Run full unit suite to catch regressions**

```bash
uv run pytest tests/unit -v
```

Expected: green.

- [ ] **Step 8.7: Commit**

```bash
git add ergon_core/ergon_core/core/api/app.py \
        tests/unit/test_app_mounts_harness_conditionally.py
git commit -m "feat(harness): conditionally mount /api/test/* router on ENABLE_TEST_HARNESS=1"
```

---

## Task 9 — Integration test: seed → read → reset round-trip

**Files:**
- Create: `tests/integration/smokes/__init__.py`
- Create: `tests/integration/smokes/test_smoke_harness.py`

This test runs against real Postgres via the integration-tier fixture (already wired by the parent reset RFC's PR 3). If that fixture isn't available yet (reset PR 3 not merged), mark with `@pytest.mark.skip` and add a TODO to re-enable; do NOT block PR 1 of this plan on reset PR 3.

- [ ] **Step 9.1: Create the integration-test module**

```python
# tests/integration/smokes/__init__.py
```

```python
# tests/integration/smokes/test_smoke_harness.py
"""Integration: /api/test/* round-trips against real Postgres."""

from __future__ import annotations

import os

import httpx
import pytest


pytestmark = pytest.mark.integration


API = os.environ.get("ERGON_API_BASE_URL", "http://127.0.0.1:9000")
SECRET = os.environ.get("TEST_HARNESS_SECRET", "ci-secret")


@pytest.fixture(autouse=True)
def _reset_before_each() -> None:
    httpx.post(
        f"{API}/api/test/write/reset",
        json={"cohort_prefix": "ci-smoke-"},
        headers={"X-Test-Secret": SECRET},
        timeout=5,
    )
    yield


def test_seed_then_read_then_reset_roundtrip() -> None:
    # Seed
    seed = httpx.post(
        f"{API}/api/test/write/run/seed",
        json={"cohort": "ci-smoke-harness-test", "status": "completed"},
        headers={"X-Test-Secret": SECRET},
        timeout=5,
    )
    assert seed.status_code == 201, seed.text
    run_id = seed.json()["run_id"]

    # Read
    read = httpx.get(f"{API}/api/test/read/run/{run_id}/state", timeout=5)
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["run_id"] == run_id
    assert body["status"] == "completed"

    # Reset
    reset = httpx.post(
        f"{API}/api/test/write/reset",
        json={"cohort_prefix": "ci-smoke-"},
        headers={"X-Test-Secret": SECRET},
        timeout=5,
    )
    assert reset.status_code == 204

    # Now gone
    read2 = httpx.get(f"{API}/api/test/read/run/{run_id}/state", timeout=5)
    assert read2.status_code == 404
```

- [ ] **Step 9.2: Attempt to run (may skip if integration fixtures unavailable)**

```bash
uv run pytest tests/integration/smokes/test_smoke_harness.py -v -m integration
```

Expected: PASS if the integration stack is up; else skipped. Document the result in the PR body.

- [ ] **Step 9.3: Commit**

```bash
git add tests/integration/smokes/__init__.py \
        tests/integration/smokes/test_smoke_harness.py
git commit -m "test(harness): integration round-trip for /api/test/* against real Postgres"
```

---

## Task 10 — `BackendHarnessClient` TypeScript helper

**Files:**
- Create: `ergon-dashboard/tests/helpers/testHarnessClient.ts`

Note: The existing `ergon-dashboard/tests/helpers/harnessClient.ts` talks to **dashboard-side** harness routes (`/api/test/dashboard/*`) on Next.js. That is a different system and remains untouched. The new file talks to the **backend Python** harness.

- [ ] **Step 10.1: Implement the helper**

```typescript
// ergon-dashboard/tests/helpers/testHarnessClient.ts

import type { APIRequestContext } from "@playwright/test";

export interface TestGraphNodeDto {
  task_key: string;
  level: number;
  status: string;
  parent_task_key: string | null;
}

export interface TestEvaluationDto {
  score: number;
  reason: string;
}

export interface TestGraphMutationDto {
  sequence: number;
  mutation_type: string;
  target_task_key: string | null;
}

export interface TestRunStateDto {
  run_id: string;
  status: string;
  graph_nodes: TestGraphNodeDto[];
  mutations: TestGraphMutationDto[];
  evaluations: TestEvaluationDto[];
  resource_count: number;
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
        `BackendHarnessClient.getRunState failed: ${response.status()} ${await response.text()}`,
      );
    }
    return (await response.json()) as TestRunStateDto;
  }
}
```

- [ ] **Step 10.2: Confirm TS compiles**

```bash
pnpm --dir ergon-dashboard exec tsc --noEmit
```

Expected: no TS errors.

- [ ] **Step 10.3: Commit**

```bash
git add ergon-dashboard/tests/helpers/testHarnessClient.ts
git commit -m "feat(harness): BackendHarnessClient TS helper for /api/test/read"
```

---

## Task 11 — `playwright.config.ts`: screenshots always on

**Files:**
- Modify: `ergon-dashboard/playwright.config.ts`

- [ ] **Step 11.1: Flip the screenshot setting**

Read the file to locate the `use:` block, then change:

```diff
 use: {
   baseURL,
   trace: "on-first-retry",
-  screenshot: "only-on-failure",
+  screenshot: "on",
   video: "retain-on-failure",
 },
```

- [ ] **Step 11.2: Confirm Playwright config still parses**

```bash
pnpm --dir ergon-dashboard exec playwright test --list 2>&1 | head -5
```

Expected: lists existing tests with no config-parse errors.

- [ ] **Step 11.3: Commit**

```bash
git add ergon-dashboard/playwright.config.ts
git commit -m "chore(playwright): screenshots always on (required by e2e smoke RFC)"
```

---

## Task 12 — Close superseded RFCs + open PR 1

**Files:**
- Move: `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md` → `docs/rfcs/rejected/2026-04-18-fixed-delegation-stub-worker.md`
- Move: `docs/rfcs/active/2026-04-18-test-harness-endpoints.md` → `docs/rfcs/rejected/2026-04-18-test-harness-endpoints.md`

- [ ] **Step 12.1: Create `rejected/` dir if absent**

```bash
mkdir -p docs/rfcs/rejected
```

- [ ] **Step 12.2: Move + set frontmatter on the fixed-delegation RFC**

```bash
git mv docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md \
       docs/rfcs/rejected/2026-04-18-fixed-delegation-stub-worker.md
```

Open the moved file. Change its frontmatter `status:` to `rejected` and add `superseded_by:` if not already present:

```yaml
---
status: rejected
superseded_by: docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md
# (other fields unchanged)
---
```

Note: the path under `superseded_by:` points to `accepted/` because by the time someone reads this RFC, the successor is expected to be accepted. Until PR 4 of this plan lands, the successor still lives at `docs/rfcs/active/...` — that is OK, the pointer is the *intended* final path.

- [ ] **Step 12.3: Move + set frontmatter on the test-harness-endpoints RFC**

```bash
git mv docs/rfcs/active/2026-04-18-test-harness-endpoints.md \
       docs/rfcs/rejected/2026-04-18-test-harness-endpoints.md
```

Edit the frontmatter identically.

- [ ] **Step 12.4: Run full check suite**

```bash
pnpm run check:fast
uv run pytest tests/unit -v
```

Expected: both green.

- [ ] **Step 12.5: Commit RFC moves**

```bash
git add docs/rfcs/rejected/2026-04-18-fixed-delegation-stub-worker.md \
        docs/rfcs/rejected/2026-04-18-test-harness-endpoints.md \
        docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md \
        docs/rfcs/active/2026-04-18-test-harness-endpoints.md
git commit -m "docs(rfc): move fixed-delegation-stub-worker + test-harness-endpoints to rejected/ (absorbed)"
```

- [ ] **Step 12.6: Push + open PR**

```bash
git push -u origin feature/smoke-shared-infra
gh pr create --title "feat(smoke): shared canonical-smoke infrastructure + /api/test/* harness (PR 1 of 4)" \
  --body "$(cat <<'EOF'
## Summary
- Lands shared canonical-smoke worker infrastructure (parent worker + subworker Protocol + base leaf + criterion base).
- Lands `/api/test/*` harness router with conditional mount and `X-Test-Secret` gate.
- Closes two superseded RFCs (absorbed into `2026-04-21-e2e-smoke-coverage-rewrite.md`).
- **No** env-specific smoke wiring; no CI workflow. Those arrive in PRs 2–4.

## Test plan
- [x] `uv run pytest tests/unit -v` — unit suite green (new smoke + harness tests)
- [x] `pnpm run check:fast` — backend + frontend lint/type green
- [x] Integration harness round-trip (if integration stack up locally; otherwise CI verifies)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 12.7: Watch PR CI**

If CI fails, iterate with fresh commits on the branch. Never `--amend` a pushed commit. Never `--no-verify`.

---

# PR 2 — `researchrubrics` canary env smoke

**PR branch:** `feature/smoke-researchrubrics`

**Precondition:** PR 1 of this plan is merged. Reset RFC PRs 2 + 3 + 4 are merged (Docker caching, integration infra, `tests/e2e/` deleted).

**Goal:** First live canonical smoke, end-to-end wired. CI matrix exists with only this env. Failure-mode rehearsal verifies screenshots upload on all failure paths.

**PR 2 acceptance gate:** `researchrubrics` smoke runs on every PR in under 5 minutes; Postgres record-log + Playwright assertions + screenshot upload + PR inline comment all work end-to-end on pass AND on induced failure.

---

## Task 13 — Prereq check + branch setup

- [ ] **Step 13.1: Verify prerequisites**

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
git fetch origin main
git log origin/main --oneline | head -20
ls tests/e2e/ 2>&1 | grep -v "No such" || echo "tests/e2e/ clean slate confirmed"
ls docker-compose.ci.yml && grep -c "cache-from\|cache-to" .github/workflows/*.yml
```

Expected: `tests/e2e/` does not exist (reset PR 4 merged); `docker-compose.ci.yml` present; GHA cache directives present in at least one workflow.

If any prereq is missing, stop and post a note on the team channel — do not proceed to PR 2 until reset is complete.

- [ ] **Step 13.2: Create branch**

```bash
git checkout main
git pull origin main
git checkout -b feature/smoke-researchrubrics
```

---

## Task 14 — `ResearchRubricsSmokeSubworker` + leaf worker

**Files:**
- Create: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/smoke_subworker.py`
- Test: `tests/unit/test_researchrubrics_smoke_subworker.py`

- [ ] **Step 14.1: Write failing test**

```python
# tests/unit/test_researchrubrics_smoke_subworker.py
"""ResearchRubricsSmokeSubworker: writes markdown report + runs wc -l."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ergon_builtins.benchmarks.researchrubrics.smoke_subworker import (
    ResearchRubricsSmokeSubworker,
)


@pytest.mark.asyncio
async def test_writes_deterministic_markdown_and_runs_wc() -> None:
    sandbox = MagicMock()
    sandbox.files = MagicMock()
    sandbox.files.write = AsyncMock()
    sandbox.commands = MagicMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(stdout="3 /tmp/d_root.md\n", exit_code=0)
    )

    sub = ResearchRubricsSmokeSubworker()
    result = await sub.work(node_id="d_root", sandbox=sandbox)

    sandbox.files.write.assert_awaited_once()
    write_args = sandbox.files.write.await_args.args
    assert write_args[0] == "/tmp/d_root.md"
    assert "# Report d_root" in write_args[1]
    sandbox.commands.run.assert_awaited_once_with("wc -l /tmp/d_root.md")

    assert result.file_path == "/tmp/d_root.md"
    assert result.probe_exit_code == 0
    assert result.probe_stdout.strip().split()[0].isdigit()
```

- [ ] **Step 14.2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_researchrubrics_smoke_subworker.py -v
```

- [ ] **Step 14.3: Implement**

```python
# ergon_builtins/ergon_builtins/benchmarks/researchrubrics/smoke_subworker.py
"""Per-env canonical smoke subworker + leaf for researchrubrics."""

from __future__ import annotations

from ergon_core.core.providers.sandbox.manager import AsyncSandbox

from ergon_builtins.workers.stubs.base_smoke_leaf import BaseSmokeLeafWorker
from ergon_builtins.workers.stubs.smoke_subworker import SubworkerResult


class ResearchRubricsSmokeSubworker:
    """Writes a deterministic markdown report + runs `wc -l`."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        content = f"# Report {node_id}\n\nFinding: canonical smoke artifact.\n"
        path = f"/tmp/{node_id}.md"
        await sandbox.files.write(path, content)
        probe = await sandbox.commands.run(f"wc -l {path}")
        return SubworkerResult(
            file_path=path,
            probe_stdout=probe.stdout,
            probe_exit_code=probe.exit_code,
        )


class ResearchRubricsSmokeLeafWorker(BaseSmokeLeafWorker):
    subworker_cls = ResearchRubricsSmokeSubworker  # type: ignore[assignment]
```

- [ ] **Step 14.4: Run tests**

```bash
uv run pytest tests/unit/test_researchrubrics_smoke_subworker.py -v
```

Expected: PASS.

- [ ] **Step 14.5: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/researchrubrics/smoke_subworker.py \
        tests/unit/test_researchrubrics_smoke_subworker.py
git commit -m "feat(smoke/rr): ResearchRubricsSmokeSubworker writes .md + runs wc -l"
```

---

## Task 15 — Fill `ResearchRubricsSmokeCriterion._verify_env_content`

**Files:**
- Modify: `ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py`
- Modify: `tests/unit/test_smoke_criterion.py`

- [ ] **Step 15.1: Add failing test**

Append to `tests/unit/test_smoke_criterion.py`:

```python
from dataclasses import replace


@pytest.mark.asyncio
async def test_researchrubrics_criterion_passes_with_markdown_and_digit_wc() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        ResearchRubricsSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = f"# Report {r.task_key}\n\nFinding: x.\n".encode()
        r.metadata["probe_stdout"] = "3 /tmp/x.md\n"
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await ResearchRubricsSmokeCriterion().evaluate(ctx)
    assert score.value == 1.0


@pytest.mark.asyncio
async def test_researchrubrics_criterion_fails_missing_header() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        ResearchRubricsSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = b"no header here\n"
        r.metadata["probe_stdout"] = "3 /tmp/x.md\n"
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await ResearchRubricsSmokeCriterion().evaluate(ctx)
    assert score.value == 0.0
    assert "markdown header" in score.reason.lower()


@pytest.mark.asyncio
async def test_researchrubrics_criterion_fails_non_digit_wc_output() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        ResearchRubricsSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = f"# Report {r.task_key}\n".encode()
        r.metadata["probe_stdout"] = "hello world\n"
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await ResearchRubricsSmokeCriterion().evaluate(ctx)
    assert score.value == 0.0
    assert "number" in score.reason.lower()
```

- [ ] **Step 15.2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_smoke_criterion.py -v
```

- [ ] **Step 15.3: Fill the criterion**

Edit `ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py`. Replace `ResearchRubricsSmokeCriterion._verify_env_content`:

```python
class ResearchRubricsSmokeCriterion(SmokeCriterionBase):
    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        for r in ctx.resources.all():
            text = r.content.decode("utf-8")
            assert text.startswith(f"# Report {r.task_key}"), (
                f"{r.task_key}: missing expected markdown header"
            )
            wc_output = r.metadata["probe_stdout"].strip()
            first_token = wc_output.split()[0] if wc_output else ""
            assert first_token.isdigit(), (
                f"{r.task_key}: wc -l probe did not return a number, got {wc_output!r}"
            )
```

- [ ] **Step 15.4: Run tests**

```bash
uv run pytest tests/unit/test_smoke_criterion.py -v
```

Expected: all pass.

- [ ] **Step 15.5: Commit**

```bash
git add ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py \
        tests/unit/test_smoke_criterion.py
git commit -m "feat(smoke/rr): ResearchRubricsSmokeCriterion asserts markdown header + wc digit"
```

---

## Task 16 — Register `researchrubrics-smoke-leaf` + composition binding

**Files:**
- Modify: `ergon_builtins/ergon_builtins/registry_core.py`
- Modify: `ergon_cli/ergon_cli/composition/__init__.py`
- Test: `tests/unit/test_researchrubrics_registry_and_binding.py`

- [ ] **Step 16.1: Write failing test**

```python
# tests/unit/test_researchrubrics_registry_and_binding.py
"""Registry + composition bindings include the researchrubrics smoke leaf."""


def test_researchrubrics_smoke_leaf_registered() -> None:
    from ergon_builtins.registry_core import WORKERS
    from ergon_builtins.benchmarks.researchrubrics.smoke_subworker import (
        ResearchRubricsSmokeLeafWorker,
    )

    assert WORKERS["researchrubrics-smoke-leaf"] is ResearchRubricsSmokeLeafWorker


def test_researchrubrics_composition_binds_smoke_leaf() -> None:
    from ergon_cli.composition import BENCHMARK_COMPOSITIONS

    comp = BENCHMARK_COMPOSITIONS["researchrubrics"]
    assert comp.bindings["smoke-leaf"] == "researchrubrics-smoke-leaf"
```

Import path for `BENCHMARK_COMPOSITIONS` may differ. Confirm with:

```bash
uv run python -c "from ergon_cli.composition import BENCHMARK_COMPOSITIONS; print(list(BENCHMARK_COMPOSITIONS.keys()))"
```

If the module path is different (e.g. `ergon_cli.ergon_cli.composition`), adjust both the import in the test and the source.

- [ ] **Step 16.2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_researchrubrics_registry_and_binding.py -v
```

- [ ] **Step 16.3: Register leaf worker**

In `ergon_builtins/ergon_builtins/registry_core.py`, add to imports:

```python
from ergon_builtins.benchmarks.researchrubrics.smoke_subworker import (
    ResearchRubricsSmokeLeafWorker,
)
```

Add to `WORKERS`:

```python
    "researchrubrics-smoke-leaf": ResearchRubricsSmokeLeafWorker,
```

- [ ] **Step 16.4: Add composition binding**

In `ergon_cli/ergon_cli/composition/__init__.py`, locate `BENCHMARK_COMPOSITIONS` (or its equivalent; confirm with step 16.1 grep). Add/extend the `researchrubrics` entry:

```python
    "researchrubrics": Composition(
        bindings={
            # ... existing bindings preserved ...
            "smoke-leaf": "researchrubrics-smoke-leaf",
        },
    ),
```

- [ ] **Step 16.5: Run tests**

```bash
uv run pytest tests/unit/test_researchrubrics_registry_and_binding.py -v
pnpm run check:be:type
```

Expected: unit tests pass; `ty` check clean.

- [ ] **Step 16.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/registry_core.py \
        ergon_cli/ergon_cli/composition/__init__.py \
        tests/unit/test_researchrubrics_registry_and_binding.py
git commit -m "feat(smoke/rr): register researchrubrics-smoke-leaf + smoke-leaf composition binding"
```

---

## Task 17 — `tests/e2e/conftest.py` with finalizer + helpers

**Files:**
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/conftest.py`

- [ ] **Step 17.1: Create the package marker**

```python
# tests/e2e/__init__.py
```

- [ ] **Step 17.2: Write the conftest**

```python
# tests/e2e/conftest.py
"""Shared fixtures + helpers for the canonical e2e smoke tier.

Key responsibilities:
  - run_benchmark(): invoke the `ergon` CLI and extract the run_id.
  - wait_for_terminal(): poll /runs/{id} until the run reaches a terminal state.
  - screenshot_upload_finalizer: after every test (pass or fail), push captures
    to the `screenshots/pr-{N}` orphan ref and post a PR inline-image comment.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from uuid import UUID

import httpx
import pytest


log = logging.getLogger(__name__)


def run_benchmark(
    *,
    slug: str,
    worker: str,
    evaluator: str,
    cohort: str,
    limit: int = 1,
) -> UUID:
    """Run a benchmark via the CLI. Returns the newly-created run_id.

    The CLI is expected to emit the run_id on its last stdout line. If the CLI
    output shape changes, update this parser accordingly.
    """
    result = subprocess.run(
        [
            "ergon", "benchmark", "run", slug,
            "--worker", worker,
            "--evaluator", evaluator,
            "--cohort", cohort,
            "--limit", str(limit),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    result.check_returncode()
    last_line = result.stdout.strip().splitlines()[-1]
    return UUID(last_line.strip())


def wait_for_terminal(run_id: UUID, *, timeout_seconds: int = 180) -> None:
    """Poll /runs/{run_id} every 2s until status ∈ {completed, failed, cancelled}."""
    deadline = time.time() + timeout_seconds
    api = os.environ.get("ERGON_API_BASE_URL", "http://127.0.0.1:9000")
    while time.time() < deadline:
        try:
            r = httpx.get(f"{api}/runs/{run_id}", timeout=5)
        except httpx.HTTPError:
            time.sleep(2)
            continue
        if r.status_code == 200:
            status = r.json().get("status")
            if status in {"completed", "failed", "cancelled"}:
                return
        time.sleep(2)
    raise TimeoutError(
        f"run {run_id} did not reach terminal within {timeout_seconds}s"
    )


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> None:
    """Expose each phase's result on the item so finalizers can inspect pass/fail."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture(autouse=True)
def screenshot_upload_finalizer(
    request: pytest.FixtureRequest,
) -> None:
    """After every e2e test, upload screenshots + post PR comment.

    No-op when PR_NUMBER env absent (local runs). Upload failures are logged but
    never raised — they must not mask the real test failure.
    """
    yield
    pr_number = os.environ.get("PR_NUMBER")
    if not pr_number:
        return

    env = os.environ.get("SMOKE_ENV", "unknown")
    # screenshot_dir fixture is required by each test module; locate via
    # getfixturevalue so we don't fail for non-e2e tests that somehow import us.
    try:
        src = Path(request.getfixturevalue("screenshot_dir"))
    except pytest.FixtureLookupError:
        return

    passed = bool(
        getattr(request.node, "rep_call", None) is not None
        and request.node.rep_call.passed
    )

    try:
        _push_screenshots_to_ref(pr_number, env, src)
        _post_pr_comment(pr_number, env, passed=passed)
    except Exception:
        log.exception("screenshot upload failed; not masking test result")


def _push_screenshots_to_ref(pr_number: str, env: str, src: Path) -> None:
    """git push screenshots/pr-{N} with src/*.png under {env}/."""
    ref = f"screenshots/pr-{pr_number}"
    worktree = Path(f"/tmp/screenshots-{pr_number}")
    if worktree.exists():
        subprocess.run(["rm", "-rf", str(worktree)], check=True)

    fetch = subprocess.run(
        ["git", "fetch", "origin", f"{ref}:{ref}"],
        capture_output=True, text=True,
    )
    if fetch.returncode == 0:
        subprocess.run(["git", "worktree", "add", str(worktree), ref], check=True)
    else:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), "HEAD"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "checkout", "--orphan", ref],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "rm", "-rf", "."],
            check=False,
        )

    env_dir = worktree / env
    env_dir.mkdir(parents=True, exist_ok=True)
    for png in src.glob("*.png"):
        subprocess.run(["cp", str(png), str(env_dir / png.name)], check=True)

    subprocess.run(["git", "-C", str(worktree), "add", "."], check=True)
    commit = subprocess.run(
        ["git", "-C", str(worktree), "commit",
         "-m", f"ci: e2e screenshots pr-{pr_number} {env}"],
        capture_output=True, text=True,
    )
    if commit.returncode == 0:
        subprocess.run(
            ["git", "-C", str(worktree), "push", "origin", f"HEAD:{ref}"],
            check=True,
        )
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree)],
        check=False,
    )


def _post_pr_comment(pr_number: str, env: str, *, passed: bool) -> None:
    """Post a PR comment with inline screenshot images via gh CLI."""
    repo = os.environ.get("GITHUB_REPOSITORY", "DeepFlow-research/ergon")
    status = "PASS" if passed else "FAIL"
    body = (
        f"## E2E smoke — `{env}` — {status}\n\n"
        f"Screenshots from CI run:\n\n"
        f"![dashboard](https://raw.githubusercontent.com/{repo}/screenshots/pr-{pr_number}/{env}/dashboard-full.png)\n\n"
        f"![graph canvas](https://raw.githubusercontent.com/{repo}/screenshots/pr-{pr_number}/{env}/graph.png)\n\n"
        f"![cohort index](https://raw.githubusercontent.com/{repo}/screenshots/pr-{pr_number}/{env}/cohort.png)\n"
    )
    subprocess.run(
        ["gh", "pr", "comment", pr_number, "--body", body],
        check=True,
    )
```

- [ ] **Step 17.3: Sanity-check the conftest imports**

```bash
uv run python -c "import tests.e2e.conftest; print('conftest imports ok')"
```

Expected: `conftest imports ok`.

- [ ] **Step 17.4: Commit**

```bash
git add tests/e2e/__init__.py tests/e2e/conftest.py
git commit -m "feat(e2e): conftest with run_benchmark, wait_for_terminal, screenshot finalizer"
```

---

## Task 18 — `tests/e2e/test_researchrubrics_smoke.py`

**Files:**
- Create: `tests/e2e/test_researchrubrics_smoke.py`

- [ ] **Step 18.1: Write the test**

```python
# tests/e2e/test_researchrubrics_smoke.py
"""End-to-end canonical smoke for the researchrubrics benchmark.

Phases:
  1. Invoke the CLI to start a benchmark run.
  2. Wait for terminal status.
  3. Postgres record-log assertions (direct DB).
  4. Playwright subprocess: dashboard assertions + screenshots.
  5. Finalizer (conftest): upload screenshots + post PR comment.

Requires: ergon backend + dashboard running; ENABLE_TEST_HARNESS=1; Postgres
reachable via ERGON_DATABASE_URL.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest
from sqlmodel import Session, select

from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.shared.enums import RunStatus, TaskStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
)

from tests.e2e.conftest import run_benchmark, wait_for_terminal

ENV = "researchrubrics"
EXPECTED_SUBTASK_KEYS = (
    "d_root", "d_left", "d_right", "d_join",
    "l_1", "l_2", "l_3",
    "s_a", "s_b",
)


@pytest.fixture(scope="module")
def screenshot_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp(f"playwright-{ENV}")


def test_canonical_smoke_passes(screenshot_dir: Path) -> None:
    os.environ["SMOKE_ENV"] = ENV

    # Phase 1: CLI kicks off the benchmark.
    run_id = run_benchmark(
        slug=ENV,
        worker="canonical-smoke",
        evaluator=f"{ENV}-smoke-rubric",
        cohort=f"ci-smoke-{ENV}-{int(time.time())}",
    )

    # Phase 2: wait for terminal state.
    wait_for_terminal(run_id, timeout_seconds=180)

    # Phase 3: Postgres record-log assertions.
    with Session(get_engine()) as s:
        run = s.exec(select(RunRecord).where(RunRecord.id == run_id)).one()
        assert run.status == RunStatus.COMPLETED, f"run status: {run.status}"

        nodes = s.exec(
            select(RunGraphNode).where(RunGraphNode.run_id == run_id)
        ).all()
        subtask_keys = sorted(n.task_key for n in nodes if n.level > 0)
        assert subtask_keys == sorted(EXPECTED_SUBTASK_KEYS), subtask_keys
        for n in nodes:
            assert n.status == TaskStatus.COMPLETED, f"{n.task_key}: {n.status}"

        muts = s.exec(
            select(RunGraphMutation)
            .where(RunGraphMutation.run_id == run_id)
            .order_by(RunGraphMutation.sequence)
        ).all()
        assert any(
            str(m.mutation_type).lower().endswith("add_subtask") for m in muts
        ), "no add_subtask mutations recorded"

        resources = s.exec(
            select(RunResource).where(RunResource.run_id == run_id)
        ).all()
        assert len(resources) == 9, len(resources)
        for r in resources:
            assert r.content_hash, f"{r.task_key}: empty hash"

        evals = s.exec(
            select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
        ).all()
        assert len(evals) == 1 and evals[0].score == 1.0, evals

    # Phase 4: Playwright subprocess (always runs; writes screenshots on
    # pass or fail via playwright.config.ts screenshot: "on").
    result = subprocess.run(
        [
            "pnpm", "--dir", "ergon-dashboard", "exec",
            "playwright", "test",
            f"tests/e2e/{ENV}.smoke.spec.ts",
            "--project=chromium",
        ],
        env={
            **os.environ,
            "RUN_ID": str(run_id),
            "SMOKE_ENV": ENV,
            "SCREENSHOT_DIR": str(screenshot_dir),
            "PLAYWRIGHT_LIVE": "1",
            "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:3000",
            "ERGON_API_BASE_URL": "http://127.0.0.1:9000",
            "TEST_HARNESS_SECRET": os.environ.get("TEST_HARNESS_SECRET", "ci-secret"),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    # Phase 5 upload runs in the conftest finalizer regardless.
    assert result.returncode == 0, (
        f"Playwright failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
```

- [ ] **Step 18.2: Commit (no local run — CI is authoritative)**

```bash
git add tests/e2e/test_researchrubrics_smoke.py
git commit -m "feat(e2e/rr): canonical smoke test — CLI + Postgres asserts + Playwright subprocess"
```

---

## Task 19 — Playwright spec for researchrubrics

**Files:**
- Create: `ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts`

- [ ] **Step 19.1: Locate Playwright test directory**

```bash
ls ergon-dashboard/tests/e2e/ 2>&1 | head
```

If `ergon-dashboard/tests/e2e/` doesn't exist, create it with:

```bash
mkdir -p ergon-dashboard/tests/e2e
```

- [ ] **Step 19.2: Write the spec**

```typescript
// ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts
//
// Canonical smoke spec for researchrubrics. Driven by the Python pytest
// (tests/e2e/test_researchrubrics_smoke.py) as a subprocess. Playwright does:
//   1. Query the backend harness for authoritative run state.
//   2. Navigate to /run/{RUN_ID}; assert 10 graph nodes render (1 root + 9).
//   3. Navigate to /; assert the cohort index renders.
//   4. Capture full-page, graph-canvas, and cohort-index screenshots.
//
// Screenshots on failure are captured automatically by the global config
// (`screenshot: "on"`).

import { expect, test } from "@playwright/test";

import { BackendHarnessClient } from "../helpers/testHarnessClient";

const RUN_ID = process.env.RUN_ID;
const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR ?? "/tmp/playwright";
const ERGON_API =
  process.env.ERGON_API_BASE_URL ?? "http://127.0.0.1:9000";

test.skip(!RUN_ID, "RUN_ID env var required (populated by pytest driver)");

test("canonical smoke — dashboard renders expected run", async ({
  request,
  page,
}) => {
  // 1. Authoritative backend state.
  const harness = new BackendHarnessClient(request, ERGON_API);
  const state = await harness.getRunState(RUN_ID!);
  expect(state.status).toBe("completed");
  expect(state.graph_nodes.filter((n) => n.level > 0)).toHaveLength(9);

  // 2. Run page renders the full graph.
  await page.goto(`/run/${RUN_ID}`);
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  const nodes = page.getByTestId(/^graph-node-/);
  await expect(nodes).toHaveCount(10); // 1 root + 9 subtasks

  await page.screenshot({
    path: `${SCREENSHOT_DIR}/dashboard-full.png`,
    fullPage: true,
  });
  await page.getByTestId("graph-canvas").screenshot({
    path: `${SCREENSHOT_DIR}/graph.png`,
  });

  // 3. Cohort index.
  await page.goto("/");
  await expect(page.getByTestId("cohort-index-list")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/cohort.png`,
  });
});
```

Note: if the dashboard uses different `data-testid` attribute names for the graph canvas, node elements, or cohort index, grep the source and swap them in. Likely candidates (inspect `ergon-dashboard/src/components/`):

```bash
grep -rn "data-testid" ergon-dashboard/src/ | head -40
```

- [ ] **Step 19.3: Lint/typecheck**

```bash
pnpm --dir ergon-dashboard exec tsc --noEmit
pnpm run check:fe
```

Expected: green.

- [ ] **Step 19.4: Commit**

```bash
git add ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts
git commit -m "feat(e2e/rr): Playwright spec asserts dashboard renders 10-node graph + captures screenshots"
```

---

## Task 20 — `docker-compose.ci.yml` env additions

**Files:**
- Modify: `docker-compose.ci.yml`

- [ ] **Step 20.1: Inspect current env block for the api service**

```bash
grep -A 12 "^  api:" docker-compose.ci.yml
```

- [ ] **Step 20.2: Add `ENABLE_TEST_HARNESS` + `TEST_HARNESS_SECRET`**

In the `api:` service `environment:` block, add:

```yaml
      ENABLE_TEST_HARNESS: "1"
      TEST_HARNESS_SECRET: "ci-secret"
```

- [ ] **Step 20.3: Smoke the compose file**

```bash
docker compose -f docker-compose.ci.yml config > /dev/null && echo "compose config ok"
```

Expected: `compose config ok`.

- [ ] **Step 20.4: Commit**

```bash
git add docker-compose.ci.yml
git commit -m "ci: enable /api/test/* harness + secret in docker-compose.ci.yml api env"
```

---

## Task 21 — `.github/workflows/e2e-benchmarks.yml` with researchrubrics only

**Files:**
- Create: `.github/workflows/e2e-benchmarks.yml`

- [ ] **Step 21.1: Write the workflow**

```yaml
# .github/workflows/e2e-benchmarks.yml
name: e2e-benchmarks

on:
  pull_request:
    types: [opened, synchronize, reopened, closed]
    branches: [main]

concurrency:
  group: e2e-${{ github.ref }}
  cancel-in-progress: true

jobs:
  smoke:
    name: e2e smoke — ${{ matrix.env }}
    if: github.event.action != 'closed'
    timeout-minutes: 5
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        env: [researchrubrics]  # PR 3 adds minif2f; PR 4 adds swebench-verified
    permissions:
      contents: write       # push to screenshots/pr-{N} ref
      pull-requests: write  # post PR comment
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - run: uv sync --all-packages --group dev
      - run: pnpm install --frozen-lockfile

      - uses: docker/setup-buildx-action@v3
      - uses: docker/bake-action@v4
        with:
          files: docker-compose.ci.yml
          load: true
          set: |
            *.cache-from=type=gha
            *.cache-to=type=gha,mode=max

      - name: Bring up backend stack
        run: |
          docker compose -f docker-compose.ci.yml up -d postgres inngest-dev api
          timeout 60 bash -c 'until curl -sf http://localhost:9000/docs >/dev/null; do sleep 2; done'

      - name: Build + serve dashboard
        run: |
          pnpm --dir ergon-dashboard build
          pnpm --dir ergon-dashboard start > /tmp/dashboard.log 2>&1 &
          timeout 30 bash -c 'until curl -sf http://localhost:3000 >/dev/null; do sleep 2; done'
        env:
          ERGON_API_BASE_URL: http://127.0.0.1:9000

      - name: Install Playwright browsers
        run: pnpm --dir ergon-dashboard exec playwright install --with-deps chromium

      - name: Run smoke
        run: |
          uv run pytest tests/e2e/test_${{ matrix.env }}_smoke.py -v --timeout=270
        env:
          ERGON_DATABASE_URL: postgresql://ergon:ci_test@localhost:5433/ergon
          ENABLE_TEST_HARNESS: "1"
          TEST_HARNESS_SECRET: ci-secret
          PR_NUMBER: ${{ github.event.pull_request.number }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          E2B_API_KEY: ${{ secrets.E2B_API_KEY }}

      - name: Upload Playwright trace on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-trace-${{ matrix.env }}
          path: ergon-dashboard/test-results/
          retention-days: 7

      - name: Dump backend log on failure
        if: failure()
        run: |
          docker compose -f docker-compose.ci.yml logs api | tail -200

  cleanup-screenshot-ref:
    name: Delete screenshots/pr-${{ github.event.pull_request.number }} on close
    if: github.event.action == 'closed'
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - name: Delete screenshot ref
        run: |
          git push origin --delete "screenshots/pr-${{ github.event.pull_request.number }}" || true
```

- [ ] **Step 21.2: Yaml-lint**

```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/e2e-benchmarks.yml'))" && echo "yaml ok"
```

- [ ] **Step 21.3: Commit**

```bash
git add .github/workflows/e2e-benchmarks.yml
git commit -m "ci(e2e): per-env matrix workflow (researchrubrics only; PR 3/4 extend) + ref cleanup"
```

---

## Task 22 — Push PR 2 and verify CI green-path

- [ ] **Step 22.1: Push + open PR**

```bash
git push -u origin feature/smoke-researchrubrics
gh pr create --title "feat(e2e/rr): canonical smoke for researchrubrics (PR 2 of 4)" \
  --body "$(cat <<'EOF'
## Summary
- First live canonical smoke (researchrubrics), using the shared infra from PR 1.
- Python pytest asserts Postgres record-log + 10-node graph; invokes Playwright subprocess for dashboard checks + screenshots.
- Screenshots upload inline to PR comment on pass AND fail via `screenshots/pr-{N}` orphan ref.
- CI workflow `.github/workflows/e2e-benchmarks.yml` with 5-minute budget, every-PR trigger, and ref-cleanup on PR close.

## Test plan
- [x] Unit + integration suites green locally.
- [x] CI: `e2e smoke — researchrubrics` job runs and produces a passing screenshot comment on this PR.
- [ ] Failure-mode rehearsal (Task 23) before merge.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 22.2: Wait for first CI run + confirm screenshot comment appears**

Wait ~5 minutes. Open the PR in the browser and confirm:
- A comment appears with inline dashboard / graph / cohort images.
- The `e2e smoke — researchrubrics` check is green.
- The 5-min budget was not exceeded.

If the 5-min budget was exceeded: note actuals in the PR body and raise to 8 min (edit the workflow + push).

If screenshot upload fails but the run passes: diagnose the finalizer — check logs for the finalizer exception (it logs but does not fail the test). Fix and push a follow-up commit.

---

## Task 23 — Failure-mode rehearsal (pre-merge)

Before merging PR 2, manually induce each failure class against the live CI to verify screenshot delivery works on every failure path.

- [ ] **Step 23.1: Fail the Postgres assertion**

On a throwaway branch off `feature/smoke-researchrubrics`:

```bash
git checkout -b rehearsal/postgres-fail
```

Edit `tests/e2e/test_researchrubrics_smoke.py`, change `assert len(resources) == 9` to `assert len(resources) == 999`. Push and open a dummy PR (do NOT merge):

```bash
git push -u origin rehearsal/postgres-fail
gh pr create --title "rehearsal: force Postgres assertion fail" --body "Do not merge. Rehearsal for PR 2."
```

Confirm: pytest fails on phase 3; Playwright still ran (see run log); finalizer uploaded screenshots; PR comment shows ❌ FAIL with dashboard images.

Close this PR without merging:

```bash
gh pr close --delete-branch "$(gh pr list --head rehearsal/postgres-fail --json number -q '.[0].number')"
```

- [ ] **Step 23.2: Fail the Playwright assertion**

On a new rehearsal branch off `feature/smoke-researchrubrics`:

```bash
git checkout feature/smoke-researchrubrics
git checkout -b rehearsal/playwright-fail
```

Edit `ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts`, change `toHaveCount(10)` to `toHaveCount(999)`. Push and open a dummy PR. Confirm:
- Python pytest fails on phase 4 with non-zero subprocess returncode.
- Playwright-captured failure screenshots (via global config) are uploaded.
- PR comment shows ❌ FAIL.

Close without merging.

- [ ] **Step 23.3: Force a timeout**

New rehearsal branch:

```bash
git checkout feature/smoke-researchrubrics
git checkout -b rehearsal/timeout-fail
```

Edit `tests/e2e/test_researchrubrics_smoke.py`: set `wait_for_terminal(run_id, timeout_seconds=3)`. Push and open a dummy PR. Confirm:
- `wait_for_terminal` raises `TimeoutError`.
- Finalizer still runs (no screenshots were written because Playwright never ran; the finalizer logs missing files but does not raise).
- PR comment shows ❌ FAIL but images render as broken (that's expected — no Playwright screenshot was taken).

Close without merging.

- [ ] **Step 23.4: Document rehearsal in PR 2 body**

Append to PR 2 description (`gh pr edit`):

```
## Failure-mode rehearsal results
- Postgres-fail: screenshots delivered ✅ (rehearsal PR #XXX)
- Playwright-fail: failure screenshots delivered ✅ (rehearsal PR #YYY)
- Timeout: PR comment posted with FAIL status ✅ (rehearsal PR #ZZZ)
```

- [ ] **Step 23.5: Merge PR 2**

```bash
gh pr merge feature/smoke-researchrubrics --squash --delete-branch
```

---

# PR 3 — `minif2f` env smoke

**PR branch:** `feature/smoke-minif2f`

**Goal:** Add the second canonical smoke. No architectural changes — pure template repetition against the `minif2f` env. Adds to the CI matrix.

**PR 3 acceptance gate:** both `researchrubrics` and `minif2f` smokes green on every PR; MiniF2F sandbox image has `lean` on PATH.

---

## Task 24 — Branch + subworker

**Files:**
- Create: `ergon_builtins/ergon_builtins/benchmarks/minif2f/smoke_subworker.py`
- Test: `tests/unit/test_minif2f_smoke_subworker.py`

- [ ] **Step 24.1: Create branch**

```bash
git checkout main && git pull origin main
git checkout -b feature/smoke-minif2f
```

- [ ] **Step 24.2: Write failing test**

```python
# tests/unit/test_minif2f_smoke_subworker.py
"""MiniF2FSmokeSubworker: writes .lean + runs `lean --check`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ergon_builtins.benchmarks.minif2f.smoke_subworker import (
    MiniF2FSmokeSubworker,
)


@pytest.mark.asyncio
async def test_writes_lean_theorem_and_runs_lean_check() -> None:
    sandbox = MagicMock()
    sandbox.files = MagicMock()
    sandbox.files.write = AsyncMock()
    sandbox.commands = MagicMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(stdout="", exit_code=0)
    )

    sub = MiniF2FSmokeSubworker()
    result = await sub.work(node_id="d_root", sandbox=sandbox)

    write_args = sandbox.files.write.await_args.args
    assert write_args[0] == "/tmp/d_root.lean"
    assert "theorem smoke_trivial" in write_args[1]
    sandbox.commands.run.assert_awaited_once_with("lean --check /tmp/d_root.lean")
    assert result.probe_exit_code == 0
```

- [ ] **Step 24.3: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_minif2f_smoke_subworker.py -v
```

- [ ] **Step 24.4: Implement**

```python
# ergon_builtins/ergon_builtins/benchmarks/minif2f/smoke_subworker.py
"""Per-env canonical smoke subworker + leaf for minif2f."""

from __future__ import annotations

from ergon_core.core.providers.sandbox.manager import AsyncSandbox

from ergon_builtins.workers.stubs.base_smoke_leaf import BaseSmokeLeafWorker
from ergon_builtins.workers.stubs.smoke_subworker import SubworkerResult


class MiniF2FSmokeSubworker:
    """Writes a trivial Lean proof + runs `lean --check`."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        content = (
            f"-- canonical smoke proof for {node_id}\n"
            "theorem smoke_trivial : 1 + 1 = 2 := by norm_num\n"
        )
        path = f"/tmp/{node_id}.lean"
        await sandbox.files.write(path, content)
        probe = await sandbox.commands.run(f"lean --check {path}")
        return SubworkerResult(
            file_path=path,
            probe_stdout=probe.stdout,
            probe_exit_code=probe.exit_code,
        )


class MiniF2FSmokeLeafWorker(BaseSmokeLeafWorker):
    subworker_cls = MiniF2FSmokeSubworker  # type: ignore[assignment]
```

- [ ] **Step 24.5: Run tests**

```bash
uv run pytest tests/unit/test_minif2f_smoke_subworker.py -v
```

- [ ] **Step 24.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/minif2f/smoke_subworker.py \
        tests/unit/test_minif2f_smoke_subworker.py
git commit -m "feat(smoke/minif2f): MiniF2FSmokeSubworker writes .lean + lean --check"
```

---

## Task 25 — Fill `MiniF2FSmokeCriterion`

**Files:**
- Modify: `ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py`
- Modify: `tests/unit/test_smoke_criterion.py`

- [ ] **Step 25.1: Add failing test**

Append to `tests/unit/test_smoke_criterion.py`:

```python
@pytest.mark.asyncio
async def test_minif2f_criterion_passes_with_theorem_text() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        MiniF2FSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = (
            f"-- canonical smoke proof for {r.task_key}\n"
            "theorem smoke_trivial : 1 + 1 = 2 := by norm_num\n"
        ).encode()
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await MiniF2FSmokeCriterion().evaluate(ctx)
    assert score.value == 1.0


@pytest.mark.asyncio
async def test_minif2f_criterion_fails_without_theorem_declaration() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        MiniF2FSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = b"-- no theorem here\n"
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await MiniF2FSmokeCriterion().evaluate(ctx)
    assert score.value == 0.0
    assert "theorem" in score.reason.lower()
```

- [ ] **Step 25.2: Implement**

Replace `MiniF2FSmokeCriterion._verify_env_content`:

```python
class MiniF2FSmokeCriterion(SmokeCriterionBase):
    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        for r in ctx.resources.all():
            text = r.content.decode("utf-8")
            assert "theorem smoke_trivial" in text, (
                f"{r.task_key}: missing Lean theorem declaration"
            )
```

- [ ] **Step 25.3: Run tests**

```bash
uv run pytest tests/unit/test_smoke_criterion.py -v
```

- [ ] **Step 25.4: Commit**

```bash
git add ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py \
        tests/unit/test_smoke_criterion.py
git commit -m "feat(smoke/minif2f): MiniF2FSmokeCriterion asserts theorem declaration in .lean"
```

---

## Task 26 — Register minif2f leaf + composition binding

**Files:**
- Modify: `ergon_builtins/ergon_builtins/registry_core.py`
- Modify: `ergon_cli/ergon_cli/composition/__init__.py`
- Test: `tests/unit/test_minif2f_registry_and_binding.py`

- [ ] **Step 26.1: Write failing test**

```python
# tests/unit/test_minif2f_registry_and_binding.py
def test_minif2f_smoke_leaf_registered() -> None:
    from ergon_builtins.registry_core import WORKERS
    from ergon_builtins.benchmarks.minif2f.smoke_subworker import (
        MiniF2FSmokeLeafWorker,
    )

    assert WORKERS["minif2f-smoke-leaf"] is MiniF2FSmokeLeafWorker


def test_minif2f_composition_binds_smoke_leaf() -> None:
    from ergon_cli.composition import BENCHMARK_COMPOSITIONS

    assert (
        BENCHMARK_COMPOSITIONS["minif2f"].bindings["smoke-leaf"]
        == "minif2f-smoke-leaf"
    )
```

- [ ] **Step 26.2: Wire registry + binding**

In `registry_core.py`, add:

```python
from ergon_builtins.benchmarks.minif2f.smoke_subworker import MiniF2FSmokeLeafWorker
```

```python
    "minif2f-smoke-leaf": MiniF2FSmokeLeafWorker,
```

In `ergon_cli/ergon_cli/composition/__init__.py`, extend the `minif2f` composition's `bindings` dict with:

```python
            "smoke-leaf": "minif2f-smoke-leaf",
```

- [ ] **Step 26.3: Run tests**

```bash
uv run pytest tests/unit/test_minif2f_registry_and_binding.py -v
```

- [ ] **Step 26.4: Commit**

```bash
git add ergon_builtins/ergon_builtins/registry_core.py \
        ergon_cli/ergon_cli/composition/__init__.py \
        tests/unit/test_minif2f_registry_and_binding.py
git commit -m "feat(smoke/minif2f): register minif2f-smoke-leaf + composition binding"
```

---

## Task 27 — minif2f pytest + Playwright spec

**Files:**
- Create: `tests/e2e/test_minif2f_smoke.py`
- Create: `ergon-dashboard/tests/e2e/minif2f.smoke.spec.ts`

- [ ] **Step 27.1: Create the pytest**

```python
# tests/e2e/test_minif2f_smoke.py
"""End-to-end canonical smoke for the minif2f benchmark.

Identical shape to test_researchrubrics_smoke.py — only ENV differs.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest
from sqlmodel import Session, select

from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.shared.enums import RunStatus, TaskStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
)

from tests.e2e.conftest import run_benchmark, wait_for_terminal

ENV = "minif2f"
EXPECTED_SUBTASK_KEYS = (
    "d_root", "d_left", "d_right", "d_join",
    "l_1", "l_2", "l_3",
    "s_a", "s_b",
)


@pytest.fixture(scope="module")
def screenshot_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp(f"playwright-{ENV}")


def test_canonical_smoke_passes(screenshot_dir: Path) -> None:
    os.environ["SMOKE_ENV"] = ENV

    run_id = run_benchmark(
        slug=ENV,
        worker="canonical-smoke",
        evaluator=f"{ENV}-smoke-rubric",
        cohort=f"ci-smoke-{ENV}-{int(time.time())}",
    )
    wait_for_terminal(run_id, timeout_seconds=180)

    with Session(get_engine()) as s:
        run = s.exec(select(RunRecord).where(RunRecord.id == run_id)).one()
        assert run.status == RunStatus.COMPLETED, f"run status: {run.status}"

        nodes = s.exec(
            select(RunGraphNode).where(RunGraphNode.run_id == run_id)
        ).all()
        subtask_keys = sorted(n.task_key for n in nodes if n.level > 0)
        assert subtask_keys == sorted(EXPECTED_SUBTASK_KEYS), subtask_keys
        for n in nodes:
            assert n.status == TaskStatus.COMPLETED, f"{n.task_key}: {n.status}"

        muts = s.exec(
            select(RunGraphMutation)
            .where(RunGraphMutation.run_id == run_id)
            .order_by(RunGraphMutation.sequence)
        ).all()
        assert any(
            str(m.mutation_type).lower().endswith("add_subtask") for m in muts
        )

        resources = s.exec(
            select(RunResource).where(RunResource.run_id == run_id)
        ).all()
        assert len(resources) == 9, len(resources)

        evals = s.exec(
            select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
        ).all()
        assert len(evals) == 1 and evals[0].score == 1.0, evals

    result = subprocess.run(
        [
            "pnpm", "--dir", "ergon-dashboard", "exec",
            "playwright", "test",
            f"tests/e2e/{ENV}.smoke.spec.ts",
            "--project=chromium",
        ],
        env={
            **os.environ,
            "RUN_ID": str(run_id),
            "SMOKE_ENV": ENV,
            "SCREENSHOT_DIR": str(screenshot_dir),
            "PLAYWRIGHT_LIVE": "1",
            "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:3000",
            "ERGON_API_BASE_URL": "http://127.0.0.1:9000",
            "TEST_HARNESS_SECRET": os.environ.get("TEST_HARNESS_SECRET", "ci-secret"),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"Playwright failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
```

- [ ] **Step 27.2: Create the Playwright spec**

```typescript
// ergon-dashboard/tests/e2e/minif2f.smoke.spec.ts

import { expect, test } from "@playwright/test";

import { BackendHarnessClient } from "../helpers/testHarnessClient";

const RUN_ID = process.env.RUN_ID;
const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR ?? "/tmp/playwright";
const ERGON_API =
  process.env.ERGON_API_BASE_URL ?? "http://127.0.0.1:9000";

test.skip(!RUN_ID, "RUN_ID env var required (populated by pytest driver)");

test("canonical smoke — dashboard renders expected run", async ({
  request,
  page,
}) => {
  const harness = new BackendHarnessClient(request, ERGON_API);
  const state = await harness.getRunState(RUN_ID!);
  expect(state.status).toBe("completed");
  expect(state.graph_nodes.filter((n) => n.level > 0)).toHaveLength(9);

  await page.goto(`/run/${RUN_ID}`);
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  const nodes = page.getByTestId(/^graph-node-/);
  await expect(nodes).toHaveCount(10);

  await page.screenshot({
    path: `${SCREENSHOT_DIR}/dashboard-full.png`,
    fullPage: true,
  });
  await page.getByTestId("graph-canvas").screenshot({
    path: `${SCREENSHOT_DIR}/graph.png`,
  });

  await page.goto("/");
  await expect(page.getByTestId("cohort-index-list")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/cohort.png`,
  });
});
```

- [ ] **Step 27.3: Type-check**

```bash
pnpm --dir ergon-dashboard exec tsc --noEmit
```

- [ ] **Step 27.4: Commit**

```bash
git add tests/e2e/test_minif2f_smoke.py \
        ergon-dashboard/tests/e2e/minif2f.smoke.spec.ts
git commit -m "feat(e2e/minif2f): pytest + Playwright spec for canonical smoke"
```

---

## Task 28 — Extend CI matrix with minif2f

**Files:**
- Modify: `.github/workflows/e2e-benchmarks.yml`

- [ ] **Step 28.1: Add to matrix**

In `.github/workflows/e2e-benchmarks.yml`, change:

```diff
     strategy:
       fail-fast: false
       matrix:
-        env: [researchrubrics]  # PR 3 adds minif2f; PR 4 adds swebench-verified
+        env: [researchrubrics, minif2f]  # PR 4 adds swebench-verified
```

- [ ] **Step 28.2: Yaml-lint**

```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/e2e-benchmarks.yml'))" && echo "yaml ok"
```

- [ ] **Step 28.3: Commit**

```bash
git add .github/workflows/e2e-benchmarks.yml
git commit -m "ci(e2e): add minif2f to the smoke matrix"
```

---

## Task 29 — Push PR 3 and verify

- [ ] **Step 29.1: Push + open PR**

```bash
git push -u origin feature/smoke-minif2f
gh pr create --title "feat(e2e/minif2f): canonical smoke (PR 3 of 4)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `minif2f` to the canonical smoke matrix (second env).
- Sandbox image must have `lean` on PATH; if CI fails with `lean: command not found`, update the minif2f sandbox build to include the Lean toolchain.

## Test plan
- [x] Unit + existing smoke tests green.
- [ ] CI green for both `researchrubrics` and `minif2f` on this PR.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 29.2: Verify CI**

Wait for CI. Confirm both matrix jobs (`researchrubrics`, `minif2f`) produce passing inline screenshot comments.

If `lean: command not found`: the minif2f sandbox image is missing the Lean toolchain. Fix by ensuring its Dockerfile installs `lean` (or `elan`) — this is a separate upstream dependency. If it was supposed to be fixed earlier and wasn't, spawn an unblocker task.

- [ ] **Step 29.3: Merge**

```bash
gh pr merge feature/smoke-minif2f --squash --delete-branch
```

---

# PR 4 — `swebench-verified` env smoke + architecture-doc updates + RFC acceptance

**PR branch:** `feature/smoke-swebench`

**Goal:** Third canonical smoke, plus all the architecture-doc updates the RFC commits to in `§Invariants affected`, plus moving this RFC from `active/` to `accepted/`.

**PR 4 acceptance gate:** all three env smokes green; four architecture docs updated to reflect the new invariants; this RFC in `accepted/`.

---

## Task 30 — Branch + subworker

**Files:**
- Create: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/smoke_subworker.py`
- Test: `tests/unit/test_swebench_smoke_subworker.py`

- [ ] **Step 30.1: Create branch**

```bash
git checkout main && git pull origin main
git checkout -b feature/smoke-swebench
```

- [ ] **Step 30.2: Write failing test**

```python
# tests/unit/test_swebench_smoke_subworker.py
"""SweBenchSmokeSubworker: writes .py + runs `pytest --collect-only`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ergon_builtins.benchmarks.swebench_verified.smoke_subworker import (
    SweBenchSmokeSubworker,
)


@pytest.mark.asyncio
async def test_writes_python_and_runs_pytest_collect_only() -> None:
    sandbox = MagicMock()
    sandbox.files = MagicMock()
    sandbox.files.write = AsyncMock()
    sandbox.commands = MagicMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(stdout="collected 1 item\ntest_smoke_noop\n", exit_code=0)
    )

    sub = SweBenchSmokeSubworker()
    result = await sub.work(node_id="d_root", sandbox=sandbox)

    write_args = sandbox.files.write.await_args.args
    assert write_args[0] == "/tmp/fix_d_root.py"
    assert "def test_smoke_noop" in write_args[1]
    sandbox.commands.run.assert_awaited_once_with("pytest --collect-only /tmp/fix_d_root.py")
    assert result.probe_exit_code == 0
```

- [ ] **Step 30.3: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_swebench_smoke_subworker.py -v
```

- [ ] **Step 30.4: Implement**

```python
# ergon_builtins/ergon_builtins/benchmarks/swebench_verified/smoke_subworker.py
"""Per-env canonical smoke subworker + leaf for swebench-verified."""

from __future__ import annotations

from ergon_core.core.providers.sandbox.manager import AsyncSandbox

from ergon_builtins.workers.stubs.base_smoke_leaf import BaseSmokeLeafWorker
from ergon_builtins.workers.stubs.smoke_subworker import SubworkerResult


class SweBenchSmokeSubworker:
    """Writes a no-op pytest file + runs `pytest --collect-only`."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        content = (
            f"# canonical smoke artifact {node_id}\n"
            "def test_smoke_noop() -> None:\n"
            "    assert 1 + 1 == 2\n"
        )
        path = f"/tmp/fix_{node_id}.py"
        await sandbox.files.write(path, content)
        probe = await sandbox.commands.run(f"pytest --collect-only {path}")
        return SubworkerResult(
            file_path=path,
            probe_stdout=probe.stdout,
            probe_exit_code=probe.exit_code,
        )


class SweBenchSmokeLeafWorker(BaseSmokeLeafWorker):
    subworker_cls = SweBenchSmokeSubworker  # type: ignore[assignment]
```

- [ ] **Step 30.5: Run tests**

```bash
uv run pytest tests/unit/test_swebench_smoke_subworker.py -v
```

- [ ] **Step 30.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/swebench_verified/smoke_subworker.py \
        tests/unit/test_swebench_smoke_subworker.py
git commit -m "feat(smoke/swebench): SweBenchSmokeSubworker writes .py + pytest --collect-only"
```

---

## Task 31 — Fill `SweBenchSmokeCriterion`

**Files:**
- Modify: `ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py`
- Modify: `tests/unit/test_smoke_criterion.py`

- [ ] **Step 31.1: Add failing test**

Append to `tests/unit/test_smoke_criterion.py`:

```python
@pytest.mark.asyncio
async def test_swebench_criterion_passes_with_pytest_collection() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        SweBenchSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = (
            f"# canonical smoke artifact {r.task_key}\n"
            "def test_smoke_noop() -> None: assert 1+1 == 2\n"
        ).encode()
        r.metadata["probe_stdout"] = "collected 1 item\ntest_smoke_noop\n"
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await SweBenchSmokeCriterion().evaluate(ctx)
    assert score.value == 1.0


@pytest.mark.asyncio
async def test_swebench_criterion_fails_if_collect_missed() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        SweBenchSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = b"def test_smoke_noop() -> None: pass\n"
        r.metadata["probe_stdout"] = "collected 0 items\n"
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await SweBenchSmokeCriterion().evaluate(ctx)
    assert score.value == 0.0
    assert "test_smoke_noop" in score.reason
```

- [ ] **Step 31.2: Implement**

Replace `SweBenchSmokeCriterion._verify_env_content`:

```python
class SweBenchSmokeCriterion(SmokeCriterionBase):
    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        for r in ctx.resources.all():
            text = r.content.decode("utf-8")
            assert "def test_smoke_noop" in text, (
                f"{r.task_key}: missing pytest function"
            )
            collect_output = r.metadata.get("probe_stdout", "")
            assert "test_smoke_noop" in collect_output, (
                f"{r.task_key}: pytest did not collect test_smoke_noop"
            )
```

- [ ] **Step 31.3: Run tests**

```bash
uv run pytest tests/unit/test_smoke_criterion.py -v
```

- [ ] **Step 31.4: Commit**

```bash
git add ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py \
        tests/unit/test_smoke_criterion.py
git commit -m "feat(smoke/swebench): SweBenchSmokeCriterion asserts pytest function + collect-only output"
```

---

## Task 32 — Register swebench leaf + binding

**Files:**
- Modify: `ergon_builtins/ergon_builtins/registry_core.py`
- Modify: `ergon_cli/ergon_cli/composition/__init__.py`
- Test: `tests/unit/test_swebench_registry_and_binding.py`

- [ ] **Step 32.1: Write test**

```python
# tests/unit/test_swebench_registry_and_binding.py
def test_swebench_smoke_leaf_registered() -> None:
    from ergon_builtins.registry_core import WORKERS
    from ergon_builtins.benchmarks.swebench_verified.smoke_subworker import (
        SweBenchSmokeLeafWorker,
    )

    assert WORKERS["swebench-smoke-leaf"] is SweBenchSmokeLeafWorker


def test_swebench_composition_binds_smoke_leaf() -> None:
    from ergon_cli.composition import BENCHMARK_COMPOSITIONS

    assert (
        BENCHMARK_COMPOSITIONS["swebench-verified"].bindings["smoke-leaf"]
        == "swebench-smoke-leaf"
    )
```

- [ ] **Step 32.2: Wire**

In `registry_core.py`:

```python
from ergon_builtins.benchmarks.swebench_verified.smoke_subworker import (
    SweBenchSmokeLeafWorker,
)
```

```python
    "swebench-smoke-leaf": SweBenchSmokeLeafWorker,
```

In `ergon_cli/ergon_cli/composition/__init__.py`, extend the `swebench-verified` composition `bindings` with:

```python
            "smoke-leaf": "swebench-smoke-leaf",
```

- [ ] **Step 32.3: Run + commit**

```bash
uv run pytest tests/unit/test_swebench_registry_and_binding.py -v
git add ergon_builtins/ergon_builtins/registry_core.py \
        ergon_cli/ergon_cli/composition/__init__.py \
        tests/unit/test_swebench_registry_and_binding.py
git commit -m "feat(smoke/swebench): register swebench-smoke-leaf + composition binding"
```

---

## Task 33 — swebench pytest + Playwright spec

**Files:**
- Create: `tests/e2e/test_swebench_verified_smoke.py`
- Create: `ergon-dashboard/tests/e2e/swebench-verified.smoke.spec.ts`

- [ ] **Step 33.1: Create the pytest (same structure as minif2f, only ENV differs)**

```python
# tests/e2e/test_swebench_verified_smoke.py
"""End-to-end canonical smoke for the swebench-verified benchmark."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest
from sqlmodel import Session, select

from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.shared.enums import RunStatus, TaskStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
)

from tests.e2e.conftest import run_benchmark, wait_for_terminal

ENV = "swebench-verified"
EXPECTED_SUBTASK_KEYS = (
    "d_root", "d_left", "d_right", "d_join",
    "l_1", "l_2", "l_3",
    "s_a", "s_b",
)


@pytest.fixture(scope="module")
def screenshot_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp(f"playwright-{ENV}")


def test_canonical_smoke_passes(screenshot_dir: Path) -> None:
    os.environ["SMOKE_ENV"] = ENV

    run_id = run_benchmark(
        slug=ENV,
        worker="canonical-smoke",
        evaluator="swebench-smoke-rubric",
        cohort=f"ci-smoke-{ENV}-{int(time.time())}",
    )
    wait_for_terminal(run_id, timeout_seconds=180)

    with Session(get_engine()) as s:
        run = s.exec(select(RunRecord).where(RunRecord.id == run_id)).one()
        assert run.status == RunStatus.COMPLETED, f"run status: {run.status}"

        nodes = s.exec(
            select(RunGraphNode).where(RunGraphNode.run_id == run_id)
        ).all()
        subtask_keys = sorted(n.task_key for n in nodes if n.level > 0)
        assert subtask_keys == sorted(EXPECTED_SUBTASK_KEYS), subtask_keys
        for n in nodes:
            assert n.status == TaskStatus.COMPLETED, f"{n.task_key}: {n.status}"

        muts = s.exec(
            select(RunGraphMutation)
            .where(RunGraphMutation.run_id == run_id)
            .order_by(RunGraphMutation.sequence)
        ).all()
        assert any(
            str(m.mutation_type).lower().endswith("add_subtask") for m in muts
        )

        resources = s.exec(
            select(RunResource).where(RunResource.run_id == run_id)
        ).all()
        assert len(resources) == 9, len(resources)

        evals = s.exec(
            select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
        ).all()
        assert len(evals) == 1 and evals[0].score == 1.0, evals

    result = subprocess.run(
        [
            "pnpm", "--dir", "ergon-dashboard", "exec",
            "playwright", "test",
            f"tests/e2e/{ENV}.smoke.spec.ts",
            "--project=chromium",
        ],
        env={
            **os.environ,
            "RUN_ID": str(run_id),
            "SMOKE_ENV": ENV,
            "SCREENSHOT_DIR": str(screenshot_dir),
            "PLAYWRIGHT_LIVE": "1",
            "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:3000",
            "ERGON_API_BASE_URL": "http://127.0.0.1:9000",
            "TEST_HARNESS_SECRET": os.environ.get("TEST_HARNESS_SECRET", "ci-secret"),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"Playwright failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
```

- [ ] **Step 33.2: Create the Playwright spec**

```typescript
// ergon-dashboard/tests/e2e/swebench-verified.smoke.spec.ts

import { expect, test } from "@playwright/test";

import { BackendHarnessClient } from "../helpers/testHarnessClient";

const RUN_ID = process.env.RUN_ID;
const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR ?? "/tmp/playwright";
const ERGON_API =
  process.env.ERGON_API_BASE_URL ?? "http://127.0.0.1:9000";

test.skip(!RUN_ID, "RUN_ID env var required (populated by pytest driver)");

test("canonical smoke — dashboard renders expected run", async ({
  request,
  page,
}) => {
  const harness = new BackendHarnessClient(request, ERGON_API);
  const state = await harness.getRunState(RUN_ID!);
  expect(state.status).toBe("completed");
  expect(state.graph_nodes.filter((n) => n.level > 0)).toHaveLength(9);

  await page.goto(`/run/${RUN_ID}`);
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  const nodes = page.getByTestId(/^graph-node-/);
  await expect(nodes).toHaveCount(10);

  await page.screenshot({
    path: `${SCREENSHOT_DIR}/dashboard-full.png`,
    fullPage: true,
  });
  await page.getByTestId("graph-canvas").screenshot({
    path: `${SCREENSHOT_DIR}/graph.png`,
  });

  await page.goto("/");
  await expect(page.getByTestId("cohort-index-list")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/cohort.png`,
  });
});
```

- [ ] **Step 33.3: Type-check + commit**

```bash
pnpm --dir ergon-dashboard exec tsc --noEmit
git add tests/e2e/test_swebench_verified_smoke.py \
        ergon-dashboard/tests/e2e/swebench-verified.smoke.spec.ts
git commit -m "feat(e2e/swebench): pytest + Playwright spec for canonical smoke"
```

---

## Task 34 — Extend CI matrix with swebench-verified

**Files:**
- Modify: `.github/workflows/e2e-benchmarks.yml`

- [ ] **Step 34.1: Add to matrix**

```diff
     strategy:
       fail-fast: false
       matrix:
-        env: [researchrubrics, minif2f]  # PR 4 adds swebench-verified
+        env: [researchrubrics, minif2f, swebench-verified]
```

- [ ] **Step 34.2: Yaml-lint + commit**

```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/e2e-benchmarks.yml'))"
git add .github/workflows/e2e-benchmarks.yml
git commit -m "ci(e2e): add swebench-verified to the smoke matrix"
```

---

## Task 35 — Architecture doc: `06_builtins.md`

**Files:**
- Modify: `docs/architecture/06_builtins.md`

- [ ] **Step 35.1: Read the current §4 invariant**

```bash
grep -n -A 10 "^## 4\|^### 4" docs/architecture/06_builtins.md | head -40
```

- [ ] **Step 35.2: Rewrite the §4 invariant**

Locate the invariant that reads roughly "Every benchmark MUST ship a stub worker …" and replace with:

```markdown
**Invariant (canonical smoke contract):** Every benchmark MUST ship a
`SmokeSubworker` implementation plus a `SmokeCriterion` subclass, and MUST
register the `smoke-leaf` binding in its composition. The parent worker is
shared (`canonical-smoke`); only the leaf subworker and criterion content
assertions are env-specific. See
[`docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md`].
```

Verify the file reference: once this RFC moves to `accepted/` (Task 37), the link target will be valid.

- [ ] **Step 35.3: Commit**

```bash
git add docs/architecture/06_builtins.md
git commit -m "docs(arch/06): replace stub-worker invariant with SmokeSubworker + SmokeCriterion contract"
```

---

## Task 36 — Architecture doc: `07_testing.md`

**Files:**
- Modify: `docs/architecture/07_testing.md`

- [ ] **Step 36.1: Update §2 (code map)**

Under the e2e-tier entry, ensure the file-pattern reads:

```markdown
- `tests/e2e/test_{env}_smoke.py` — per-env canonical smoke (Python driver; invokes Playwright as subprocess).
- `ergon-dashboard/tests/e2e/{env}.smoke.spec.ts` — per-env Playwright spec for dashboard assertion + screenshot capture.
- `tests/e2e/conftest.py` — shared helpers (`run_benchmark`, `wait_for_terminal`, screenshot upload finalizer).
```

- [ ] **Step 36.2: Update §3 (trigger policy)**

Replace any "feature/* only" trigger policy for e2e with:

```markdown
- **Canonical smoke tier**: runs on every PR (see `.github/workflows/e2e-benchmarks.yml`).
- **Full-stack benchmark e2e (non-smoke)**: runs on `feature/*` branches.
```

- [ ] **Step 36.3: Add §4 invariant**

```markdown
**Invariant (canonical smoke completeness):** The envs in
`{researchrubrics, minif2f, swebench-verified}` have exactly one canonical
smoke pair each (Python + Playwright). The CI matrix in
`.github/workflows/e2e-benchmarks.yml` must include all three envs with
`fail-fast: false`. Expansion to additional envs requires adding the env to
the matrix, a `SmokeSubworker`, a `SmokeCriterion` subclass, a pytest
`test_{env}_smoke.py`, a Playwright `{env}.smoke.spec.ts`, and a composition
binding for `smoke-leaf`.
```

- [ ] **Step 36.4: Commit**

```bash
git add docs/architecture/07_testing.md
git commit -m "docs(arch/07): update testing tier map + trigger policy + canonical-smoke invariant"
```

---

## Task 37 — Architecture doc: `05_dashboard.md` + `01_public_api.md` + move RFC

**Files:**
- Modify: `docs/architecture/05_dashboard.md`
- Modify: `docs/architecture/01_public_api.md`
- Move: `docs/rfcs/active/2026-04-21-e2e-smoke-coverage-rewrite.md` → `docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md`

- [ ] **Step 37.1: Add dashboard invariant**

Append to the dashboard invariants section of `docs/architecture/05_dashboard.md`:

```markdown
**Invariant (canonical smoke dashboard rendering):** Every run produced by
the `canonical-smoke` worker renders in the dashboard with exactly 10 graph
nodes (1 root + 9 subtasks) and must reach `completed` status. The
canonical-smoke Playwright specs
(`ergon-dashboard/tests/e2e/{env}.smoke.spec.ts`) enforce this on every PR.
```

- [ ] **Step 37.2: Add public-API section**

Append a new section to `docs/architecture/01_public_api.md`:

```markdown
## Test-only extension points

The `/api/test/*` router is **not part of the public API**. It is mounted
only when `ENABLE_TEST_HARNESS=1` at server startup and is intended for
automated test drivers (Playwright + pytest). Write endpoints require the
`X-Test-Secret` header. See
[`docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md`] §"Test-harness
endpoints".
```

- [ ] **Step 37.3: Move the RFC**

```bash
mkdir -p docs/rfcs/accepted
git mv docs/rfcs/active/2026-04-21-e2e-smoke-coverage-rewrite.md \
       docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md
```

Edit the moved file's frontmatter: `status: active` → `status: accepted`.

- [ ] **Step 37.4: Commit**

```bash
git add docs/architecture/05_dashboard.md \
        docs/architecture/01_public_api.md \
        docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md \
        docs/rfcs/active/2026-04-21-e2e-smoke-coverage-rewrite.md
git commit -m "docs(arch): canonical-smoke dashboard + public-API invariants; accept e2e-smoke RFC"
```

---

## Task 38 — Push PR 4 and verify

- [ ] **Step 38.1: Push + open PR**

```bash
git push -u origin feature/smoke-swebench
gh pr create --title "feat(e2e/swebench): canonical smoke + arch-doc updates + RFC acceptance (PR 4 of 4)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `swebench-verified` to the canonical smoke matrix (third and final env).
- Updates `docs/architecture/06_builtins.md`, `07_testing.md`, `05_dashboard.md`, `01_public_api.md` per the RFC's §"Invariants affected".
- Moves the RFC from `active/` to `accepted/`.

## Test plan
- [x] Unit suite green.
- [ ] CI matrix green for all 3 envs on this PR.
- [ ] Inline screenshot comments posted for all 3 envs on this PR.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 38.2: Verify CI + comments**

Confirm all 3 matrix jobs green and the PR has 3 inline-screenshot comments (one per env) showing dashboard / graph / cohort images.

- [ ] **Step 38.3: Merge**

```bash
gh pr merge feature/smoke-swebench --squash --delete-branch
```

---

## Task 39 — Post-merge housekeeping

- [ ] **Step 39.1: Confirm `screenshots/pr-*` refs don't pile up**

```bash
git ls-remote origin 'refs/heads/screenshots/*' | head
```

Open PRs should have a ref; closed PRs should not.

- [ ] **Step 39.2: If `docs/bugs/open/2026-04-18-ci-docker-caching.md` is not already moved to `fixed/`, move it**

```bash
ls docs/bugs/open/2026-04-18-ci-docker-caching.md 2>/dev/null && \
  git mv docs/bugs/open/2026-04-18-ci-docker-caching.md docs/bugs/fixed/ && \
  git commit -m "docs(bug): ci-docker-caching fixed as part of reset+e2e RFCs"
```

- [ ] **Step 39.3: Close the plan**

Mark this plan's tracking issue (if any) closed. Verify no followup tasks are needed before declaring complete.

---

## Global checks run at end of each PR

Every PR MUST leave these green before merging:

```bash
pnpm run check:fast          # ruff + ty + slopcop + eslint + tsc
uv run pytest tests/unit -v  # unit suite
# Plus: the relevant CI e2e smoke job(s) green on the PR itself.
```

If any fail, fix with additional commits on the branch — never `--amend` or `--no-verify`.

---

## Appendix — Troubleshooting

### `ModuleNotFoundError` on a new import

Most commonly a missing package marker — add `__init__.py` at each intermediate level.

### Playwright `getByTestId` finds zero elements

The dashboard source may use a different attribute (`data-test-id` vs `data-testid`) or different strings. Grep:

```bash
grep -rn "data-testid\|data-test-id\|testId=" ergon-dashboard/src/ | head
```

Update the Playwright spec to match the actual selectors.

### Screenshot ref push denied

Check that `permissions:` in the workflow includes `contents: write`. GitHub rulesets may also block pushes to custom refs — if so, either adjust the ruleset (preferred) or switch to uploading screenshots as a CI artifact and linking the artifact URL in the PR comment (fallback).

### 5-minute budget exceeded

First run: expect this; tune. If consistently over:
1. Check Docker layer-cache hit rate in the workflow logs.
2. Profile the individual phases (`time uv run pytest ...`).
3. If the sandbox provisioning is the bottleneck, raise the budget; don't cut corners on coverage.
