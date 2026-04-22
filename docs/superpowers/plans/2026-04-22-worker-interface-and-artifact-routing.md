# Worker interface + artifact routing cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the four cleanups in `docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md` on `feature/real-llm-harness-infra` (PR #27) — tighten the Worker construction contract, move SWE-Bench per-task setup into the sandbox manager's `_install_dependencies` hook driven by a new data-layer payload lookup, rewire artifact routing to flow via sandbox files + `CriterionRuntime`, and rename the ambiguous `output_text` field to `final_assistant_message` end-to-end.

**Architecture:** Four parallel changes that converge on PR #27 without a DB schema addition. `ReActWorker` becomes a plain `(tools, prompt, iterations)` worker with all kwargs required; benchmark-specific wiring moves from a `BenchmarkAdapter` ABC into registry-level factory closures. SWE-Bench setup scripts run inside `BaseSandboxManager._install_dependencies` after the new method `queries.task_executions.get_task_payload` joins `run_task_executions → experiment_definition_tasks`. Criteria stop reading `WorkerOutput.artifacts` entirely — MiniF2F reads its proof via `context.runtime.read_resource("final_solution.lean")`, SWE-Bench computes the patch itself via `context.runtime.run_command("git diff HEAD")`. One Alembic migration renames the `run_task_executions.output_text` column.

**Tech Stack:** Python 3.13, PEP 695 type aliases (`type Tool = Any`), SQLModel, Alembic, pydantic-ai `Agent`, Inngest steps, `ty` type checker, `ruff`, `slopcop`, `uv run pytest`.

**Branch:** `feature/real-llm-harness-infra` (already exists — no worktree needed; PR #27 open).

---

## Pre-flight

- [ ] **Confirm branch + clean tree**

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
git status
git rev-parse --abbrev-ref HEAD
```

Expected: on `feature/real-llm-harness-infra`, working tree clean (or uncommitted RFC edits only).

- [ ] **Run baseline fast tests to confirm green start**

```bash
pnpm run test:be:fast
```

Expected: all pass. If anything is already red, surface to human before touching code.

- [ ] **Commit any outstanding RFC doc edits before starting**

```bash
git add docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md
git status
git diff --cached --stat
git commit -m "rfc(worker-interface): finalize before implementation"
```

Skip if nothing staged.

---

## Task 1: Add `Tool` type alias module + re-export

**Files:**
- Create: `ergon_core/ergon_core/api/types.py`
- Modify: `ergon_core/ergon_core/api/__init__.py`
- Test: `tests/unit/api/test_types_reexport.py`

**Why:** The RFC hoists `Tool = Any` to a single definition in `ergon_core.api.types` so call sites read as "list of tools" rather than "list of Any" and the `slopcop: ignore[no-typing-any]` lives at one site only.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_types_reexport.py
"""Ensure the public ``Tool`` alias is exported from ``ergon_core.api``."""

from typing import get_type_hints


def test_tool_is_reexported_from_api_root() -> None:
    from ergon_core.api import Tool  # noqa: F401 — import is the assertion

    # Defining a function with list[Tool] must type-check (Tool is callable as a type hint).
    def _takes_tools(tools: list[Tool]) -> int:
        return len(tools)

    assert _takes_tools([]) == 0
    assert _takes_tools([object(), object()]) == 2


def test_tool_module_is_importable() -> None:
    from ergon_core.api import types as api_types

    assert hasattr(api_types, "Tool")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/api/test_types_reexport.py -v
```

Expected: `ImportError: cannot import name 'Tool' from 'ergon_core.api'`.

- [ ] **Step 3: Create `ergon_core/ergon_core/api/types.py`**

```python
# ergon_core/ergon_core/api/types.py
"""Shared type aliases for the public API surface."""

from typing import Any

type Tool = Any  # slopcop: ignore[no-typing-any]
"""Framework-agnostic tool carrier.

Intentionally unconstrained so workers can integrate with any agent
framework. ``ReActWorker`` passes these through to pydantic-ai's
``Agent(tools=...)``; nothing in our code enforces a structural protocol.
If we ever pin to pydantic-ai, tighten this to
``pydantic_ai.tools.Tool | Callable[..., Any]``.
"""

__all__ = ["Tool"]
```

- [ ] **Step 4: Re-export `Tool` from `ergon_core/ergon_core/api/__init__.py`**

Add the import alphabetically (after `task_types`, before `worker`) and add `"Tool"` to `__all__`:

```python
from ergon_core.api.types import Tool
```

And add `"Tool",` to `__all__` between `"TaskEvaluationResult"` and `"Worker"`.

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/unit/api/test_types_reexport.py -v
```

Expected: both tests pass.

- [ ] **Step 6: Run full check**

```bash
pnpm run check:be
```

Expected: clean (lint/format/ty/slopcop all pass). Fix any issues.

- [ ] **Step 7: Commit**

```bash
git add ergon_core/ergon_core/api/types.py ergon_core/ergon_core/api/__init__.py tests/unit/api/test_types_reexport.py
git commit -m "$(cat <<'EOF'
feat(api): introduce public Tool type alias

Hoist `Tool = Any` from inline usage in workers into `ergon_core.api.types`
so call sites read as `list[Tool]` and the `slopcop: ignore[no-typing-any]`
lives at exactly one definition site. Re-exported from `ergon_core.api`.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md §1

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Tighten base `Worker.__init__` — drop `model` default

**Files:**
- Modify: `ergon_core/ergon_core/api/worker.py`
- Test: `tests/unit/api/test_worker_base_contract.py`

**Why:** The RFC commits to making `model: str | None` required on the base class. The union stays (caller may pass `None` to opt into the platform resolver), but the `= None` default is dropped. Concrete subclasses and their test fixtures will update in the next task.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_worker_base_contract.py
"""Contract tests for the base `Worker.__init__` signature."""

import inspect

from ergon_core.api import Worker


def test_model_kwarg_has_no_default() -> None:
    """`model` must be keyword-only AND have no default value.

    Defaults on worker `__init__` are an anti-pattern (RFC 2026-04-22):
    they hide sizing decisions. Factories must pass `model=` explicitly.
    """
    sig = inspect.signature(Worker.__init__)
    model_param = sig.parameters["model"]
    assert model_param.kind == inspect.Parameter.KEYWORD_ONLY, (
        f"`model` must be keyword-only, got {model_param.kind}"
    )
    assert model_param.default is inspect.Parameter.empty, (
        f"`model` must have no default; got {model_param.default!r}"
    )


def test_name_kwarg_has_no_default() -> None:
    sig = inspect.signature(Worker.__init__)
    name_param = sig.parameters["name"]
    assert name_param.kind == inspect.Parameter.KEYWORD_ONLY
    assert name_param.default is inspect.Parameter.empty
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/api/test_worker_base_contract.py -v
```

Expected: `test_model_kwarg_has_no_default` FAILS with "`model` must have no default; got None".

- [ ] **Step 3: Edit `ergon_core/ergon_core/api/worker.py`**

Replace the `__init__` signature starting at line 30:

```python
    def __init__(
        self,
        *,
        name: str,
        model: str | None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        self.name = name
        self.model = model
        self.metadata: dict[str, Any] = dict(metadata or {})  # slopcop: ignore[no-typing-any]
        self._turn_repo = GenerationTurnRepository()
```

(The only change: delete `= None` after `model: str | None` on line 34.)

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/api/test_worker_base_contract.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Run `ty` to find subclasses that now fail**

```bash
uv run ty check ergon_core ergon_builtins tests
```

Expected: failures at every site that constructed a `Worker` subclass without `model=`. Note the list — they're fixed in Task 3.

- [ ] **Step 6: DO NOT commit yet** — Task 3 fixes the ripple. Keep the tree uncommitted and move on.

---

## Task 3: Fix non-benchmark worker subclasses + their call-sites

**Files:**
- Modify: `ergon_builtins/ergon_builtins/workers/baselines/stub_worker.py`
- Modify: `ergon_builtins/ergon_builtins/workers/baselines/training_stub_worker.py`
- Modify: `ergon_builtins/ergon_builtins/workers/baselines/smoke_test_worker.py`
- Modify: `ergon_builtins/ergon_builtins/workers/baselines/manager_researcher_worker.py`
- Modify: `ergon_builtins/ergon_builtins/workers/research_rubrics/stub_worker.py`
- Modify: `ergon_builtins/ergon_builtins/workers/stubs/canonical_smoke_worker.py`
- Modify: all test files that construct any of the above without `model=`
- Test: existing fast suite acts as the regression check

**Why:** Resolves Open Question 1 in favor of **option (a)** — every subclass propagates the "no default" rule so the registry factory closures (built in Task 6) can wrap them uniformly. This is noisier than option (b) but keeps the contract consistent from the top of the hierarchy down: a reader of any worker class sees the same story about `model`.

**Strategy:** Each subclass that forwards `model` to `super().__init__` simply drops its own `= None`. Test fixtures that constructed with `StubWorker(name="x")` now write `StubWorker(name="x", model=None)` — the explicit `None` is intentional and documents the "use platform default" choice.

- [ ] **Step 1: Inventory all subclasses and their constructors**

```bash
uv run ruff check --select=F401 --fix ergon_builtins ergon_core tests 2>/dev/null || true
```

Then:

```bash
grep -n "def __init__" ergon_builtins/ergon_builtins/workers/baselines/stub_worker.py \
  ergon_builtins/ergon_builtins/workers/baselines/training_stub_worker.py \
  ergon_builtins/ergon_builtins/workers/baselines/smoke_test_worker.py \
  ergon_builtins/ergon_builtins/workers/baselines/manager_researcher_worker.py \
  ergon_builtins/ergon_builtins/workers/research_rubrics/stub_worker.py \
  ergon_builtins/ergon_builtins/workers/stubs/canonical_smoke_worker.py
```

Note which ones define their own `__init__` vs. inherit from the base (the latter need no change).

- [ ] **Step 2: For each subclass with its own `__init__`, drop the `model` default**

If the subclass signature reads:

```python
def __init__(self, *, name: str, model: str | None = None, ...) -> None:
```

change to:

```python
def __init__(self, *, name: str, model: str | None, ...) -> None:
```

If the subclass only passes `name=` to `super()` and doesn't mention `model` in its own signature, it inherits from base and no source change is needed — callers pass `model=` directly.

- [ ] **Step 3: Update every construction call-site that omits `model=`**

Run:

```bash
uv run ty check ergon_core ergon_builtins tests 2>&1 | tee /tmp/ty-report.txt
```

For each error reporting "missing argument `model`", open the file and add `model=None` explicitly:

```python
# Before
StubWorker(name="test")
# After
StubWorker(name="test", model=None)
```

Pattern to grep if `ty` output is noisy:

```bash
grep -rn --include="*.py" "StubWorker(name=" tests/ ergon_builtins/ ergon_core/
grep -rn --include="*.py" "TrainingStubWorker(name=" tests/ ergon_builtins/ ergon_core/
grep -rn --include="*.py" "SmokeTestWorker(name=" tests/ ergon_builtins/ ergon_core/
grep -rn --include="*.py" "ManagerResearcherWorker(name=" tests/ ergon_builtins/ ergon_core/
grep -rn --include="*.py" "StubResearchRubricsWorker(name=" tests/ ergon_builtins/ ergon_core/
grep -rn --include="*.py" "CanonicalSmokeWorker(name=" tests/ ergon_builtins/ ergon_core/
```

Pass `model=None` wherever `model=` is absent.

- [ ] **Step 4: Run `ty` again to confirm clean**

```bash
uv run ty check ergon_core ergon_builtins tests
```

Expected: no missing-argument errors. Ignore unrelated warnings that pre-date this change.

- [ ] **Step 5: Run fast suite**

```bash
pnpm run test:be:fast
```

Expected: all green. If anything fails, it's either (a) a site you missed; or (b) a subclass whose signature ripple missed a nested `super().__init__` call — fix inline.

- [ ] **Step 6: Run full check**

```bash
pnpm run check:be
```

Expected: clean.

- [ ] **Step 7: Commit the base + subclass tightening together**

```bash
git add ergon_core/ergon_core/api/worker.py \
        ergon_builtins/ergon_builtins/workers \
        tests/unit/api/test_worker_base_contract.py \
        tests/
git commit -m "$(cat <<'EOF'
refactor(worker): make `model` kwarg required on base Worker and subclasses

Drop `model: str | None = None` defaults across the Worker hierarchy
(base class, StubWorker, TrainingStubWorker, SmokeTestWorker,
ManagerResearcherWorker, StubResearchRubricsWorker, CanonicalSmokeWorker)
and update call-sites to pass `model=None` explicitly where the platform
resolver default is intended. The union `str | None` stays; the default
goes.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md §1
(anti-pattern: nullable-with-default on worker __init__)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Tighten `ReActWorker.__init__` — drop adapter + all-kwargs-required

**Files:**
- Modify: `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`
- Test: `tests/unit/workers/test_react_worker_contract.py`

**Why:** `ReActWorker` becomes a plain `(tools, system_prompt, max_iterations)` worker. The adapter ABC and its hooks disappear from the worker signature (actual file deletion happens in Task 5). All kwargs are required — no defaults.

- [ ] **Step 1: Write the failing contract tests**

```python
# tests/unit/workers/test_react_worker_contract.py
"""Contract tests for the post-RFC `ReActWorker.__init__` signature."""

import inspect

import pytest

from ergon_builtins.workers.baselines.react_worker import ReActWorker


def test_no_adapter_kwarg() -> None:
    sig = inspect.signature(ReActWorker.__init__)
    assert "adapter" not in sig.parameters, (
        "BenchmarkAdapter ABC is being deleted — ReActWorker must not accept an adapter kwarg."
    )


@pytest.mark.parametrize(
    "kwarg",
    ["name", "model", "tools", "system_prompt", "max_iterations"],
)
def test_all_kwargs_required_and_keyword_only(kwarg: str) -> None:
    sig = inspect.signature(ReActWorker.__init__)
    param = sig.parameters[kwarg]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        f"`{kwarg}` must be keyword-only; got {param.kind}"
    )
    assert param.default is inspect.Parameter.empty, (
        f"`{kwarg}` must have no default (RFC 2026-04-22 forbids nullable-with-default); "
        f"got {param.default!r}"
    )


def test_construct_with_minimal_explicit_kwargs() -> None:
    """A ReActWorker can be built with explicit [] tools and None prompt."""
    worker = ReActWorker(
        name="unit",
        model=None,
        tools=[],
        system_prompt=None,
        max_iterations=1,
    )
    assert worker.name == "unit"
    assert worker.tools == []
    assert worker.system_prompt is None
    assert worker.max_iterations == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/workers/test_react_worker_contract.py -v
```

Expected: `test_no_adapter_kwarg` and all parametrized `test_all_kwargs_required_and_keyword_only` cases fail.

- [ ] **Step 3: Rewrite `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`**

Open the file. Make the following edits (line numbers from the current read):

- Remove line 28: `from ergon_builtins.workers.baselines.adapters.base import BenchmarkAdapter` (not needed after adapter dir is deleted in Task 5 — removing the import early keeps intermediate state runnable once Task 5 lands; for THIS task, keep it until Task 5 deletes it).
- Add import: `from ergon_core.api import Tool` near the other `ergon_core.api` imports (line ~11).
- Replace the entire `__init__` method (lines 82–109) with:

```python
    def __init__(
        self,
        *,
        name: str,
        model: str | None,
        tools: list[Tool],
        system_prompt: str | None,
        max_iterations: int,
    ) -> None:
        super().__init__(name=name, model=model)
        self.tools: list[Tool] = tools
        self.system_prompt: str | None = system_prompt
        self.max_iterations: int = max_iterations
        self._seed_messages: list[ModelMessage] | None = None
```

- Replace the `execute` method body (lines 111–126) — remove all `self._adapter` references:

```python
    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        async for turn in self._run_agent(task):
            yield turn
```

- Delete `self._adapter = adapter` + the three adapter-resolution branches in the old `__init__`.
- Replace `get_output` (lines 173–178) with:

```python
    def get_output(self, context: WorkerContext) -> WorkerOutput:
        """Extract the agent's text output from the last context event."""
        return self._base_output(context)
```

- Remove the `BenchmarkAdapter` type annotation on the class docstring (lines 74–77) — the class no longer knows about adapters.

- Keep everything else (`_run_agent`, `_base_output`, `from_buffer`, helpers) unchanged.

- [ ] **Step 4: Run the contract tests to verify they pass**

```bash
uv run pytest tests/unit/workers/test_react_worker_contract.py -v
```

Expected: all four tests pass.

- [ ] **Step 5: Expected secondary failures**

```bash
uv run pytest tests/minif2f/test_react_worker.py -v 2>&1 | head -30
```

Expected: existing MiniF2F adapter-style tests will now fail (they construct `ReActWorker(adapter=...)`). These tests are deleted/rewritten in Task 5 + later tasks — DO NOT fix them here.

- [ ] **Step 6: DO NOT commit yet** — Tasks 5–7 must land atomically with this so registry factories and adapter-test deletion reach a consistent state in one PR. Keep the tree in flight.

---

## Task 5: Delete adapter module + adapter tests

**Files:**
- Delete: `ergon_builtins/ergon_builtins/workers/baselines/adapters/__init__.py`
- Delete: `ergon_builtins/ergon_builtins/workers/baselines/adapters/base.py`
- Delete: `ergon_builtins/ergon_builtins/workers/baselines/adapters/minif2f.py`
- Delete: `ergon_builtins/ergon_builtins/workers/baselines/adapters/swebench.py`
- Delete: any `tests/**/test_*adapter*.py`
- Delete: `tests/minif2f/test_react_worker.py` (will be rewritten in Task 13)
- Modify: `ergon_builtins/ergon_builtins/registry_core.py` (drop adapter imports)
- Modify: `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py` (drop lingering adapter import if still present from Task 4)

**Why:** The ABC is the wrong abstraction (RFC §1). Nothing imports from `adapters/` outside the files being deleted or modified here.

- [ ] **Step 1: Confirm nothing outside scope imports from `adapters/`**

```bash
grep -rn --include="*.py" "from ergon_builtins.workers.baselines.adapters" \
  ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
```

Expected only hits: `react_worker.py` (will drop import now) and `registry_core.py` (will drop in Task 6). If there are others, stop and flag to human.

- [ ] **Step 2: Delete the adapter directory**

```bash
rm -r ergon_builtins/ergon_builtins/workers/baselines/adapters/
```

- [ ] **Step 3: Find + delete adapter-targeted tests**

```bash
find tests -type f -name "test_*adapter*.py"
```

Delete each matching file. Also delete `tests/minif2f/test_react_worker.py` (the current version constructs `ReActWorker(adapter=...)`; a new `test_react_worker.py` will be written in Task 13 covering the new surface).

```bash
rm tests/minif2f/test_react_worker.py
# For each finding from the find command above:
rm <path>
```

- [ ] **Step 4: Remove any lingering adapter import in `react_worker.py`**

Search the file:

```bash
grep -n "adapter" ergon_builtins/ergon_builtins/workers/baselines/react_worker.py
```

If any remain, delete those lines.

- [ ] **Step 5: Remove adapter imports from `registry_core.py` (partial — factories still wrong; fixed in Task 6)**

Delete the line:

```python
from ergon_builtins.workers.baselines.adapters import MiniF2FAdapter, SWEBenchAdapter
```

The `_minif2f_react` and `_swebench_react` functions will fail to resolve — that's fine because Task 6 rewrites them next.

- [ ] **Step 6: Run lint to confirm no broken imports in files that remain**

```bash
uv run ruff check ergon_core ergon_builtins tests
```

Ignore errors that come from `registry_core.py`'s missing `MiniF2FAdapter` / `SWEBenchAdapter` symbols — Task 6 fixes them.

- [ ] **Step 7: Commit Tasks 4 + 5 together**

```bash
git add ergon_builtins/ergon_builtins/workers/baselines/react_worker.py \
        tests/unit/workers/test_react_worker_contract.py
git add -u  # stage deletions
git status  # verify: react_worker.py modified, adapters/ deleted, adapter tests deleted, minif2f react test deleted
git commit -m "$(cat <<'EOF'
refactor(react-worker): drop BenchmarkAdapter ABC; require all kwargs

`ReActWorker.__init__` now takes `(name, model, tools, system_prompt,
max_iterations)` as required keyword-only kwargs — no defaults, no
adapter. The ABC, the four hooks (`build_tools`, `on_run_start`,
`on_run_end`, `transform_output`), and both concrete adapters
(`MiniF2FAdapter`, `SWEBenchAdapter`) are deleted. Benchmark-specific
wiring moves into registry factory closures (next commit).

Tests targeting the deleted adapter ABC are removed. A replacement
`tests/unit/workers/test_react_worker_contract.py` locks in the
new signature. A new behavioral test for MiniF2F will land with
the criterion rewrite.

Registry factories (`_minif2f_react`, `_swebench_react`) are TEMPORARILY
broken by this commit — the very next commit rewires them.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md §1

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

Note: this commit intentionally leaves `registry_core.py` in a broken state for exactly one commit. Task 6 immediately repairs it. **Do NOT push the branch between Tasks 5 and 6.**

---

## Task 6: Rewrite registry factories with inline toolkits + new kwargs

**Files:**
- Modify: `ergon_builtins/ergon_builtins/registry_core.py`
- Create: `ergon_builtins/ergon_builtins/workers/baselines/react_prompts.py`
- Test: `tests/unit/registry/test_react_factories.py`

**Why:** With `BenchmarkAdapter` gone, per-benchmark wiring (toolkit, system prompt, `max_iterations`) lives in the registry factory. The factory call signature grows `task_id: UUID` and `sandbox_id: str` kwargs so benchmark factories can build toolkits bound to the live sandbox. Non-benchmark factories accept-and-ignore the extras (option (a) from Open Question 1).

- [ ] **Step 1: Write the failing factory test**

```python
# tests/unit/registry/test_react_factories.py
"""Smoke-test the new registry factory signatures."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from ergon_builtins.registry_core import WORKERS
from ergon_core.api import Worker


def test_no_bare_react_v1_entry() -> None:
    """RFC §1: `react-v1` bare entry removed — every factory binds a concrete toolkit."""
    assert "react-v1" not in WORKERS, (
        "Bare `react-v1` entry must not exist post-RFC. Use `minif2f-react` or "
        "`swebench-react` instead."
    )


def test_stub_factory_accepts_new_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-benchmark factories must accept `task_id` / `sandbox_id` kwargs (option a)."""
    factory = WORKERS["stub-worker"]
    worker = factory(
        name="stub-under-test",
        model=None,
        task_id=uuid4(),
        sandbox_id="sbx-abc",
    )
    assert isinstance(worker, Worker)
    assert worker.name == "stub-under-test"


def test_minif2f_factory_builds_toolkit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The minif2f factory must construct a live toolkit bound to the sandbox."""
    from ergon_builtins.benchmarks.minif2f import sandbox_manager as sm_mod

    fake_sandbox = MagicMock(name="fake-sandbox")
    fake_manager = MagicMock(spec=sm_mod.MiniF2FSandboxManager)
    fake_manager.get_sandbox.return_value = fake_sandbox
    monkeypatch.setattr(sm_mod, "MiniF2FSandboxManager", lambda: fake_manager)

    factory = WORKERS["minif2f-react"]
    task_id = uuid4()
    worker = factory(
        name="minif2f-test",
        model=None,
        task_id=task_id,
        sandbox_id="sbx-minif2f",
    )
    assert isinstance(worker, Worker)
    # Factory should have asked the manager for the sandbox
    fake_manager.get_sandbox.assert_called_once_with(task_id)
    # Tools list must be non-empty (the MiniF2F toolkit publishes ≥1 tool)
    assert worker.tools != []
    # `max_iterations` must be explicit — 30 is the MiniF2F budget from the old adapter
    assert worker.max_iterations == 30
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/registry/test_react_factories.py -v
```

Expected: all three tests fail (registry still references deleted adapters).

- [ ] **Step 3: Create `ergon_builtins/ergon_builtins/workers/baselines/react_prompts.py`**

Move the two prompts here (they previously lived on the adapter subclasses):

```python
# ergon_builtins/ergon_builtins/workers/baselines/react_prompts.py
"""System prompts for ReAct worker factories.

Each benchmark's registry factory binds one of these at worker-construction
time; the prompts are otherwise framework-agnostic and contain no runtime
state.
"""

MINIF2F_SYSTEM_PROMPT = (
    "You are an expert Lean 4 theorem prover. Your task is to produce a "
    "complete, verified proof of the given theorem using Mathlib4.\n\n"
    "Workflow:\n"
    "1. Call write_lean_file to save a candidate proof to "
    "/workspace/scratchpad/draft.lean. Use 'sorry' as a placeholder while "
    "exploring.\n"
    "2. Call check_lean_file to see compilation errors and remaining goals.\n"
    "3. Iterate until the proof has no 'sorry' and no errors.\n"
    "4. Write the final proof to /workspace/final_output/final_solution.lean "
    "and call verify_lean_proof to confirm the Lean kernel accepts it.\n\n"
    "Always import Mathlib at the top. Keep proofs short and use high-level "
    "tactics (ring, linarith, nlinarith, simp, omega) when possible."
)

SWEBENCH_SYSTEM_PROMPT = (
    "You are a senior software engineer fixing an issue in a Python repo.\n\n"
    "You have two tools:\n"
    "- bash: run shell commands in the repo workdir.\n"
    "- str_replace_editor: view/create/str_replace files.\n\n"
    "Workflow:\n"
    "1. Read the problem statement and explore the repo layout.\n"
    "2. Locate the relevant files; run failing tests to reproduce.\n"
    "3. Edit code via str_replace_editor; re-run tests until they pass.\n"
    "4. Keep the patch minimal — do not modify test files.\n"
    "The final answer is whatever `git diff HEAD` shows when you stop."
)
```

- [ ] **Step 4: Rewrite `ergon_builtins/ergon_builtins/registry_core.py`**

Replace the old factory section. Updated imports (drop the adapter import, add toolkit imports + UUID):

```python
from uuid import UUID

from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import SWEBenchSandboxManager
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
from ergon_builtins.workers.baselines.react_prompts import (
    MINIF2F_SYSTEM_PROMPT,
    SWEBENCH_SYSTEM_PROMPT,
)
from ergon_builtins.workers.baselines.react_worker import ReActWorker
# ... rest of imports unchanged (drop the adapters import line)
```

Replace the `_minif2f_react` factory closure:

```python
def _minif2f_react(
    *,
    name: str,
    model: str | None,
    task_id: UUID,
    sandbox_id: str,  # unused; sandbox is resolved via the singleton manager
) -> ReActWorker:
    """Registry factory: ReActWorker wired with a live MiniF2F toolkit."""
    _ = sandbox_id  # factory signature requires it; manager lookup uses task_id
    sandbox = MiniF2FSandboxManager().get_sandbox(task_id)
    if sandbox is None:
        raise RuntimeError(
            f"MiniF2F factory requires a live sandbox for task_id={task_id}; "
            "SandboxSetupRequest must have completed before worker-execute runs."
        )
    toolkit = MiniF2FToolkit(
        sandbox=sandbox,
        sandbox_run_skill=_minif2f_run_skill(sandbox),
        run_id=task_id,  # MiniF2FToolkit uses this only for tracing
    )
    return ReActWorker(
        name=name,
        model=model,
        tools=list(toolkit.get_tools()),
        system_prompt=MINIF2F_SYSTEM_PROMPT,
        max_iterations=30,
    )


def _minif2f_run_skill(sandbox):  # slopcop: ignore[no-return-annotation]
    """Return the write_lean_file run_skill callback bound to ``sandbox``.

    Extracted from the old MiniF2FAdapter verbatim. The MiniF2F toolkit
    only routes ``write_lean_file`` through this callback; the other
    tools drive ``sandbox.commands.run`` directly.
    """
    from typing import Any
    from uuid import UUID

    async def run_skill(
        _run_id: UUID,
        skill_name: str,
        response_model: type,
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> Any:  # slopcop: ignore[no-typing-any]
        if skill_name != "write_lean_file":
            raise ValueError(f"MiniF2F factory does not support skill {skill_name!r}")
        file_path = kwargs["file_path"]
        content = kwargs["content"]
        payload = content.encode("utf-8") if isinstance(content, str) else content
        await sandbox.files.write(file_path, payload)
        return response_model(
            success=True,
            filename=file_path,
            bytes_written=len(payload),
        )

    return run_skill
```

Replace `_swebench_react`:

```python
def _swebench_react(
    *,
    name: str,
    model: str | None,
    task_id: UUID,
    sandbox_id: str,
) -> ReActWorker:
    """Registry factory: ReActWorker wired with a live SWE-Bench toolkit."""
    _ = sandbox_id  # see note in _minif2f_react
    sandbox = SWEBenchSandboxManager().get_sandbox(task_id)
    if sandbox is None:
        raise RuntimeError(
            f"SWE-Bench factory requires a live sandbox for task_id={task_id}; "
            "SandboxSetupRequest must have completed (including "
            "_install_dependencies) before worker-execute runs."
        )
    toolkit = SWEBenchToolkit(sandbox=sandbox, workdir="/workspace/repo")
    return ReActWorker(
        name=name,
        model=model,
        tools=list(toolkit.get_tools()),
        system_prompt=SWEBENCH_SYSTEM_PROMPT,
        max_iterations=50,
    )
```

Add a helper that wraps plain `Worker` subclasses so the registry signature is uniform — **resolves Open Question 1 in favor of option (a)** but keeps the wrapping minimal:

```python
def _plain(cls: type[Worker]):  # slopcop: ignore[no-return-annotation]
    """Wrap a plain ``Worker`` subclass so it ignores registry-injected kwargs.

    Non-benchmark workers (``StubWorker``, ``SmokeTestWorker``, …) don't need
    ``task_id`` or ``sandbox_id``. The registry call site always passes them
    (see ``worker_execute.py``); this shim drops the extras before forwarding.
    """

    def factory(
        *,
        name: str,
        model: str | None,
        task_id: UUID,  # noqa: ARG001
        sandbox_id: str,  # noqa: ARG001
    ) -> Worker:
        return cls(name=name, model=model)

    factory.__name__ = f"_{cls.__name__}_factory"
    factory.__qualname__ = factory.__name__
    return factory
```

Then the `WORKERS` dict loses the bare `"react-v1"` entry and wraps plain classes through `_plain`:

```python
WORKERS: dict[str, Callable[..., Worker]] = {
    "stub-worker": _plain(StubWorker),
    "training-stub": _plain(TrainingStubWorker),
    "smoke-test-worker": _plain(SmokeTestWorker),
    # NOTE: `react-v1` bare entry removed (RFC 2026-04-22).
    # Every real use binds a concrete toolkit via a factory closure below.
    "minif2f-react": _minif2f_react,
    "swebench-react": _swebench_react,
    "manager-researcher": _plain(ManagerResearcherWorker),
    "researcher": _plain(StubWorker),
    "researchrubrics-stub": _plain(StubResearchRubricsWorker),
    "canonical-smoke": _plain(CanonicalSmokeWorker),
}
```

- [ ] **Step 5: Run the factory tests to verify they pass**

```bash
uv run pytest tests/unit/registry/test_react_factories.py -v
```

Expected: all three pass.

- [ ] **Step 6: Run fast suite**

```bash
pnpm run test:be:fast
```

Expected: all green (MiniF2F `test_react_worker.py` was deleted in Task 5; no other suite exercises the old adapter paths).

- [ ] **Step 7: Run full check**

```bash
pnpm run check:be
```

Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add ergon_builtins/ergon_builtins/registry_core.py \
        ergon_builtins/ergon_builtins/workers/baselines/react_prompts.py \
        tests/unit/registry/test_react_factories.py
git commit -m "$(cat <<'EOF'
refactor(registry): move benchmark wiring into ReAct factory closures

Registry factories now build toolkits inline and pass concrete
`tools=`, `system_prompt=`, `max_iterations=` into `ReActWorker(...)`.
Signature grows `task_id: UUID` and `sandbox_id: str` kwargs so
benchmark factories can resolve the live sandbox from their singleton
manager. Plain workers (Stub, SmokeTest, …) are wrapped in a
`_plain(cls)` shim that accepts-and-ignores the extras.

The bare `"react-v1": ReActWorker` entry is removed — every real use
now binds a concrete toolkit + prompt + iteration budget, so a generic
ReAct registration is meaningless.

System prompts move from deleted adapters to
`workers/baselines/react_prompts.py` as plain module constants.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md §1

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Update `worker_execute.py` call-site to pass `task_id` / `sandbox_id`

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/inngest/worker_execute.py`
- Test: `tests/unit/runtime/test_worker_execute_factory_call.py` (or add to existing unit test if one covers this function)

**Why:** The `worker_cls(...)` call site is the one place the registry-wrapped factory is actually invoked. Now that every factory in the registry expects `task_id=` and `sandbox_id=`, the call must supply them. Both fields are already in `WorkerExecuteRequest` (line 33–34).

- [ ] **Step 1: Write the failing call-site test**

```python
# tests/unit/runtime/test_worker_execute_factory_call.py
"""Verify worker_execute passes task_id / sandbox_id into the factory."""

from unittest.mock import MagicMock
from uuid import uuid4

from ergon_builtins.registry_core import WORKERS


def test_factory_receives_task_and_sandbox(monkeypatch) -> None:
    """The factory registered in WORKERS must receive task_id + sandbox_id kwargs."""
    captured: dict[str, object] = {}

    def capturing_factory(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        w = MagicMock()
        w.name = "captured"
        return w

    monkeypatch.setitem(WORKERS, "capturing", capturing_factory)

    task_id = uuid4()
    sandbox_id = "sbx-xyz"

    # Direct call imitating worker_execute.py:60
    worker_cls = WORKERS["capturing"]
    worker_cls(
        name="captured",
        model="anthropic:claude-sonnet-4",
        task_id=task_id,
        sandbox_id=sandbox_id,
    )

    assert captured == {
        "name": "captured",
        "model": "anthropic:claude-sonnet-4",
        "task_id": task_id,
        "sandbox_id": sandbox_id,
    }
```

- [ ] **Step 2: Run test**

```bash
uv run pytest tests/unit/runtime/test_worker_execute_factory_call.py -v
```

Expected: this test should actually **pass** already given Task 6's factory shape. But the real fix is in `worker_execute.py`:60 — it must pass those kwargs when invoking the factory. Confirm by grep:

```bash
grep -n "worker_cls(" ergon_core/ergon_core/core/runtime/inngest/worker_execute.py
```

If the call still reads `worker_cls(name=payload.assigned_worker_slug, model=payload.model_target)` without `task_id=` / `sandbox_id=`, the real runtime path is broken even though the unit test isolates the factory.

- [ ] **Step 3: Edit `ergon_core/ergon_core/core/runtime/inngest/worker_execute.py` line ~60**

Change:

```python
worker = worker_cls(
    name=payload.assigned_worker_slug,
    model=payload.model_target,
)
```

to:

```python
worker = worker_cls(
    name=payload.assigned_worker_slug,
    model=payload.model_target,
    task_id=payload.task_id,
    sandbox_id=payload.sandbox_id,
)
```

- [ ] **Step 4: Add a behavioral assertion to the existing `worker_execute` test if present**

```bash
find tests -name "test_worker_execute*.py"
```

If such a file exists, add a case that asserts the factory signature match. If not, the unit test from Step 1 is sufficient.

- [ ] **Step 5: Run fast suite**

```bash
pnpm run test:be:fast
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add ergon_core/ergon_core/core/runtime/inngest/worker_execute.py \
        tests/unit/runtime/test_worker_execute_factory_call.py
git commit -m "$(cat <<'EOF'
feat(runtime): pass task_id + sandbox_id into worker factory

The registry-wrapped factory call at worker_execute.py:60 now supplies
`task_id=payload.task_id` and `sandbox_id=payload.sandbox_id` in addition
to the existing `name=` / `model=` kwargs. Both are already present on
`WorkerExecuteRequest`; this is purely a call-site propagation.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md §1

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Add `TaskExecutionsQueries.get_task_payload`

**Files:**
- Modify: `ergon_core/ergon_core/core/persistence/queries.py`
- Test: `tests/state/test_task_executions_queries.py` (add or extend)

**Why:** The data layer owns the `run_task_executions` → `experiment_definition_tasks` JOIN. Sandbox managers read task_payload through this helper; they do NOT re-implement the JOIN themselves.

- [ ] **Step 1: Write the failing test**

```python
# tests/state/test_task_executions_queries.py  (add to existing file or create)
"""Tests for TaskExecutionsQueries.get_task_payload."""

from uuid import uuid4

from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionTask,
)
from ergon_core.core.persistence.queries import queries
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution


def _insert_task_execution_with_payload(payload: dict[str, object]) -> tuple:
    """Insert minimal fixture rows and return (execution_id, definition_task_id)."""
    with get_session() as session:
        ed = ExperimentDefinition(
            id=uuid4(),
            experiment_id=uuid4(),
            benchmark_type="swebench-verified",
            name="test-def",
        )
        edt = ExperimentDefinitionTask(
            id=uuid4(),
            experiment_definition_id=ed.id,
            task_slug="test-task",
            task_description="fixture",
            task_payload=payload,
        )
        run = RunRecord(id=uuid4(), experiment_definition_id=ed.id, name="test-run")
        exe = RunTaskExecution(
            id=uuid4(),
            run_id=run.id,
            definition_task_id=edt.id,
            task_slug="test-task",
            attempt_number=1,
            status="pending",
        )
        session.add_all([ed, edt, run, exe])
        session.commit()
        return exe.id, edt.id


def test_get_task_payload_returns_joined_payload(db_session) -> None:  # noqa: ARG001
    payload = {"instance_id": "django__django-12345", "repo": "django/django"}
    exe_id, _ = _insert_task_execution_with_payload(payload)

    result = queries.task_executions.get_task_payload(exe_id)
    assert result == payload


def test_get_task_payload_returns_none_for_missing_execution(db_session) -> None:  # noqa: ARG001
    assert queries.task_executions.get_task_payload(uuid4()) is None
```

(Use whatever `db_session` fixture the existing state tests use; check an existing file like `tests/state/test_runs_queries.py` for the fixture name.)

- [ ] **Step 2: Run test**

```bash
uv run pytest tests/state/test_task_executions_queries.py -v
```

Expected: `AttributeError: 'TaskExecutionsQueries' object has no attribute 'get_task_payload'`.

- [ ] **Step 3: Add the method to `TaskExecutionsQueries`**

In `ergon_core/ergon_core/core/persistence/queries.py`, after `update_status` (line ~257):

```python
    def get_task_payload(self, task_execution_id: UUID) -> dict[str, Any] | None:
        """Return the immutable task_payload for a task execution.

        Joins ``run_task_executions`` → ``experiment_definition_tasks``.
        Returns ``None`` if the execution row does not exist or its
        ``definition_task_id`` points at nothing (run-scoped tasks that
        weren't tied to a definition — should not happen in normal
        benchmark flow).
        """
        with get_session() as session:
            stmt = (
                select(ExperimentDefinitionTask.task_payload)
                .join(
                    RunTaskExecution,
                    RunTaskExecution.definition_task_id == ExperimentDefinitionTask.id,
                )
                .where(RunTaskExecution.id == task_execution_id)
            )
            return session.exec(stmt).first()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/state/test_task_executions_queries.py::test_get_task_payload_returns_joined_payload -v
uv run pytest tests/state/test_task_executions_queries.py::test_get_task_payload_returns_none_for_missing_execution -v
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add ergon_core/ergon_core/core/persistence/queries.py \
        tests/state/test_task_executions_queries.py
git commit -m "$(cat <<'EOF'
feat(queries): add TaskExecutionsQueries.get_task_payload

JOIN helper that reads `experiment_definition_tasks.task_payload` through
`run_task_executions.definition_task_id`. Callers (next commit: the
SWE-Bench sandbox manager's `_install_dependencies` hook) no longer need
to know about the JOIN — they ask the data layer for the payload by
execution id.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md §2

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Rewrite `SWEBenchSandboxManager._install_dependencies`

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_manager.py`
- Create: `ergon_core/ergon_core/core/providers/sandbox/errors.py` (if `SandboxSetupError` doesn't already exist — check first)
- Test: `tests/unit/benchmarks/test_swebench_sandbox_manager.py`

**Why:** The adapter's `on_run_start` used to run `setup_env_script` + `install_repo_script`. The hooks are gone; the sandbox manager owns per-task setup now. The hook has `task_id` — fetch the payload via `queries.task_executions.get_task_payload` and drive the harness scripts.

- [ ] **Step 1: Check whether `SandboxSetupError` exists**

```bash
grep -rn "class SandboxSetupError" ergon_core/
```

If not found, create it in `ergon_core/ergon_core/core/providers/sandbox/errors.py`:

```python
# ergon_core/ergon_core/core/providers/sandbox/errors.py
"""Exceptions raised by sandbox lifecycle code paths."""


class SandboxSetupError(RuntimeError):
    """Raised when `BaseSandboxManager._install_dependencies` cannot complete.

    Carries the original stderr/stdout tail in its message so Inngest
    retries surface actionable errors without digging through logs.
    """
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/benchmarks/test_swebench_sandbox_manager.py
"""Install-dependencies behavior for SWE-Bench."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)


SAMPLE_PAYLOAD = {
    "instance_id": "django__django-12345",
    "repo": "django/django",
    "base_commit": "abcdef1234567890",
    "version": "4.2",
    "problem_statement": "fix foo",
    "fail_to_pass": ["tests.test_x"],
    "pass_to_pass": ["tests.test_y"],
    "environment_setup_commit": "setup123",
    "test_patch": "",
    "hints_text": "",
}


@pytest.mark.asyncio
async def test_install_runs_setup_and_install_scripts(monkeypatch: pytest.MonkeyPatch) -> None:
    from ergon_core.core.persistence import queries as q_mod

    monkeypatch.setattr(
        q_mod.queries.task_executions,
        "get_task_payload",
        lambda _tid: SAMPLE_PAYLOAD,
    )

    fake_spec = MagicMock(
        setup_env_script="echo setup",
        install_repo_script="echo install",
    )
    from ergon_builtins.benchmarks.swebench_verified import sandbox_manager as sm

    monkeypatch.setattr(sm, "make_test_spec", lambda _row: fake_spec)

    sandbox = MagicMock()
    sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout="ok"))

    manager = SWEBenchSandboxManager()
    await manager._install_dependencies(sandbox, uuid4())  # type: ignore[attr-defined]

    assert sandbox.commands.run.call_count == 2
    cmds = [c.args[0] for c in sandbox.commands.run.call_args_list]
    assert any("echo setup" in cmd for cmd in cmds)
    assert any("echo install" in cmd for cmd in cmds)


@pytest.mark.asyncio
async def test_install_raises_when_payload_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from ergon_core.core.persistence import queries as q_mod
    from ergon_core.core.providers.sandbox.errors import SandboxSetupError

    monkeypatch.setattr(
        q_mod.queries.task_executions, "get_task_payload", lambda _tid: None
    )

    manager = SWEBenchSandboxManager()
    with pytest.raises(SandboxSetupError, match="No task_payload"):
        await manager._install_dependencies(MagicMock(), uuid4())  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_install_raises_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    from ergon_core.core.persistence import queries as q_mod
    from ergon_core.core.providers.sandbox.errors import SandboxSetupError
    from ergon_builtins.benchmarks.swebench_verified import sandbox_manager as sm

    monkeypatch.setattr(
        q_mod.queries.task_executions, "get_task_payload", lambda _tid: SAMPLE_PAYLOAD
    )
    monkeypatch.setattr(
        sm,
        "make_test_spec",
        lambda _row: MagicMock(setup_env_script="false", install_repo_script="true"),
    )

    sandbox = MagicMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=1, stdout="boom")
    )

    manager = SWEBenchSandboxManager()
    with pytest.raises(SandboxSetupError, match="setup_env"):
        await manager._install_dependencies(sandbox, uuid4())  # type: ignore[attr-defined]
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/unit/benchmarks/test_swebench_sandbox_manager.py -v
```

Expected: 3 failures — current `_install_dependencies` is a `pass`.

- [ ] **Step 4: Rewrite `_install_dependencies` in `sandbox_manager.py`**

Replace the body (lines 58–61):

```python
    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        """Clone the repo at base_commit and install deps for this SWE-Bench instance.

        Payload is fetched from the data layer (no event-payload leak);
        `make_test_spec` produces the canonical setup + install shell
        scripts.  Called exactly once per sandbox by
        `BaseSandboxManager.create()` — the early-return at `create()`
        guards idempotence, so re-entry does not re-run these scripts.
        """
        from ergon_core.core.persistence.queries import queries
        from ergon_core.core.providers.sandbox.errors import SandboxSetupError

        from ergon_builtins.benchmarks.swebench_verified.criterion import (
            make_test_spec,
        )
        from ergon_builtins.benchmarks.swebench_verified.sandbox_manager_support import (
            payload_to_swebench_row,
        )

        payload = queries.task_executions.get_task_payload(task_id)
        if payload is None:
            raise SandboxSetupError(
                f"No task_payload for task_id={task_id}; prepare step must commit "
                "before sandbox-setup dispatches."
            )
        row = payload_to_swebench_row(payload)
        spec = make_test_spec(row)

        import shlex

        for label, script in (
            ("setup_env", spec.setup_env_script),
            ("install_repo", spec.install_repo_script),
        ):
            logger.info("SWE-Bench _install_dependencies running %s for task_id=%s", label, task_id)
            r = await sandbox.commands.run(
                f"bash -c {shlex.quote(script)}",
                timeout=1800,
            )
            if r.exit_code != 0:
                tail = (r.stdout or "")[-1000:]
                raise SandboxSetupError(
                    f"swebench {label} failed for task_id={task_id}: exit={r.exit_code} "
                    f"tail={tail!r}"
                )
```

Note the two imports at the top of the function body — `make_test_spec` and `payload_to_swebench_row`. The latter is moved out of the deleted `adapters/swebench.py` into a new small module:

- [ ] **Step 5: Create `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_manager_support.py`**

```python
# ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_manager_support.py
"""Small helpers for SWE-Bench sandbox setup.

Formerly `_payload_to_swebench_row` lived on the deleted
`BenchmarkAdapter` subclass; it belongs to the sandbox manager (and the
evaluation criterion) now.
"""

from typing import Any


def payload_to_swebench_row(
    payload: dict[str, Any],  # slopcop: ignore[no-typing-any]
) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    """Translate a ``SWEBenchTaskPayload`` dict into a harness row.

    The harness expects UPPER_CASE keys for ``FAIL_TO_PASS`` / ``PASS_TO_PASS``
    and a ``patch`` field (we always pass the empty string since the gold
    patch must never reach the worker).
    """
    return {
        "instance_id": payload["instance_id"],
        "repo": payload["repo"],
        "base_commit": payload["base_commit"],
        "version": payload["version"],
        "problem_statement": payload["problem_statement"],
        "hints_text": payload.get("hints_text", ""),
        "FAIL_TO_PASS": payload["fail_to_pass"],
        "PASS_TO_PASS": payload["pass_to_pass"],
        "environment_setup_commit": payload["environment_setup_commit"],
        "test_patch": payload["test_patch"],
        "patch": "",
    }
```

- [ ] **Step 6: Update `criterion.py` to use the moved helper**

In `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py` line 26:

```python
# Before
from ergon_builtins.workers.baselines.adapters.swebench import _payload_to_swebench_row
# After
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager_support import (
    payload_to_swebench_row as _payload_to_swebench_row,
)
```

(Keep the local alias with the leading underscore if the criterion's body still references the private name; changing the body is Task 11's scope.)

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/unit/benchmarks/test_swebench_sandbox_manager.py -v
```

Expected: all three pass.

- [ ] **Step 8: Run fast suite**

```bash
pnpm run test:be:fast
```

Expected: green.

- [ ] **Step 9: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_manager.py \
        ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_manager_support.py \
        ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py \
        ergon_core/ergon_core/core/providers/sandbox/errors.py \
        tests/unit/benchmarks/test_swebench_sandbox_manager.py
git commit -m "$(cat <<'EOF'
feat(swebench): move per-task setup into _install_dependencies

`SWEBenchSandboxManager._install_dependencies` now fetches the
instance payload through the new `queries.task_executions.get_task_payload`
helper and runs `setup_env_script` + `install_repo_script` via the
harness. `_payload_to_swebench_row` moves out of the deleted
`adapters/swebench.py` into a new `sandbox_manager_support` module
shared by the manager and the criterion.

`SandboxSetupError` is added to the sandbox-provider package. Raised on
missing payload or non-zero exit; propagates through Inngest.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md §2

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: `ensure_sandbox()` idempotence regression test (resolves Open Question 2)

**Files:**
- Test: `tests/unit/sandbox/test_ensure_sandbox_idempotence.py`

**Why:** With per-task setup scripts now living in `_install_dependencies`, the cost of a redundant `ensure_sandbox()` call from a criterion must remain zero (scripts must NOT re-run). `BaseSandboxManager.create()` already early-returns when the sandbox_key is in `_sandboxes`; lock that guarantee down with a regression test so a future refactor doesn't silently re-run setup.

- [ ] **Step 1: Write the regression test**

```python
# tests/unit/sandbox/test_ensure_sandbox_idempotence.py
"""Regression: `_install_dependencies` runs exactly once across repeat
`ensure_sandbox()` / `create()` calls for the same key.

RFC 2026-04-22 moves SWE-Bench per-task setup into `_install_dependencies`.
If `BaseSandboxManager.create()` ever stops early-returning on a cached
sandbox, setup scripts would re-run on every criterion-level
`ensure_sandbox()`. That would be silent but expensive — this test keeps
it caught."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_core.core.providers.sandbox.manager import BaseSandboxManager


class _ProbeManager(BaseSandboxManager):
    """Tiny subclass that counts `_install_dependencies` invocations."""

    install_calls: int = 0
    template = "test-template"

    async def _create_directory_structure(self, sandbox, sandbox_key) -> None:  # noqa: ANN001
        return None

    async def _install_dependencies(self, sandbox, task_id) -> None:  # noqa: ANN001
        type(self).install_calls += 1

    async def _verify_setup(self, sandbox, task_id) -> None:  # noqa: ANN001
        return None


@pytest.mark.asyncio
async def test_install_dependencies_runs_exactly_once_on_repeated_create() -> None:
    _ProbeManager.install_calls = 0
    task_id = uuid4()

    fake_sandbox = MagicMock()
    fake_sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="")
    )

    # Stub out the E2B sandbox creation path used by the base class.
    with patch.object(
        BaseSandboxManager,
        "_open_async_sandbox",
        AsyncMock(return_value=fake_sandbox),
    ):
        mgr = _ProbeManager()
        await mgr.create(task_id, run_id=task_id, timeout_minutes=30)
        await mgr.create(task_id, run_id=task_id, timeout_minutes=30)
        await mgr.create(task_id, run_id=task_id, timeout_minutes=30)

    assert _ProbeManager.install_calls == 1, (
        "BaseSandboxManager.create must early-return on a cached sandbox "
        "and NOT re-invoke _install_dependencies; otherwise criterion-level "
        "ensure_sandbox() calls will silently re-run SWE-Bench setup scripts."
    )
```

Note: if `BaseSandboxManager` does not expose a `_open_async_sandbox` helper, find the actual low-level factory used in `create()` (check lines around 231–300 of `manager.py`) and patch that instead. The spirit of the test — three creates, one install — is the invariant.

- [ ] **Step 2: Run the test**

```bash
uv run pytest tests/unit/sandbox/test_ensure_sandbox_idempotence.py -v
```

Expected: passes (the early-return already exists). If it fails, that itself is a bug — surface to human before moving on.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/sandbox/test_ensure_sandbox_idempotence.py
git commit -m "$(cat <<'EOF'
test(sandbox): regression — _install_dependencies runs exactly once

With SWE-Bench per-task setup scripts now running in
`_install_dependencies`, `BaseSandboxManager.create()`'s early-return
on a cached sandbox_key is load-bearing: any refactor that drops it
would silently re-run `setup_env_script` + `install_repo_script` on
every criterion-level `ensure_sandbox()` call. This test locks the
invariant in.

Resolves open question 2 of RFC 2026-04-22.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Add `CriterionRuntime.get_all_files_for_task`

**Files:**
- Modify: `ergon_core/ergon_core/api/criterion_runtime.py`
- Modify: `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py`
- Test: `tests/unit/runtime/test_criterion_runtime_get_all_files.py`

**Why:** RFC §3 adds this single materializing helper so criteria can pick up every file a task published without iterating `list_resources()` + `read_resource()` themselves.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/runtime/test_criterion_runtime_get_all_files.py
"""Unit tests for DefaultCriterionRuntime.get_all_files_for_task."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunResource


@pytest.fixture
def runtime_for_task(db_session, tmp_path):  # noqa: ARG001 — db_session side-effect
    """Yield (runtime, run_id, task_id)."""
    from ergon_core.core.runtime.evaluation.criterion_runtime import DefaultCriterionRuntime
    from ergon_core.core.runtime.evaluation.evaluation_schemas import CriterionContext

    run_id = uuid4()
    task_id = uuid4()
    ctx = CriterionContext(run_id=run_id, task_execution_id=task_id)
    runtime = DefaultCriterionRuntime(
        context=ctx,
        sandbox_manager=MagicMock(),
        run_id=run_id,
        task_id=task_id,
    )
    return runtime, run_id, task_id, tmp_path


def _write_resource(
    *,
    run_id,
    task_id,
    name: str,
    content: bytes,
    tmp_path: Path,
    created_at: datetime,
) -> None:
    path = tmp_path / f"{name}-{created_at.timestamp()}.bin"
    path.write_bytes(content)
    with get_session() as session:
        session.add(
            RunResource(
                id=uuid4(),
                run_id=run_id,
                task_execution_id=task_id,
                kind="output",
                name=name,
                mime_type="application/octet-stream",
                file_path=str(path),
                size_bytes=len(content),
                created_at=created_at,
            )
        )
        session.commit()


@pytest.mark.asyncio
async def test_returns_materialized_bytes(runtime_for_task) -> None:
    runtime, run_id, task_id, tmp = runtime_for_task
    now = datetime.now(UTC)
    _write_resource(
        run_id=run_id, task_id=task_id, name="a.txt",
        content=b"hello", tmp_path=tmp, created_at=now,
    )
    _write_resource(
        run_id=run_id, task_id=task_id, name="b.bin",
        content=b"\x00\x01\x02", tmp_path=tmp, created_at=now,
    )

    result = await runtime.get_all_files_for_task()
    assert result == {"a.txt": b"hello", "b.bin": b"\x00\x01\x02"}


@pytest.mark.asyncio
async def test_dedups_keeping_newest(runtime_for_task) -> None:
    runtime, run_id, task_id, tmp = runtime_for_task
    now = datetime.now(UTC)
    _write_resource(
        run_id=run_id, task_id=task_id, name="proof.lean",
        content=b"old", tmp_path=tmp, created_at=now - timedelta(seconds=5),
    )
    _write_resource(
        run_id=run_id, task_id=task_id, name="proof.lean",
        content=b"NEW", tmp_path=tmp, created_at=now,
    )

    result = await runtime.get_all_files_for_task()
    assert result == {"proof.lean": b"NEW"}


@pytest.mark.asyncio
async def test_scoped_to_own_task(runtime_for_task) -> None:
    runtime, run_id, task_id, tmp = runtime_for_task
    other_task_id = uuid4()
    now = datetime.now(UTC)
    _write_resource(
        run_id=run_id, task_id=task_id, name="mine.txt",
        content=b"mine", tmp_path=tmp, created_at=now,
    )
    _write_resource(
        run_id=run_id, task_id=other_task_id, name="not-mine.txt",
        content=b"other", tmp_path=tmp, created_at=now,
    )

    result = await runtime.get_all_files_for_task()
    assert "not-mine.txt" not in result
    assert result["mine.txt"] == b"mine"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/runtime/test_criterion_runtime_get_all_files.py -v
```

Expected: `AttributeError: 'DefaultCriterionRuntime' object has no attribute 'get_all_files_for_task'`.

- [ ] **Step 3: Extend the Protocol**

In `ergon_core/ergon_core/api/criterion_runtime.py`, add to the `# ── resource I/O ──` section:

```python
    async def get_all_files_for_task(self) -> "dict[str, bytes]":
        """Return `{name: bytes}` for every resource produced by this task.

        Scoped to the `(run_id, task_id)` the runtime was constructed with.
        On duplicate `name`s (same file published multiple times), the
        newest `created_at` wins. Not size-capped — callers expecting
        large resources should use `list_resources()` + `read_resource()`.
        """
        ...
```

- [ ] **Step 4: Implement on `DefaultCriterionRuntime`**

In `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py`, after `list_resources` (line ~231):

```python
    async def get_all_files_for_task(self) -> dict[str, bytes]:
        """See `CriterionRuntime.get_all_files_for_task`."""
        if self._task_id is None:
            return {}
        with get_session() as session:
            stmt = (
                select(RunResource)
                .where(RunResource.run_id == self._run_id)
                .where(RunResource.task_execution_id == self._task_id)
                .order_by(RunResource.created_at.desc())  # type: ignore[arg-type]
            )
            rows = list(session.exec(stmt).all())

        seen: set[str] = set()
        out: dict[str, bytes] = {}
        for row in rows:
            if row.name in seen:
                continue
            seen.add(row.name)
            out[row.name] = Path(row.file_path).read_bytes()
        return out
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/runtime/test_criterion_runtime_get_all_files.py -v
```

Expected: all three pass.

- [ ] **Step 6: Commit**

```bash
git add ergon_core/ergon_core/api/criterion_runtime.py \
        ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py \
        tests/unit/runtime/test_criterion_runtime_get_all_files.py
git commit -m "$(cat <<'EOF'
feat(criterion-runtime): add get_all_files_for_task helper

Materializing `(run_id, task_id)`-scoped helper that returns
`{name: bytes}` for every `run_resources` row produced by this task,
keeping the newest revision of each name. Criteria that want the whole
output bundle (MiniF2F proof + verifier log, etc.) call this once
instead of iterating `list_resources()` + `read_resource()`.

Protocol (api) + concrete impl both updated. Brings the Protocol
surface to 12 methods.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md §3

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Rewrite MiniF2F criterion to read from RunResources

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/minif2f/rules/proof_verification.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/minif2f/toolkit.py` (verify writes go to `/workspace/final_output/`)
- Test: `tests/unit/benchmarks/test_minif2f_proof_verification.py`

**Why:** RFC §3, path A. `lean_write_file` writes to `/workspace/final_output/final_solution.lean` (already confirmed from summary); `SandboxResourcePublisher.sync()` auto-publishes it; the criterion reads via `context.runtime.read_resource`.

- [ ] **Step 1: Open `toolkit.py` and confirm the write path**

```bash
grep -n "final_output\|/workspace" ergon_builtins/ergon_builtins/benchmarks/minif2f/toolkit.py
```

If the `lean_write_file` tool already writes to `/workspace/final_output/final_solution.lean`, no change is needed. If any path writes elsewhere (e.g. only to `/workspace/scratchpad/`), update the default `file_path` the docstring recommends to the final_output location. Log the finding.

- [ ] **Step 2: Write the failing criterion test**

```python
# tests/unit/benchmarks/test_minif2f_proof_verification.py
"""MiniF2F criterion reads proof via CriterionRuntime, not WorkerOutput.artifacts."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.minif2f.rules.proof_verification import (
    ProofVerificationCriterion,
)
from ergon_core.api import WorkerOutput
from ergon_core.api.criterion_runtime import CommandResult
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.task_types import BenchmarkTask


@pytest.mark.asyncio
async def test_reads_proof_via_runtime_read_resource() -> None:
    runtime = MagicMock()
    runtime.read_resource = AsyncMock(return_value=b"theorem t : True := by trivial")
    runtime.run_command = AsyncMock(
        return_value=CommandResult(stdout="[ok]", stderr="", exit_code=0)
    )

    context = EvaluationContext(
        run_id=uuid4(),
        task=BenchmarkTask(task_slug="t1", description="d", task_payload={}),
        worker_result=WorkerOutput(output="irrelevant", success=True),
        runtime=runtime,
    )

    criterion = ProofVerificationCriterion()
    result = await criterion.evaluate(context)

    runtime.read_resource.assert_awaited_once_with("final_solution.lean")
    # Whatever the criterion's verification impl decides, it must NOT
    # have touched `worker_result.artifacts`.
    assert result.name  # smoke: result is a well-formed CriterionResult


@pytest.mark.asyncio
async def test_scores_zero_when_proof_missing() -> None:
    from ergon_core.core.runtime.evaluation.criterion_runtime import ResourceNotFoundError

    runtime = MagicMock()
    runtime.read_resource = AsyncMock(side_effect=ResourceNotFoundError("missing"))

    context = EvaluationContext(
        run_id=uuid4(),
        task=BenchmarkTask(task_slug="t1", description="d", task_payload={}),
        worker_result=WorkerOutput(output="irrelevant", success=True),
        runtime=runtime,
    )

    criterion = ProofVerificationCriterion()
    result = await criterion.evaluate(context)
    assert result.score == 0.0
    assert not result.passed
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/unit/benchmarks/test_minif2f_proof_verification.py -v
```

Expected: fails — current `_extract_proof` reads `context.worker_result.artifacts.get("final_solution.lean")`.

- [ ] **Step 4: Rewrite `_extract_proof` in `proof_verification.py`**

Open the file at line ~97. Replace whatever the current body does with:

```python
    async def _extract_proof(self, context: EvaluationContext) -> str | None:
        """Return the Lean source the agent wrote, or None if missing.

        Reads from the task-scoped run_resource named
        ``final_solution.lean`` — published by
        ``SandboxResourcePublisher.sync()`` after the worker writes to
        ``/workspace/final_output/final_solution.lean``. The
        pre-RFC-2026-04-22 path through ``worker_result.artifacts`` is
        not used: ``artifacts`` is dropped at the Inngest
        ``worker_execute`` boundary.
        """
        if context.runtime is None:
            return None
        from ergon_core.core.runtime.evaluation.criterion_runtime import (
            ResourceNotFoundError,
        )

        try:
            raw = await context.runtime.read_resource("final_solution.lean")
        except ResourceNotFoundError:
            return None
        return raw.decode("utf-8", errors="replace")
```

If `_extract_proof` is called from a synchronous entry point, the caller must become `async`; trace upward and add `await` as needed.

- [ ] **Step 5: Update any other adjacent call that still reads `worker_result.artifacts`**

```bash
grep -n "worker_result.artifacts\|worker.artifacts" ergon_builtins/ergon_builtins/benchmarks/minif2f/
```

Remove any remaining reads. The criterion must read nothing from the artifacts dict.

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/unit/benchmarks/test_minif2f_proof_verification.py -v
```

Expected: both pass.

- [ ] **Step 7: Run fast suite**

```bash
pnpm run test:be:fast
```

Expected: green.

- [ ] **Step 8: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/minif2f \
        tests/unit/benchmarks/test_minif2f_proof_verification.py
git commit -m "$(cat <<'EOF'
refactor(minif2f): criterion reads proof via CriterionRuntime

`ProofVerificationCriterion._extract_proof` now calls
`context.runtime.read_resource("final_solution.lean")` and returns
`None` on `ResourceNotFoundError`. The pre-RFC path through
`worker_result.artifacts` is removed — `artifacts` is dropped at the
Inngest `worker_execute` boundary so reading from it was always
dead code masked by the deleted `MiniF2FAdapter.transform_output`.

The `lean_write_file` tool writes to
`/workspace/final_output/final_solution.lean`; auto-published by
`SandboxResourcePublisher.sync()` before sandbox teardown.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md §3

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Rewrite SWE-Bench criterion to compute patch via run_command

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py`
- Test: `tests/unit/benchmarks/test_swebench_criterion_patch_source.py`

**Why:** RFC §3, path B. The criterion owns the patch extraction now (`git add -A && git diff HEAD`); it no longer reads `worker.artifacts["patch"]` or falls back to `worker.output`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/benchmarks/test_swebench_criterion_patch_source.py
"""SWE-Bench criterion computes its own patch via runtime.run_command."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.swebench_verified.criterion import SWEBenchTestCriterion
from ergon_core.api import WorkerOutput
from ergon_core.api.criterion_runtime import CommandResult
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.task_types import BenchmarkTask


@pytest.mark.asyncio
async def test_criterion_computes_patch_via_run_command(monkeypatch) -> None:
    """The criterion must NOT read `worker.artifacts` or `worker.output`
    for the patch — it runs `git diff HEAD` itself."""
    runtime = MagicMock()
    # run_command is called many times (install, apply patches, run tests,
    # and — critically — to compute the patch). Return a benign patch for
    # the `git diff` invocation.
    def _fake_run(cmd: str, timeout: int = 30) -> CommandResult:
        if "git diff HEAD" in cmd:
            return CommandResult(
                stdout="diff --git a/x b/x\n-old\n+new\n",
                stderr="",
                exit_code=0,
            )
        return CommandResult(stdout="", stderr="", exit_code=0)

    runtime.run_command = AsyncMock(side_effect=_fake_run)
    runtime.ensure_sandbox = AsyncMock()

    # The old criterion still uses the sandbox-manager-under-runtime path;
    # we inject that.
    sandbox = MagicMock()
    sandbox.files.write = AsyncMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="PASSED")
    )

    runtime.sandbox_manager = MagicMock()
    runtime.sandbox_manager.get_sandbox = MagicMock(return_value=sandbox)

    payload = {
        "instance_id": "django__django-1",
        "repo": "django/django",
        "base_commit": "abc",
        "version": "4.2",
        "problem_statement": "x",
        "fail_to_pass": ["tests.t"],
        "pass_to_pass": [],
        "environment_setup_commit": "setup",
        "test_patch": "",
        "hints_text": "",
    }

    # Worker produces NO artifacts and empty output; criterion must still
    # derive the patch from the sandbox.
    context = EvaluationContext(
        run_id=uuid4(),
        task=BenchmarkTask(
            task_slug="django-1", description="d", task_payload=payload
        ),
        worker_result=WorkerOutput(output="", success=True),
        runtime=runtime,
    )

    criterion = SWEBenchTestCriterion()

    # Skip the heavy harness-grading path with a monkeypatch:
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.criterion.get_eval_report",
        lambda **kwargs: {
            payload["instance_id"]: {"resolved": True, "tests_status": {}}
        },
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.criterion.make_test_spec",
        lambda row: MagicMock(install_repo_script=":", eval_script=":"),
    )

    result = await criterion.evaluate(context)

    # At least one call to run_command must have been `git diff HEAD`.
    git_diff_calls = [
        call for call in runtime.run_command.await_args_list
        if "git diff HEAD" in call.args[0]
    ]
    assert git_diff_calls, (
        "criterion must compute its own patch via runtime.run_command('… git diff HEAD …')"
    )
    assert result.passed is True  # matches the monkeypatched harness report
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/benchmarks/test_swebench_criterion_patch_source.py -v
```

Expected: fails — current criterion reads `(worker.artifacts or {}).get("patch") or worker.output` at line 110.

- [ ] **Step 3: Rewrite the `evaluate` patch-acquisition block**

In `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py`:

Replace line 110:

```python
patch_text = (worker.artifacts or {}).get("patch") or worker.output or ""
```

with:

```python
patch_text = await _extract_patch_via_runtime(context)
```

Add at module level, below the imports:

```python
async def _extract_patch_via_runtime(context: EvaluationContext) -> str:
    """Compute `git add -A && git diff HEAD` via the criterion runtime."""
    if context.runtime is None:
        raise RuntimeError(
            "SWEBenchTestCriterion requires a CriterionRuntime for patch "
            "extraction; none was injected."
        )
    await context.runtime.ensure_sandbox()
    result = await context.runtime.run_command(
        f"cd {WORKDIR} && git add -A && git diff HEAD",
        timeout=120,
    )
    if result.exit_code != 0:
        return ""
    return result.stdout or ""
```

The rest of `evaluate()` (the empty-patch check, harness invocation, grading) stays unchanged — it already operates on a local `patch_text` variable.

Also remove the now-unused variable reference: `worker = context.worker_result` at line 109 may still be used later (e.g. for `worker.output` as a fallback). Confirm and drop if dead.

- [ ] **Step 4: Run the test**

```bash
uv run pytest tests/unit/benchmarks/test_swebench_criterion_patch_source.py -v
```

Expected: pass.

- [ ] **Step 5: Run fast suite**

```bash
pnpm run test:be:fast
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py \
        tests/unit/benchmarks/test_swebench_criterion_patch_source.py
git commit -m "$(cat <<'EOF'
refactor(swebench): criterion computes patch via runtime.run_command

`SWEBenchTestCriterion.evaluate()` no longer reads `worker.artifacts["patch"]`
or the worker's output as a fallback. It extracts the patch itself by
running `git add -A && git diff HEAD` via `context.runtime.run_command`
after `ensure_sandbox()`.

This closes the original "artifacts are dropped at the Inngest boundary"
workaround: the criterion goes straight to the source of truth (the
sandbox working tree), so the data path no longer depends on the
worker routing the patch through `WorkerOutput.output` as a fallback.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md §3

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Deprecate `WorkerOutput.artifacts` docstring

**Files:**
- Modify: `ergon_core/ergon_core/api/results.py`

**Why:** RFC §3 leaves the field in place for a follow-up PR (removal would ripple into every Worker subclass + test) but marks it as deprecated in the docstring so future readers see the anti-pattern.

- [ ] **Step 1: Edit `results.py`**

Locate the `WorkerOutput.artifacts` field and replace its `Field(...)` with the deprecation docstring from the RFC:

```python
    artifacts: dict[str, Any] = Field(  # slopcop: ignore[no-typing-any]
        default_factory=dict,
        description=(
            "DEPRECATED. This field is NOT carried across the durable "
            "worker→evaluator boundary (dropped at "
            "inngest/worker_execute.py). Do not use for files or data "
            "the criterion needs to read. Files → write to "
            "/workspace/final_output/ (auto-published as RunResources by "
            "SandboxResourcePublisher.sync). Computed artifacts → have "
            "the criterion run commands in the sandbox via "
            "CriterionRuntime.run_command. "
            "Slated for removal once no in-tree worker writes to it."
        ),
    )
```

(If the field already lacks `slopcop: ignore[no-typing-any]` but `dict[str, Any]` needs it, add the trailing `# slopcop: ignore[no-typing-any]` comment to the `artifacts:` type annotation line.)

- [ ] **Step 2: Run full check**

```bash
pnpm run check:be
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add ergon_core/ergon_core/api/results.py
git commit -m "$(cat <<'EOF'
docs(api): deprecate WorkerOutput.artifacts with explanatory docstring

The field stays on the return contract (removal is a separate PR) but
its description now warns that it is dropped at the Inngest
worker_execute boundary and points readers at
/workspace/final_output/ + CriterionRuntime as the supported channels.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md §3

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Rename `output_text` → `final_assistant_message` (code side)

**Files (27 tracked files per prior grep):**
- Modify: `ergon_core/ergon_core/core/runtime/services/inngest_function_results.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/orchestration_dto.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/task_execution_service.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/task_inspection_service.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/child_function_payloads.py` (`worker_output_text` → `worker_final_assistant_message`)
- Modify: `ergon_core/ergon_core/core/runtime/services/evaluator_dispatch_service.py`
- Modify: `ergon_core/ergon_core/core/runtime/inngest/execute_task.py`
- Modify: `ergon_core/ergon_core/core/runtime/inngest/persist_outputs.py`
- Modify: `ergon_core/ergon_core/core/runtime/inngest/worker_execute.py`
- Modify: `ergon_core/ergon_core/core/persistence/telemetry/models.py` (`RunTaskExecution` column attribute)
- Modify: `ergon_core/ergon_core/core/persistence/telemetry/repositories.py`
- Modify: `ergon_core/ergon_core/core/api/runs.py` (line 162)
- Modify: `ergon_core/ergon_core/core/api/schemas.py` (line 64)
- Modify: `ergon_core/ergon_core/core/dashboard/emitter.py` (if the grep hit it)
- Modify: every test file found in the grep that references `output_text` (or `worker_output_text`) in production-path assertions; tests under `.claude/worktrees/` are siblings and should NOT be touched
- Modify: `docs/event-wal/01_AUDIT.md`, `docs/event-wal/02_INCREMENTAL_PERSISTENCE.md`, `docs/rfcs/active/2026-04-17-cleanup-cancelled-task-release-sandbox.md` (doc updates)
- Modify: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/sandbox_utils.py` (the unexpected hit — investigate; may be a legitimate reader)

**Why:** RFC §4. Fifteen+ files carry the same field through three layers. Do the rename atomically in one commit (excluding the Alembic migration, which is Task 16).

- [ ] **Step 1: Refresh the full inventory**

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
git ls-files | xargs grep -l "output_text\|worker_output_text" 2>/dev/null | \
  grep -v "^\.claude/worktrees" | \
  grep -v "^docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md" | \
  sort -u
```

The second `grep -v` excludes this RFC and the current plan doc (which legitimately reference `output_text` in their explanations — those stay as historical record). Write the resulting list to `/tmp/rename-inventory.txt`.

- [ ] **Step 2: Investigate `ergon_builtins/benchmarks/gdpeval/sandbox_utils.py`**

```bash
grep -n "output_text" ergon_builtins/ergon_builtins/benchmarks/gdpeval/sandbox_utils.py
```

If it's a legitimate reader of `RunTaskExecution.output_text`, rename the attribute access. If it's a local variable named `output_text` (unrelated), leave it alone. Note the choice in the commit message.

- [ ] **Step 3: Rename the dataclass / pydantic field in `inngest_function_results.py`**

```python
# Before
output_text: str | None = None
# After
final_assistant_message: str | None = None
```

Same in `orchestration_dto.py` for `FinalizeTaskExecutionCommand`.

- [ ] **Step 4: Rename `RunTaskExecution.output_text` in `telemetry/models.py`**

Locate line 120. Change:

```python
output_text: str | None = None
```

to:

```python
final_assistant_message: str | None = None
```

- [ ] **Step 5: Rename `child_function_payloads.py` carrier field**

`PersistOutputsRequest.worker_output_text` → `PersistOutputsRequest.worker_final_assistant_message`. Update the docstring comment accordingly.

- [ ] **Step 6: Cascade every call-site and attribute access**

For each file in `/tmp/rename-inventory.txt`, open and rename. The two patterns are:
- `.output_text` → `.final_assistant_message`
- `output_text=` → `final_assistant_message=`
- `worker_output_text` → `worker_final_assistant_message`

**Do NOT blindly sed** — some test strings may contain "output_text" as assertion text about the old name; those should rename. But raw string literals in docs/event-wal that are quoting the *deprecated name for historical context* stay.

Recommended: for each file, open, read, make each rename consciously. The fast cross-cut:

```bash
for f in $(cat /tmp/rename-inventory.txt); do
  echo "=== $f ==="
  grep -n "output_text\|worker_output_text" "$f"
done
```

- [ ] **Step 7: Verify nothing outside docs/RFC references the old names**

```bash
git ls-files | xargs grep -l "output_text\|worker_output_text" 2>/dev/null | \
  grep -v "^docs/" | \
  grep -v "^\.claude/worktrees"
```

Expected output: empty (or only this plan file if it's been committed).

- [ ] **Step 8: Run `ty` to confirm all attribute accesses resolve**

```bash
uv run ty check ergon_core ergon_builtins tests
```

Expected: clean. Any "unresolved attribute output_text" means a site was missed.

- [ ] **Step 9: Run fast suite**

```bash
pnpm run test:be:fast
```

Expected: green. The rename is a pure symbol substitution; behavior is unchanged.

- [ ] **Step 10: Commit (without migration — next task)**

```bash
git add -A
git status  # verify scope
git commit -m "$(cat <<'EOF'
refactor(rename): output_text → final_assistant_message across layers

Rename carried through three layers end-to-end:

- `WorkerExecuteResult.output_text` → `final_assistant_message`
- `FinalizeTaskExecutionCommand.output_text` → `final_assistant_message`
- `PersistOutputsRequest.worker_output_text` → `worker_final_assistant_message`
- `RunTaskExecution.output_text` (ORM attribute) → `final_assistant_message`
  (DB column rename lands in next commit's Alembic migration)
- Dashboard API + CLI readers of `output_text` renamed
- Tests updated to assert the new name

The old name collided with `CommandResult.stdout` ("output") and with
files under `/workspace/final_output/`. The new name matches the
`assistant_text` context event that produces this value.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md §4

NOTE: ORM and DB column are temporarily out of sync until the next
commit applies the Alembic migration. Do NOT run against a live
database between these two commits.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Alembic migration for column rename

**Files:**
- Create: `ergon_core/migrations/versions/<timestamp>_rename_output_text_to_final_assistant_message.py`

**Why:** Simple column rename on `run_task_executions`. The ORM attribute is already renamed (Task 15); this brings the DB schema into sync.

- [ ] **Step 1: Identify the current head revision**

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
ls ergon_core/migrations/versions/*.py | sort
```

From prior inspection the newest revision is `f9075c2ddbc9_run_resource_append_only_log.py` or newer. Confirm:

```bash
grep -l "down_revision.*=.*None" ergon_core/migrations/versions/*.py 2>/dev/null  # earliest
# Find the head by looking for no down_revision referencing it:
for f in ergon_core/migrations/versions/*.py; do
  rev=$(grep -oE "revision: str = \"[^\"]+\"" "$f" | grep -oE "\"[^\"]+\"" | tr -d '"')
  down=$(grep -oE "down_revision: Union\[str, None\] = \"[^\"]+\"" "$f" | grep -oE "\"[^\"]+\"" | tr -d '"')
  echo "$rev → $down   ($f)"
done
```

The head is the `revision` value that does not appear as any file's `down_revision`. Save it as `HEAD_REV`.

- [ ] **Step 2: Generate the new revision file**

Name: `<new_hash>_rename_output_text_to_final_assistant_message.py`. Use `uv run alembic revision` if available; otherwise hand-write:

```bash
uv run alembic -c ergon_core/alembic.ini revision -m "rename output_text to final_assistant_message" 2>&1
```

If alembic autogen isn't set up here, create the file manually as below.

- [ ] **Step 3: Write the migration**

```python
# ergon_core/migrations/versions/<new_hash>_rename_output_text_to_final_assistant_message.py
"""rename output_text to final_assistant_message

Revision ID: <generated>
Revises: <HEAD_REV>
Create Date: 2026-04-22 00:00:00.000000

Column rename on run_task_executions. No data transform. The ORM
attribute was renamed in the preceding commit; this migration brings
the DB schema into sync. RFC: 2026-04-22-worker-interface-and-artifact-routing.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "<generated>"
down_revision: Union[str, None] = "<HEAD_REV>"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "run_task_executions",
        "output_text",
        new_column_name="final_assistant_message",
    )


def downgrade() -> None:
    op.alter_column(
        "run_task_executions",
        "final_assistant_message",
        new_column_name="output_text",
    )
```

Replace `<generated>` with a fresh 12-char hex id (you can use `python -c "import secrets; print(secrets.token_hex(6))"`). Replace `<HEAD_REV>` with the value saved in Step 1.

- [ ] **Step 4: Apply the migration locally and run tests**

```bash
uv run alembic -c ergon_core/alembic.ini upgrade head
pnpm run test:be:fast
```

Expected: migration applies cleanly; tests green.

- [ ] **Step 5: Commit**

```bash
git add ergon_core/migrations/versions/<new_hash>_rename_output_text_to_final_assistant_message.py
git commit -m "$(cat <<'EOF'
migrate: rename run_task_executions.output_text column

Simple column rename; no data transform. Paired with the prior commit
that renamed the ORM attribute from `output_text` to
`final_assistant_message`. Revision chains onto the previous head.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md §4

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 17: Update architecture docs in the same PR

**Files:**
- Modify: `docs/architecture/01_public_api.md`
- Modify: `docs/architecture/06_builtins.md`
- Modify: `docs/architecture/cross_cutting/artifacts.md`
- Modify: `docs/architecture/04_sandbox_lifecycle.md`

**Why:** CLAUDE.md mandates in-PR architecture-doc updates for every feature PR that changes public API, invariants, or anti-patterns. This PR changes all three.

- [ ] **Step 1: Update `docs/architecture/01_public_api.md`**

Add / revise the Worker contract section. Use the RFC "Invariants affected → 01_public_api.md" block verbatim as the source.

- Document `Tool` alias exported from `ergon_core.api`.
- Document the base `Worker.__init__` kwargs (no defaults).
- Document `ReActWorker.__init__` kwargs (all required).
- Update `CriterionRuntime` method list to include `get_all_files_for_task`. State surface-area count (12).
- Add the `final_assistant_message` naming invariant line.

- [ ] **Step 2: Update `docs/architecture/06_builtins.md`**

Remove the "ReAct adapter composition" section (if present, added in commit `a9819fe`). Replace with a "ReAct toolkit composition" section describing the factory-closure pattern.

Add three anti-patterns to the anti-patterns list (copy verbatim from RFC "Invariants affected → 06_builtins.md"):

- Worker subclasses for per-benchmark glue
- Per-task setup inside workers
- Nullable-with-default kwargs on concrete Worker `__init__`

- [ ] **Step 3: Update `docs/architecture/cross_cutting/artifacts.md`**

Add the "Invariants" bullet (copy verbatim from RFC "Invariants affected → cross_cutting/artifacts.md"):

> - `WorkerOutput.artifacts` is a non-durable field. It is dropped at the Inngest `worker_execute` step boundary and is not a channel to criteria. File-shaped artifacts are published via `SandboxResourcePublisher.sync()` from `/workspace/final_output/`; criteria read them via `CriterionRuntime.read_resource(name)` or `get_all_files_for_task()`. Computed artifacts (e.g. `git diff`) are produced by the criterion itself via `CriterionRuntime.run_command(...)`.

Remove any obsolete "use `WorkerOutput.artifacts` for evaluator-visible data" guidance.

- [ ] **Step 4: Update `docs/architecture/04_sandbox_lifecycle.md`**

Add the per-task-setup invariant (copy verbatim from RFC "Invariants affected → 04_sandbox_lifecycle.md"):

> For benchmarks that require per-task environment setup (clone a specific commit, install version-pinned deps, apply a harness spec), that work runs inside `BaseSandboxManager._install_dependencies(sandbox, task_id)` — not inside the worker's `execute()`, not inside a separate `on_run_start` hook, and not inside the criterion. Managers that need per-task data (payload, instance-id metadata) read it from the data layer via `queries.task_executions.get_task_payload(task_id)`; `SandboxSetupRequest` carries only `task_id`, not the full payload.

- [ ] **Step 5: Verify all arch docs still render (no broken cross-refs)**

```bash
grep -rn "output_text\|BenchmarkAdapter\|WorkerOutput.artifacts" docs/architecture/
```

Fix any stale references.

- [ ] **Step 6: Commit**

```bash
git add docs/architecture/
git commit -m "$(cat <<'EOF'
docs(arch): update public-api + builtins + artifacts + sandbox docs

In-PR architecture-doc updates paired with the code changes:

- 01_public_api.md — tightened Worker contract, `Tool` alias,
  CriterionRuntime surface (12 methods), `final_assistant_message`
  naming invariant.
- 06_builtins.md — replace "ReAct adapter composition" with
  "ReAct toolkit composition"; add three anti-pattern bullets.
- cross_cutting/artifacts.md — `WorkerOutput.artifacts` non-durability
  invariant.
- 04_sandbox_lifecycle.md — per-task setup runs in
  `_install_dependencies`, payload fetched via `queries.task_executions`.

RFC: docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: Full verification + push

**Files:** none (meta-task)

- [ ] **Step 1: Run the full `check:fast` pipeline**

```bash
pnpm run check:fast
```

Expected: backend + frontend both clean. Fix any fallout from upstream renames in the dashboard (`ergon-dashboard/`) if the generated TypeScript bindings reference `output_text`.

- [ ] **Step 2: Run both test suites**

```bash
pnpm run test:be:fast
pnpm run test:be:state
```

Expected: all green.

- [ ] **Step 3: Confirm PR #27 still tracks the branch**

```bash
git log --oneline main..HEAD | head -30
gh pr view 27 --json title,state,baseRefName,headRefName
```

Expected: PR exists, open, head is `feature/real-llm-harness-infra`.

- [ ] **Step 4: Push**

```bash
git push origin feature/real-llm-harness-infra
```

- [ ] **Step 5: Update the RFC open-questions list to reflect resolutions**

Open `docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md`. In the "Open questions" section, mark each resolved:

- Q1 (non-benchmark worker kwarg shape): **Resolved — option (a)**: every plain worker is wrapped in `_plain(cls)` in the registry; subclasses themselves don't learn about `task_id` / `sandbox_id`.
- Q2 (ensure_sandbox idempotence): **Resolved** — regression test at `tests/unit/sandbox/test_ensure_sandbox_idempotence.py`.
- Q3 (read_resource_text helper): **Resolved — no**. Criteria decode explicitly at the call site.

Commit + push:

```bash
git add docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md
git commit -m "$(cat <<'EOF'
rfc(worker-interface): resolve open questions 1/2/3

- Q1: plain workers wrapped in `_plain(cls)` registry shim; subclasses
  don't learn about task_id / sandbox_id.
- Q2: regression test locks _install_dependencies=1 across repeat
  ensure_sandbox().
- Q3: no `read_resource_text` helper; criteria decode at call site.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"

git push origin feature/real-llm-harness-infra
```

- [ ] **Step 6: On merge (post-review)**

After PR #27 merges, a follow-up (not part of this plan):

1. `git mv docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md docs/rfcs/accepted/`
2. Open a tracking issue for the `WorkerOutput.artifacts` field removal once no in-tree worker writes to it.

---

## Self-review checklist

**1. Spec coverage.** Walked the RFC section-by-section:

- Proposal §1 (Worker interface) → Tasks 1 (Tool alias), 2 (base Worker), 3 (subclasses), 4 (ReActWorker), 5 (delete adapters), 6 (registry factories), 7 (worker_execute call-site).
- Proposal §2 (setup scripts + payload lookup) → Tasks 8 (`get_task_payload`), 9 (`_install_dependencies`), 10 (ensure_sandbox idempotence regression — Open Q2).
- Proposal §3 (artifact→evaluator routing) → Tasks 11 (`get_all_files_for_task`), 12 (MiniF2F criterion), 13 (SWE-Bench criterion), 14 (`WorkerOutput.artifacts` deprecation).
- Proposal §4 (output_text rename) → Tasks 15 (code), 16 (Alembic migration).
- Invariants affected (all four arch docs) → Task 17.
- Open Q1 resolved by Task 6's `_plain(cls)` shim. Open Q3 resolved in Task 18 RFC update.

**2. Placeholder scan.** No "TBD" / "fill in" / "add appropriate error handling" / "similar to Task N" strings. Every step has concrete code or an exact command.

**3. Type consistency.**

- `Tool` is used consistently as `list[Tool]` in Tasks 1 (definition), 4 (ReActWorker signature), 6 (factory closures).
- `queries.task_executions.get_task_payload(task_execution_id)` signature matches in Task 8 (definition), Task 9 (first usage).
- `get_all_files_for_task()` return type `dict[str, bytes]` consistent between Task 11's Protocol extension, implementation, and test assertions.
- `final_assistant_message` is the final attribute name in every layer: `WorkerExecuteResult`, `FinalizeTaskExecutionCommand`, `RunTaskExecution`, with the carrier `PersistOutputsRequest.worker_final_assistant_message` prefixed as the existing `worker_output_text` was.

**4. Commit-granularity invariant.** Tasks 4 + 5 are the only pair that commits together (Task 4 leaves `registry_core.py` temporarily broken and Task 5 repairs it in the very next commit). Task 15 (code rename) + Task 16 (Alembic migration) likewise form a two-commit pair with a DO-NOT-RUN-AGAINST-PROD note. Every other task is atomically committable. This matches CLAUDE.md's "frequent commits" guidance while preserving the atomic nature of the rename.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-22-worker-interface-and-artifact-routing.md`.

Per the controller context (this is the continuation of writing-plans → subagent-driven-development flow), the next step is to execute this plan via the `superpowers:subagent-driven-development` skill on branch `feature/real-llm-harness-infra`, dispatching one implementer subagent per task, followed by two-stage review (spec compliance, then code quality) before moving to the next task.
