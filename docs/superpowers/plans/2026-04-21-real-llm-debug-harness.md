# Real-LLM debug harness — Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the real-LLM debug harness described in
`docs/rfcs/active/2026-04-21-real-llm-debug-harness.md` — a pytest tier at
`tests/real_llm/` that runs real Sonnet-4.6-via-OpenRouter experiments,
asserts Postgres + Playwright, and is used as a bug-hunting instrument to
validate the three benchmark sandboxes end-to-end.

**Architecture:** Generic ReAct worker (`react-generic` slug) + per-benchmark
DI'd toolkit via `benchmark_toolkit_composer`. Tests drive the shipped
`ergon benchmark run` CLI via subprocess against a full local stack
(`docker-compose.real-llm.yml`) with a `--assume-stack-up` escape for dev
iteration. OpenRouter cost-gated; Playwright dashboard assertions must-have.

**Tech Stack:** pytest, `httpx`, Playwright (async), Docker Compose, Ergon CLI,
`ergon_core.core.providers.generation.openrouter_budget` (new), `ergon_builtins.tools.benchmark_toolkit_composer` (new).

**Rollout:** This plan covers **PR 1 only** (Tasks 0–10). PR 2 (three-example
artifact) and the bug-hunt phase between them are driven by the RFC but run
as follow-ups on top of a merged PR 1.

---

## Preconditions

- `smoke-shared-infra` PR #25 **merged to `main`** — the `/api/test/*`
  harness endpoints this plan polls are from that PR. If #25 is not yet
  merged, **stop** and wait; do not proceed on a branched-off-PR-25 strategy
  (merge conflicts multiply). This plan's branch is
  `feature/real-llm-harness-infra` off a `main` that already contains #25.

## Task 0 — Preflight

**Files:** none yet.

- [ ] **Step 0.1: Verify smoke-shared-infra PR is merged**

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
git fetch origin main
git log origin/main --oneline | head -20 | grep -E "smoke shared infra|api/test" || {
  echo "PR #25 not merged yet — stop here."
  exit 1
}
```

Expected: at least one line matches, confirming the harness endpoints are on
main. If not, stop and wait.

- [ ] **Step 0.2: Branch off main**

```bash
git checkout main
git pull origin main
git checkout -b feature/real-llm-harness-infra
```

- [ ] **Step 0.3: Sanity-check the harness endpoints are present on main**

```bash
ls ergon_core/ergon_core/core/api/test_harness.py
grep -c "write/run/seed\|read/run\|write/reset" ergon_core/ergon_core/core/api/test_harness.py
```

Expected: file exists, ≥3 matches for the endpoint route strings.

---

## Task 1 — OpenRouter budget gate module

**Files:**
- Create: `ergon_core/ergon_core/core/providers/generation/openrouter_budget.py`
- Test: `tests/unit/test_openrouter_budget.py`

Budget module is fully testable without any real API key — just mock
`httpx.AsyncClient.get`. TDD first.

- [ ] **Step 1.1: Write the failing test**

```python
# tests/unit/test_openrouter_budget.py
"""OpenRouterBudget: snapshot baseline, compute delta, gate spend."""

from unittest.mock import AsyncMock, patch

import pytest

from ergon_core.core.providers.generation.openrouter_budget import OpenRouterBudget


@pytest.mark.asyncio
async def test_remaining_usd_returns_limit_minus_delta() -> None:
    budget = OpenRouterBudget(limit_usd=5.0, api_key="test-key")

    async def _mock_get(*_args: object, **_kwargs: object) -> object:
        class _Resp:
            status_code = 200
            def raise_for_status(self) -> None:
                return None
            def json(self) -> dict[str, object]:
                return {"data": {"usage": 2.50, "limit": 100.0, "limit_remaining": 97.50}}
        return _Resp()

    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=_mock_get)):
        await budget.snapshot_baseline()

        # usage is same as baseline on first call => spent 0, remaining = limit
        assert (await budget.remaining_usd()) == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_remaining_usd_after_spend() -> None:
    budget = OpenRouterBudget(limit_usd=5.0, api_key="test-key")

    # First call sets baseline at usage=2.50; second call reports usage=3.70;
    # delta is 1.20; remaining = 5.0 - 1.20 = 3.80.
    usages = iter([2.50, 3.70])

    async def _mock_get(*_args: object, **_kwargs: object) -> object:
        next_usage = next(usages)

        class _Resp:
            status_code = 200
            def raise_for_status(self) -> None:
                return None
            def json(self) -> dict[str, object]:
                return {"data": {"usage": next_usage, "limit": 100.0, "limit_remaining": 97.5}}
        return _Resp()

    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=_mock_get)):
        await budget.snapshot_baseline()
        assert (await budget.remaining_usd()) == pytest.approx(3.80)


@pytest.mark.asyncio
async def test_remaining_usd_raises_without_snapshot() -> None:
    budget = OpenRouterBudget(limit_usd=5.0, api_key="test-key")

    with pytest.raises(RuntimeError, match="baseline"):
        await budget.remaining_usd()
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_openrouter_budget.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named
'ergon_core.core.providers.generation.openrouter_budget'`.

- [ ] **Step 1.3: Write the module**

```python
# ergon_core/ergon_core/core/providers/generation/openrouter_budget.py
"""Track cumulative OpenRouter spend against a per-session budget.

Usage:
    budget = OpenRouterBudget(limit_usd=5.0, api_key=os.environ["OPENROUTER_API_KEY"])
    await budget.snapshot_baseline()  # at pytest session start
    ...
    if await budget.remaining_usd() <= 0:
        pytest.skip("OpenRouter budget exhausted")
"""

import httpx


_KEY_ENDPOINT = "https://openrouter.ai/api/v1/auth/key"


class OpenRouterBudget:
    """Snapshot cumulative OpenRouter spend and compare against a limit."""

    def __init__(self, *, limit_usd: float, api_key: str) -> None:
        self._limit = limit_usd
        self._api_key = api_key
        self._baseline: float | None = None

    async def snapshot_baseline(self) -> None:
        self._baseline = await self._current_usage()

    async def remaining_usd(self) -> float:
        if self._baseline is None:
            raise RuntimeError("snapshot_baseline must be called before remaining_usd")
        current = await self._current_usage()
        return self._limit - (current - self._baseline)

    async def _current_usage(self) -> float:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _KEY_ENDPOINT,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            resp.raise_for_status()
            return float(resp.json()["data"]["usage"])
```

- [ ] **Step 1.4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_openrouter_budget.py -v
```

Expected: 3 passed.

- [ ] **Step 1.5: Commit**

```bash
git add ergon_core/ergon_core/core/providers/generation/openrouter_budget.py \
        tests/unit/test_openrouter_budget.py
git commit -m "feat(budget): OpenRouterBudget snapshot + delta gate (module + unit tests)"
```

---

## Task 2 — `benchmark_toolkit_composer` module

**Files:**
- Create: `ergon_builtins/ergon_builtins/tools/benchmark_toolkit_composer.py`
- Test: `tests/unit/test_benchmark_toolkit_composer.py`

The composer takes `benchmark_slug`, `ctx: WorkerContext`, and `sandbox`
and returns the union of tools a generic ReAct worker needs for that
benchmark. **Does not** construct tools that require live sandbox skills —
returns callable protocols that will be satisfied at execute time.

- [ ] **Step 2.1: Write the failing test**

```python
# tests/unit/test_benchmark_toolkit_composer.py
"""benchmark_toolkit_composer: per-benchmark DI factory for generic ReAct."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from ergon_builtins.tools.benchmark_toolkit_composer import compose_benchmark_toolkit


def _make_ctx() -> SimpleNamespace:
    return SimpleNamespace(
        run_id=uuid4(),
        node_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sb-test",
        task_id=uuid4(),
        definition_id=None,
        metadata={},
    )


def test_compose_researchrubrics_unions_lifecycle_rr_and_graph() -> None:
    tools = compose_benchmark_toolkit(
        benchmark_slug="researchrubrics",
        ctx=_make_ctx(),
        sandbox=MagicMock(),
        run_skill=MagicMock(),
        publisher_sync=MagicMock(),
    )
    # Minimum union size: 8 (lifecycle) + 6 (rr) + 6 (graph) = 20
    assert len(tools) >= 20


def test_compose_minif2f_unions_lifecycle_and_minif2f() -> None:
    tools = compose_benchmark_toolkit(
        benchmark_slug="minif2f",
        ctx=_make_ctx(),
        sandbox=MagicMock(),
    )
    # Minimum: 8 (lifecycle) + Lean toolkit (≥5) = 13
    assert len(tools) >= 13


def test_compose_swebench_unions_lifecycle_and_swebench() -> None:
    tools = compose_benchmark_toolkit(
        benchmark_slug="swebench-verified",
        ctx=_make_ctx(),
        sandbox=MagicMock(),
    )
    # Minimum: 8 (lifecycle) + bash + str-replace = 10
    assert len(tools) >= 10


def test_compose_unknown_slug_raises() -> None:
    with pytest.raises(ValueError, match="no toolkit composer for"):
        compose_benchmark_toolkit(
            benchmark_slug="unknown",
            ctx=_make_ctx(),
            sandbox=MagicMock(),
        )
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_benchmark_toolkit_composer.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 2.3: Write the module**

```python
# ergon_builtins/ergon_builtins/tools/benchmark_toolkit_composer.py
"""Per-benchmark DI factory — unions `SubtaskLifecycleToolkit` with the
env-specific toolkit so a single generic ReAct worker can exercise any
of the three target benchmarks."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class _HasContextFields(Protocol):
    run_id: Any  # slopcop: ignore[no-typing-any]
    node_id: Any  # slopcop: ignore[no-typing-any]
    execution_id: Any  # slopcop: ignore[no-typing-any]
    sandbox_id: str


def compose_benchmark_toolkit(
    *,
    benchmark_slug: str,
    ctx: _HasContextFields,
    sandbox: Any,  # slopcop: ignore[no-typing-any]
    run_skill: Callable[..., Awaitable[Any]] | None = None,  # slopcop: ignore[no-typing-any]
    publisher_sync: Callable[[], Awaitable[list[Any]]] | None = None,  # slopcop: ignore[no-typing-any]
) -> list[Any]:  # slopcop: ignore[no-typing-any]
    """Return the union of Tools a generic ReAct worker needs for benchmark_slug."""
    from ergon_builtins.tools.subtask_lifecycle_toolkit import SubtaskLifecycleToolkit

    lifecycle = SubtaskLifecycleToolkit(
        run_id=ctx.run_id,
        parent_node_id=ctx.node_id,
        sandbox_id=ctx.sandbox_id,
    ).get_tools()

    match benchmark_slug:
        case "researchrubrics":
            from ergon_builtins.tools.graph_toolkit import ResearchGraphToolkit
            from ergon_builtins.tools.research_rubrics_toolkit import (
                ResearchRubricsToolkit,
            )

            if run_skill is None or publisher_sync is None:
                raise ValueError(
                    "researchrubrics composer requires run_skill + publisher_sync"
                )
            rr = ResearchRubricsToolkit(
                run_skill=run_skill,
                publisher_sync=publisher_sync,
            ).build_tools()
            graph = ResearchGraphToolkit(
                run_id=ctx.run_id,
                task_execution_id=ctx.execution_id,
            ).build_tools()
            return [*lifecycle, *rr, *graph]
        case "minif2f":
            from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit

            return [*lifecycle, *MiniF2FToolkit(sandbox=sandbox).get_tools()]
        case "swebench-verified":
            from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit

            return [*lifecycle, *SWEBenchToolkit(sandbox=sandbox).get_tools()]
        case _:
            raise ValueError(f"no toolkit composer for {benchmark_slug!r}")
```

- [ ] **Step 2.4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_benchmark_toolkit_composer.py -v
```

Expected: 4 passed. If the existing toolkits raise at `get_tools()` /
`build_tools()` because of missing `pydantic_ai.tools.Tool`, the test
environment already has pydantic-ai; confirm by `uv pip list | grep pydantic-ai`.

- [ ] **Step 2.5: Commit**

```bash
git add ergon_builtins/ergon_builtins/tools/benchmark_toolkit_composer.py \
        tests/unit/test_benchmark_toolkit_composer.py
git commit -m "feat(tools): benchmark_toolkit_composer DI factory (3 envs + unit tests)"
```

---

## Task 3 — `ReActGenericWorker` + registration

**Files:**
- Create: `ergon_builtins/ergon_builtins/workers/baselines/react_generic_worker.py`
- Modify: `ergon_builtins/ergon_builtins/registry_core.py:47` (add `"react-generic"` to WORKERS)
- Test: `tests/unit/test_react_generic_worker.py`

Thin subclass of `ReActWorker` that reads its benchmark slug from
`ctx.metadata["toolkit_benchmark"]`, composes the toolkit at execute-time
against the live sandbox, and delegates to `super().execute()`. Pattern
mirrors `minif2f_react_worker.py`.

- [ ] **Step 3.1: Write the failing test**

```python
# tests/unit/test_react_generic_worker.py
"""ReActGenericWorker: composes toolkit from ctx.metadata['toolkit_benchmark']."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_builtins.workers.baselines.react_generic_worker import ReActGenericWorker


def _ctx(benchmark_slug: str) -> SimpleNamespace:
    return SimpleNamespace(
        run_id=uuid4(),
        node_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sb-test",
        task_id=uuid4(),
        definition_id=None,
        metadata={"toolkit_benchmark": benchmark_slug},
    )


@pytest.mark.asyncio
async def test_execute_composes_toolkit_from_metadata_for_swebench() -> None:
    worker = ReActGenericWorker(name="w", model="x")
    ctx = _ctx("swebench-verified")
    fake_sandbox = MagicMock()

    called: dict[str, object] = {}

    def _spy(**kwargs: object) -> list[object]:
        called.update(kwargs)
        return ["tool-a", "tool-b"]

    # Patch both sandbox-connect and the composer. The worker must yield at
    # least once; we short-circuit super().execute by monkeypatching ReActWorker.
    with (
        patch(
            "ergon_builtins.workers.baselines.react_generic_worker.AsyncSandbox.connect",
            AsyncMock(return_value=fake_sandbox),
        ),
        patch(
            "ergon_builtins.workers.baselines.react_generic_worker.compose_benchmark_toolkit",
            side_effect=_spy,
        ),
        patch.object(
            ReActGenericWorker.__mro__[1],
            "execute",
            return_value=_async_iter([]),
        ),
    ):
        _turns = [t async for t in worker.execute(task=None, context=ctx)]

    assert called["benchmark_slug"] == "swebench-verified"
    assert worker.tools == ["tool-a", "tool-b"]


def _async_iter(items: list[object]) -> object:
    async def _gen():
        for i in items:
            yield i
    return _gen()


def test_raises_if_metadata_missing_toolkit_benchmark() -> None:
    worker = ReActGenericWorker(name="w", model="x")
    ctx = SimpleNamespace(
        run_id=uuid4(),
        node_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sb-test",
        task_id=uuid4(),
        definition_id=None,
        metadata={},
    )
    with pytest.raises(ValueError, match="toolkit_benchmark"):
        worker._benchmark_slug(ctx)
```

- [ ] **Step 3.2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_react_generic_worker.py -v
```

Expected: FAIL (module not found).

- [ ] **Step 3.3: Write the module**

```python
# ergon_builtins/ergon_builtins/workers/baselines/react_generic_worker.py
"""Generic ReAct worker that composes its toolkit per benchmark from metadata.

Reads `ctx.metadata["toolkit_benchmark"]` at execute() time, opens the
sandbox, calls `compose_benchmark_toolkit(...)`, stashes the result on
`self.tools`, and delegates to `super().execute()`.

Intended for the real-LLM debug harness; validates that `ReActWorker` +
the three composed toolkits behave correctly end-to-end against a real
model, without us having to maintain per-benchmark specialised workers.
"""

from collections.abc import AsyncGenerator
from typing import Any

from e2b_code_interpreter import AsyncSandbox

from ergon_core.api import BenchmarkTask, WorkerContext, WorkerOutput
from ergon_core.api.generation import GenerationTurn

from ergon_builtins.tools.benchmark_toolkit_composer import compose_benchmark_toolkit
from ergon_builtins.workers.baselines.react_worker import ReActWorker


class ReActGenericWorker(ReActWorker):
    type_slug = "react-generic"

    def _benchmark_slug(self, ctx: WorkerContext) -> str:
        slug = ctx.metadata.get("toolkit_benchmark") if ctx.metadata else None
        if not isinstance(slug, str) or not slug:
            raise ValueError(
                "ReActGenericWorker requires ctx.metadata['toolkit_benchmark']"
            )
        return slug

    async def execute(
        self,
        task: BenchmarkTask | None,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        slug = self._benchmark_slug(context)
        sandbox: Any = await AsyncSandbox.connect(context.sandbox_id)  # slopcop: ignore[no-typing-any]

        # For researchrubrics we'd also need run_skill + publisher_sync; leave
        # None-default and let the composer raise if that branch is hit without
        # them being wired at a higher layer. PR 2 adds the wiring.
        self.tools = compose_benchmark_toolkit(
            benchmark_slug=slug,
            ctx=context,
            sandbox=sandbox,
        )

        async for turn in super().execute(task, context=context):
            yield turn
```

- [ ] **Step 3.4: Register**

Modify `ergon_builtins/ergon_builtins/registry_core.py` at line 47-56
(`WORKERS` dict). Add import:

```python
from ergon_builtins.workers.baselines.react_generic_worker import ReActGenericWorker
```

And add to the dict:

```python
    "react-generic": ReActGenericWorker,
```

- [ ] **Step 3.5: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_react_generic_worker.py -v
uv run pytest tests/unit/ -k "registry or react_generic" -v
```

Expected: all green.

- [ ] **Step 3.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/workers/baselines/react_generic_worker.py \
        ergon_builtins/ergon_builtins/registry_core.py \
        tests/unit/test_react_generic_worker.py
git commit -m "feat(worker): ReActGenericWorker reads toolkit_benchmark from ctx.metadata"
```

---

## Task 4 — CLI wiring: `--toolkit-benchmark` flag

**Files:**
- Modify: `ergon_cli/ergon_cli/commands/benchmark.py` (add CLI arg; pass as metadata)
- Modify: `ergon_cli/ergon_cli/composition/__init__.py` (honour metadata→worker)
- Test: `tests/unit/test_cli_react_generic_composition.py`

`build_experiment` already resolves `worker_slug` from the registry. We need
to pipe a `toolkit_benchmark: str` value into `Experiment.metadata` so that,
when the runtime calls `worker.execute(task, context)`, `context.metadata`
contains `toolkit_benchmark`. The simplest wiring: add a kwarg to
`build_experiment`, route it onto each `BenchmarkTask.metadata`.

- [ ] **Step 4.1: Write the failing test**

```python
# tests/unit/test_cli_react_generic_composition.py
"""Smoke: build_experiment(worker=react-generic, toolkit_benchmark=...) puts
the slug into BenchmarkTask metadata so ReActGenericWorker can read it."""

from ergon_cli.composition import build_experiment


def test_react_generic_toolkit_benchmark_propagates_into_task_metadata() -> None:
    exp = build_experiment(
        benchmark_slug="smoke-test",
        model="stub:constant",
        worker_slug="react-generic",
        evaluator_slug="stub-rubric",
        toolkit_benchmark="swebench-verified",
        limit=1,
    )
    instances = exp.benchmark.build_instances()
    tasks = [t for tasks_for_cohort in instances.values() for t in tasks_for_cohort]
    assert tasks, "benchmark produced no tasks"
    assert all(
        t.metadata.get("toolkit_benchmark") == "swebench-verified" for t in tasks
    )
```

- [ ] **Step 4.2: Run to verify failure**

```bash
uv run pytest tests/unit/test_cli_react_generic_composition.py -v
```

Expected: FAIL — `build_experiment()` has no `toolkit_benchmark` kwarg.

- [ ] **Step 4.3: Add the kwarg in composition**

In `ergon_cli/ergon_cli/composition/__init__.py`:

- Add `toolkit_benchmark: str | None = None` to `build_experiment` signature.
- After `benchmark = _construct_benchmark(...)`, if `toolkit_benchmark` is
  not None, walk `benchmark.build_instances()` and mutate each
  `BenchmarkTask.metadata["toolkit_benchmark"] = toolkit_benchmark`.
- For `worker_slug == "react-generic"`, fall into the default
  `Experiment.from_single_worker(...)` branch (the existing catch-all
  already handles it once the worker is in WORKERS).

Smallest diff shape (inside the `_` catch-all case before
`Experiment.from_single_worker`):

```python
if toolkit_benchmark is not None:
    for tasks in benchmark.build_instances().values():
        for task in tasks:
            # BenchmarkTask is immutable where it's a frozen model; fall back
            # to the mutable metadata dict.
            task.metadata["toolkit_benchmark"] = toolkit_benchmark
```

(If `BenchmarkTask.metadata` is frozen in your build, construct new tasks;
inspect `ergon_core/api/task_types.py` and adapt.)

- [ ] **Step 4.4: Expose on the CLI**

In `ergon_cli/ergon_cli/commands/benchmark.py`, find the
`benchmark run` arg parser section and add:

```python
parser.add_argument(
    "--toolkit-benchmark",
    default=None,
    help="When --worker=react-generic, which benchmark's toolkit to compose.",
)
```

And pass `toolkit_benchmark=args.toolkit_benchmark` into the
`build_experiment(...)` call.

- [ ] **Step 4.5: Run tests**

```bash
uv run pytest tests/unit/test_cli_react_generic_composition.py tests/cli -v
```

Expected: new test passes; existing CLI tests unaffected.

- [ ] **Step 4.6: Commit**

```bash
git add ergon_cli/ergon_cli/commands/benchmark.py \
        ergon_cli/ergon_cli/composition/__init__.py \
        tests/unit/test_cli_react_generic_composition.py
git commit -m "feat(cli): --toolkit-benchmark flag propagates into task metadata"
```

---

## Task 5 — `tests/real_llm/` scaffolding + conftest

**Files:**
- Create: `tests/real_llm/__init__.py` (empty)
- Create: `tests/real_llm/conftest.py`
- Modify: `pyproject.toml` to register `real_llm` pytest marker

- [ ] **Step 5.1: Create empty package marker**

```bash
mkdir -p tests/real_llm
touch tests/real_llm/__init__.py
```

- [ ] **Step 5.2: Add marker to `pyproject.toml`**

Find the `[tool.pytest.ini_options]` block (currently contains `markers =
[...]` with `integration`, etc.). Add:

```toml
    "real_llm: real-LLM end-to-end tests (requires ERGON_REAL_LLM=1 + OPENROUTER_API_KEY)",
```

- [ ] **Step 5.3: Write the conftest**

```python
# tests/real_llm/conftest.py
"""Session-level fixtures for the real-LLM tier.

Gates:
  - ERGON_REAL_LLM=1 must be set (else the entire tier skips).
  - OPENROUTER_API_KEY must be set (else real-LLM tests skip; stub canary
    continues to run if it opts in explicitly).
  - --assume-stack-up flag skips the docker-compose fixture and trusts the
    developer to have the stack running (pnpm dev:test + postgres + inngest
    + fastapi).

Session fixtures (docker stack, OpenRouter budget) live here; per-benchmark
fixtures live inside each test module.
"""

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--assume-stack-up",
        action="store_true",
        default=False,
        help="Skip docker-compose fixture; trust the developer to have the "
        "full stack (dashboard + backend + postgres + inngest) running.",
    )


@pytest.fixture(scope="session")
def real_llm_enabled() -> bool:
    return os.environ.get("ERGON_REAL_LLM") == "1"


@pytest.fixture(autouse=True)
def _skip_if_not_enabled(real_llm_enabled: bool, request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("real_llm") and not real_llm_enabled:
        pytest.skip("ERGON_REAL_LLM=1 not set; real-LLM tier is opt-in")
```

- [ ] **Step 5.4: Confirm discovery**

```bash
uv run pytest tests/real_llm --collect-only
```

Expected: 0 tests collected (no test files yet), no errors.

- [ ] **Step 5.5: Commit**

```bash
git add tests/real_llm/__init__.py tests/real_llm/conftest.py pyproject.toml
git commit -m "feat(real-llm): tests/real_llm scaffolding + pytest marker + conftest"
```

---

## Task 6 — `docker-compose.real-llm.yml` + stack fixture

**Files:**
- Create: `docker-compose.real-llm.yml`
- Create: `tests/real_llm/fixtures/__init__.py`
- Create: `tests/real_llm/fixtures/stack.py`

Overlay includes Postgres, Inngest, FastAPI (ENABLE_TEST_HARNESS=1), and a
headed `pnpm dev:test` dashboard — everything the harness polls / probes /
Playwright-asserts.

- [ ] **Step 6.1: Write the compose file**

```yaml
# docker-compose.real-llm.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ergon
      POSTGRES_PASSWORD: ergon
      POSTGRES_DB: ergon
    ports: ["5433:5432"]
  inngest:
    image: inngest/inngest:latest
    command: inngest dev --port 8288
    ports: ["8288:8288"]
  api:
    build: { context: ., dockerfile: infra/Dockerfile.api }
    environment:
      DATABASE_URL: postgres://ergon:ergon@postgres:5432/ergon
      ENABLE_TEST_HARNESS: "1"
      TEST_HARNESS_SECRET: "real-llm-secret"
      INNGEST_DEV: "http://inngest:8288"
      ERGON_API_BASE_URL: "http://api:9000"
    depends_on: [postgres, inngest]
    ports: ["9000:9000"]
  dashboard:
    build: { context: ergon-dashboard, dockerfile: Dockerfile.test }
    environment:
      ERGON_API_BASE_URL: "http://api:9000"
      ENABLE_TEST_HARNESS: "1"
    depends_on: [api]
    ports: ["3101:3101"]
```

(Note: if `infra/Dockerfile.api` and `ergon-dashboard/Dockerfile.test` do
not yet exist, create minimal stubs based on the repo's existing compose
files; run `ls infra/` + `ls ergon-dashboard/` first to discover.)

- [ ] **Step 6.2: Write the stack fixture**

```python
# tests/real_llm/fixtures/stack.py
"""docker-compose up/down session fixture with --assume-stack-up flag."""

import subprocess
import time
from collections.abc import Generator

import httpx
import pytest

_COMPOSE_FILE = "docker-compose.real-llm.yml"
_API_URL = "http://127.0.0.1:9000"
_DASHBOARD_URL = "http://127.0.0.1:3101"
_UP_TIMEOUT_S = 120


def _wait_for(url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=2.0) as client:
                client.get(url)
            return
        except (httpx.ConnectError, httpx.ReadTimeout):
            time.sleep(2.0)
    raise RuntimeError(f"timed out waiting for {url}")


@pytest.fixture(scope="session")
def real_llm_stack(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    if request.config.getoption("--assume-stack-up"):
        _wait_for(f"{_API_URL}/health", 10)
        _wait_for(f"{_DASHBOARD_URL}", 10)
        yield
        return

    subprocess.run(
        ["docker", "compose", "-f", _COMPOSE_FILE, "up", "-d", "--wait"],
        check=True,
    )
    try:
        _wait_for(f"{_API_URL}/health", _UP_TIMEOUT_S)
        _wait_for(f"{_DASHBOARD_URL}", _UP_TIMEOUT_S)
        yield
    finally:
        subprocess.run(
            ["docker", "compose", "-f", _COMPOSE_FILE, "down", "-v"],
            check=False,
        )
```

- [ ] **Step 6.3: Smoke-test `--assume-stack-up` path**

With a local `pnpm dev:test` + backend already running (if you have one),
collect the fixture without running any real test:

```bash
uv run pytest tests/real_llm --collect-only --assume-stack-up
```

Expected: no errors; if no stack is up, the fixture isn't triggered by
collect-only anyway.

- [ ] **Step 6.4: Commit**

```bash
git add docker-compose.real-llm.yml tests/real_llm/fixtures/__init__.py \
        tests/real_llm/fixtures/stack.py
git commit -m "feat(real-llm): docker-compose overlay + stack session fixture"
```

---

## Task 7 — Budget + Playwright + harness client fixtures

**Files:**
- Create: `tests/real_llm/fixtures/openrouter_budget.py`
- Create: `tests/real_llm/fixtures/playwright_client.py`
- Create: `tests/real_llm/fixtures/harness_client.py` (Python twin of the TS `BackendHarnessClient`)

- [ ] **Step 7.1: Budget fixture**

```python
# tests/real_llm/fixtures/openrouter_budget.py
import os
from collections.abc import AsyncGenerator

import pytest

from ergon_core.core.providers.generation.openrouter_budget import OpenRouterBudget


@pytest.fixture(scope="session")
async def openrouter_budget() -> AsyncGenerator[OpenRouterBudget, None]:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY not set — skipping real-LLM tests")
    limit = float(os.environ.get("ERGON_REAL_LLM_BUDGET_USD", "5.0"))
    budget = OpenRouterBudget(limit_usd=limit, api_key=key)
    await budget.snapshot_baseline()
    yield budget


@pytest.fixture(autouse=True)
async def _budget_gate(openrouter_budget: OpenRouterBudget) -> None:
    remaining = await openrouter_budget.remaining_usd()
    if remaining <= 0:
        pytest.skip(f"OpenRouter budget exhausted (remaining=${remaining:.2f})")
```

- [ ] **Step 7.2: Harness client (Python, for `/api/test/read/run/*/state`)**

```python
# tests/real_llm/fixtures/harness_client.py
import os
from typing import Any

import httpx


class BackendHarnessClient:
    """Python twin of ergon-dashboard/tests/helpers/testHarnessClient.ts."""

    def __init__(self, base_url: str) -> None:
        self._base = base_url

    def get_run_state(self, run_id: str) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{self._base}/api/test/read/run/{run_id}/state")
            r.raise_for_status()
            return r.json()

    def wait_for_terminal(
        self, run_id: str, *, timeout_s: float = 600.0, poll_s: float = 3.0
    ) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        import time

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            state = self.get_run_state(run_id)
            if state["status"] in {"completed", "failed", "cancelled"}:
                return state
            time.sleep(poll_s)
        raise TimeoutError(f"run {run_id} did not reach terminal status in {timeout_s}s")


import pytest

@pytest.fixture
def harness_client() -> BackendHarnessClient:
    return BackendHarnessClient(
        os.environ.get("ERGON_API_BASE_URL", "http://127.0.0.1:9000")
    )
```

- [ ] **Step 7.3: Playwright client**

```python
# tests/real_llm/fixtures/playwright_client.py
import os
from collections.abc import AsyncGenerator

import pytest
from playwright.async_api import Browser, BrowserContext, async_playwright


@pytest.fixture(scope="session")
async def playwright_browser() -> AsyncGenerator[Browser, None]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        yield browser
        await browser.close()


@pytest.fixture
async def playwright_context(
    playwright_browser: Browser,
) -> AsyncGenerator[BrowserContext, None]:
    ctx = await playwright_browser.new_context(
        base_url=os.environ.get("ERGON_DASHBOARD_URL", "http://127.0.0.1:3101"),
    )
    yield ctx
    await ctx.close()
```

- [ ] **Step 7.4: Wire into conftest**

Edit `tests/real_llm/conftest.py` — append fixture imports so pytest finds
them:

```python
from tests.real_llm.fixtures.openrouter_budget import openrouter_budget, _budget_gate  # noqa: F401
from tests.real_llm.fixtures.harness_client import harness_client  # noqa: F401
from tests.real_llm.fixtures.playwright_client import playwright_browser, playwright_context  # noqa: F401
from tests.real_llm.fixtures.stack import real_llm_stack  # noqa: F401
```

- [ ] **Step 7.5: Collect-check**

```bash
uv run pytest tests/real_llm --collect-only
```

Expected: no import errors.

- [ ] **Step 7.6: Commit**

```bash
git add tests/real_llm/fixtures/ tests/real_llm/conftest.py
git commit -m "feat(real-llm): budget/harness/playwright fixtures wired into conftest"
```

---

## Task 8 — Canary: `test_smoke_stub.py`

**Files:**
- Create: `tests/real_llm/benchmarks/__init__.py` (empty)
- Create: `tests/real_llm/benchmarks/test_smoke_stub.py`

The canary uses the existing `smoke-test` benchmark with **stub workers** —
zero OpenRouter cost — to prove every layer of the harness wired correctly
(stack up, subprocess CLI, harness client, DB query, Playwright).

- [ ] **Step 8.1: Write the canary**

```python
# tests/real_llm/benchmarks/test_smoke_stub.py
"""Real-LLM harness canary — exercises the whole harness pipeline without
actually spending tokens. Uses the smoke-test benchmark + stub-worker path.

Validates:
  - docker stack up (or --assume-stack-up), stack fixture did not skip
  - `ergon benchmark run` CLI path works
  - /api/test/read/run/{id}/state returns a terminal state
  - Postgres row exists with the right relationships
  - Playwright can find the cohort in the dashboard
"""

import os
import subprocess
from uuid import UUID

import pytest

pytestmark = [pytest.mark.real_llm, pytest.mark.asyncio]


async def test_harness_canary_smoke_stub(
    real_llm_stack: None,
    harness_client,  # noqa: ANN001
    playwright_context,  # noqa: ANN001
) -> None:
    # Run the CLI as a user would.
    result = subprocess.run(
        [
            "uv", "run", "ergon", "benchmark", "run",
            "smoke-test",
            "--model", "stub:constant",
            "--worker", "stub-worker",
            "--evaluator", "stub-rubric",
            "--limit", "1",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"

    # CLI prints a JSON blob with run_id when --json is passed; parse it.
    import json
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    run_id = payload["run_id"]
    UUID(run_id)  # validate shape

    # Poll the harness until terminal.
    state = harness_client.wait_for_terminal(run_id, timeout_s=120)
    assert state["status"] == "completed", f"run did not complete: {state}"
    assert len(state["graph_nodes"]) >= 1

    # Playwright: cohort index renders, find the run row.
    page = await playwright_context.new_page()
    await page.goto("/")
    await page.wait_for_load_state("networkidle")
    # Loose assertion: the page rendered and didn't crash.
    assert "cohort" in (await page.content()).lower()
```

- [ ] **Step 8.2: Confirm `--json` flag exists on `ergon benchmark run`**

```bash
uv run ergon benchmark run --help 2>&1 | grep -- "--json" || {
  echo "NOTE: --json flag may not exist; adjust Step 8.1 to parse run_id from table output"
}
```

If it doesn't exist, fall back to querying the most recent run via
`/api/test/read` (requires a seed-by-cohort helper) **or** add a
`--json` flag to the CLI (small PR) — defer to Step 8.3.

- [ ] **Step 8.3: If no `--json` flag, extract run_id another way**

Acceptable alternatives, in order of preference:

1. Grep the CLI stdout for a UUID matching `RunRecord` created
   within the last 60s.
2. Query `get_session()` for the newest `RunRecord` by `created_at desc`
   and use that (in-process DB access is already used elsewhere in
   `tests/integration/`).

- [ ] **Step 8.4: Run the canary**

With a stack up (`docker compose -f docker-compose.real-llm.yml up -d` or
equivalent dev stack), run:

```bash
ERGON_REAL_LLM=1 uv run pytest tests/real_llm/benchmarks/test_smoke_stub.py -v
```

Expected: 1 passed. If any layer fails, iterate:
- subprocess timeout → check CLI path / stub registry
- harness 404 → confirm `ENABLE_TEST_HARNESS=1` set on API container
- Playwright can't reach dashboard → confirm port 3101 is exposed

- [ ] **Step 8.5: Commit**

```bash
git add tests/real_llm/benchmarks/__init__.py \
        tests/real_llm/benchmarks/test_smoke_stub.py
git commit -m "test(real-llm): canary smoke using stub workers (cost=0)"
```

---

## Task 9 — Architecture doc updates

**Files:**
- Modify: `docs/architecture/07_testing.md`
- Modify: `docs/architecture/06_builtins.md`

- [ ] **Step 9.1: Update testing doc**

Append a new row to the testing-tier matrix section in
`docs/architecture/07_testing.md`:

```markdown
| Tier | Path | Runs in CI? | Activates on | Assertions |
|---|---|---|---|---|
| real-LLM | `tests/real_llm/` | **No** (manual dispatch only) | `ERGON_REAL_LLM=1` + `OPENROUTER_API_KEY` | Postgres + Playwright + `/api/test/*` harness; OpenRouter budget gate skips when exhausted |
```

(Insert after the existing e2e row; if the doc uses a different format,
adapt to it.)

- [ ] **Step 9.2: Update builtins doc**

Append a paragraph to the tools section of
`docs/architecture/06_builtins.md`:

```markdown
`benchmark_toolkit_composer` is a DI factory that, given a benchmark slug
and a `WorkerContext`, returns the union of tools the generic ReAct worker
(`react-generic` slug) needs to exercise that benchmark. It's the
mechanism by which the real-LLM debug harness
(`tests/real_llm/`) runs one worker against all three benchmark sandboxes
without per-benchmark specialised workers.
```

- [ ] **Step 9.3: Commit**

```bash
git add docs/architecture/07_testing.md docs/architecture/06_builtins.md
git commit -m "docs(arch): add real-LLM tier row + benchmark_toolkit_composer note"
```

---

## Task 10 — Open PR 1

**Files:** none directly.

- [ ] **Step 10.1: Full check suite**

```bash
pnpm run check:fast
uv run pytest tests/unit tests/state tests/cli -v
```

Expected: all green. Fix anything that broke; iterate.

- [ ] **Step 10.2: Push + PR**

```bash
git push -u origin feature/real-llm-harness-infra
gh pr create \
  --title "feat(real-llm): debug harness infra — tests/real_llm/ + canary (PR 1 of 2)" \
  --body "$(cat <<'EOF'
## Summary
- New `tests/real_llm/` pytest tier, marker-gated (`ERGON_REAL_LLM=1` + `OPENROUTER_API_KEY`).
- `benchmark_toolkit_composer` DI factory + `react-generic` worker slug + CLI `--toolkit-benchmark` flag.
- `OpenRouterBudget` module polls `/api/v1/auth/key` for spend gating (default $5 cap).
- `docker-compose.real-llm.yml` stack overlay + `--assume-stack-up` dev flag.
- Canary test (`test_smoke_stub.py`) exercises stack + CLI + harness-read + Playwright with stub workers (cost = $0).
- No real-LLM runs in this PR. PR 2 adds the 3-random-instances-per-benchmark artifact; between PR 1 and PR 2 the overnight loop runs the harness, files bugs in `docs/bugs/open/`, and ships fix PRs.

## Test plan
- [x] `pnpm run check:fast` green
- [x] `uv run pytest tests/unit -v` green (new openrouter_budget, benchmark_toolkit_composer, react_generic_worker, cli react-generic composition tests)
- [x] Canary test runs against a local stack and exits 0 (stub workers, zero OpenRouter cost)

Follows up on `docs/rfcs/active/2026-04-21-real-llm-debug-harness.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 10.3: Watch CI, iterate**

If CI fails, fix on the branch with fresh commits — never `--amend` a
pushed commit, never `--no-verify`.

---

# After PR 1 merges: Bug-hunt phase

Run `ERGON_REAL_LLM=1 OPENROUTER_API_KEY=... uv run pytest tests/real_llm/
-m real_llm --assume-stack-up` in a loop. For each non-LLM bug:

1. Reproduce manually to confirm it's not a transient.
2. File `docs/bugs/open/YYYY-MM-DD-<slug>.md` from `docs/bugs/TEMPLATE.md`.
3. If trivial: open a fix PR that moves the bug file to `fixed/` on merge.
4. If non-trivial: promote to RFC at `docs/rfcs/active/...`, link via
   `related_rfc`.

The loop terminates when each of the three benchmarks (researchrubrics,
minif2f, swebench-verified) passes the hard-gate assertions on a fresh run.
That condition is the PR 2 freeze signal.

---

# PR 2 — Three-example artifact (follow-up plan)

A separate plan at `docs/superpowers/plans/2026-04-21-real-llm-three-examples.md`
(written after PR 1 merges and the bug-hunt phase stabilises). Shape
previewed here:

- `test_researchrubrics.py`, `test_minif2f.py`, `test_swebench.py`
  parametrised over 3 random benchmark instances (seeded).
- Hard gates (as in the RFC).
- Soft gate: "at least 1/3 non-zero score per benchmark."
- Results reporter writes `.results/YYYY-MM-DD-HHMM-<benchmark>.md` + emits
  a combined PR-body artifact.
