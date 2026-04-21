---
status: active
opened: 2026-04-18
author: deepflow-research
architecture_refs:
  - docs/architecture/03_providers.md#sandbox-managers
  - docs/architecture/03_providers.md#invariants
supersedes: []
superseded_by: null
---

# RFC: Sandbox manager — drop singleton, move state to instances, add cross-process reconnect

## 1. Problem

`BaseSandboxManager`
(`ergon_core/ergon_core/core/providers/sandbox/manager.py`) is wired as a
singleton-per-subclass via `__new__` at `manager.py:78-81`:

```python
def __new__(cls, *args: object, **kwargs: object):
    if cls._instance is None:
        cls._instance = super().__new__(cls)
    return cls._instance
```

Six class-level mutable dicts are declared at `manager.py:65-71`:

```python
_instance: "BaseSandboxManager | None" = None
_sandboxes: dict[UUID, "AsyncSandbox"] = {}
_file_registries: dict[UUID, dict[str, str]] = {}
_created_files_registry: dict[UUID, set[str]] = {}
_run_ids: dict[UUID, UUID] = {}
_display_task_ids: dict[UUID, UUID] = {}
_creation_locks: dict[UUID, asyncio.Lock] = {}
```

These dicts are **shared across every instance of a subclass** for the
process lifetime. Entries are cleared only by `terminate()` at
`manager.py:429-469`. Three concrete problems follow.

### 1.1 Invisible in-process coupling

Workers reconnect to their sandbox in `execute()` by re-instantiating the
subclass and calling `get_sandbox(task_id)` at `manager.py:394-396`:

```python
def get_sandbox(self, task_id: UUID) -> "AsyncSandbox | None":
    return self._sandboxes.get(task_id)
```

Example: `MiniF2FReActWorker.execute()` at
`ergon_builtins/ergon_builtins/workers/baselines/minif2f_react_worker.py:111-113`:

```python
manager = MiniF2FSandboxManager()
sandbox = manager.get_sandbox(context.task_id)
```

Nothing in the signature says "worker must run in same process as the
`sandbox_setup_fn` that created it." The coupling is invisible: if the
Inngest worker runs in a different process replica the call silently returns
`None` and the task fails with a confusing error.

The same pattern appears in:

- `ergon_builtins/ergon_builtins/workers/baselines/swebench_worker.py:123`
- `ergon_builtins/ergon_builtins/workers/research_rubrics/researcher_worker.py:74`
- `ergon_builtins/ergon_builtins/workers/research_rubrics/stub_worker.py:78`
- `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py:72`

`ResearchRubricsSandboxManager` (in
`ergon_core/ergon_core/core/providers/sandbox/research_rubrics_manager.py`) also
calls `self._sandboxes[task_id]` directly at `research_rubrics_manager.py:105`
in `publisher_for()`, relying on the class-level dict.

`DefaultCriterionRuntime.ensure_sandbox()` at
`ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py:53-63`
calls `self.sandbox_manager.get_sandbox(self.context.run_id)` — it would
return `None` across processes even though the sandbox row exists in the DB.

### 1.2 Latent `__init__` stomp race

`__init__` at `manager.py:85-87` is last-write-wins:

```python
def __init__(self, event_sink: SandboxEventSink | None = None):
    if event_sink is not None:
        self._event_sink = event_sink
```

Because `__new__` always returns the cached instance, every call to
`MiniF2FSandboxManager(event_sink=sink)` re-runs `__init__` on the **same**
object. A second construction with a different `event_sink` silently replaces
the first. This is the root cause documented in
`docs/bugs/open/2026-04-18-sandbox-manager-shared-state-race.md`. No
production site hits it today: all 5 construction sites omit `event_sink=`.
The latent hazard is real and blocks any future DI injection of per-test sinks.

Tests work around this at
`tests/minif2f/test_sandbox_manager.py:23-35` by manually resetting all six
class-level dicts in an `autouse` fixture — a sign that the design is leaking
its internals.

### 1.3 Unbounded memory growth

The class-level dicts grow with every task. Entries are evicted only by
`terminate()`. Any task that crashes before reaching `terminate()` leaks its
entry for the process lifetime. This is noted in `manager.py:63-64` and in
`docs/architecture/03_providers.md` Section 4.1:

> **Class-dict unbounded growth.** Manager class-level state is cleared only
> inside `terminate()`. Any task that never reaches `terminate()` leaks its
> entries for the process lifetime.

For long-lived research training processes this is a genuine memory hazard.

### 1.4 Impossible multi-process scale-out

`docs/architecture/03_providers.md` Section 2.2 states:

> A subclass's class-level state is the only source of truth for in-process
> reconnect. Applies only within a single Python process; cross-process actors
> must use `terminate_by_sandbox_id` or provision their own sandbox.

There is no `reconnect(sandbox_id)` method. In-process criteria reconnect via
`get_sandbox(task_id)`. Cross-process criteria (SWE-Bench) provision fresh
sandboxes at `swebench_verified/criterion.py:66-78`. If the backend is ever
split into multi-replica Inngest workers or async worker pools, the reconnect
path silently returns `None` and evaluation breaks.

### 1.5 Scope boundary with key-cleanup RFC

`docs/rfcs/active/2026-04-18-sandbox-manager-key-cleanup.md` collapses the
`sandbox_key` / `display_task_id` triplet in `create()`. That RFC is
**orthogonal**: either order of landing is correct. This RFC does not change
the `create()` signature; key-cleanup can proceed independently. Implementation
order: prefer key-cleanup first (smaller scope, unblocks readable diffs), then
process-state.

---

## 2. Proposal

Stop relying on process-global state in the sandbox manager. Four concrete
changes, implemented in three staged PRs.

### Option A — Instance-state migration (chosen)

1. **Move state from class-level to instance-level.** `_sandboxes`, `_run_ids`,
   `_file_registries`, `_created_files_registry`, `_display_task_ids`, and
   `_creation_locks` become instance attributes initialized in `__init__`. No
   class-level mutable dicts.
2. **Drop the singleton.** Remove `__new__` (`manager.py:78-81`) and
   `_instance` (`manager.py:65`). The construction site in
   `ergon_core/ergon_core/core/runtime/inngest/sandbox_setup.py:57`
   (`sandbox_manager = manager_cls()`) already creates one manager per
   function invocation; that behavior becomes correct rather than accidentally
   correct.
3. **Add `reconnect(sandbox_id: str) -> AsyncSandbox`.** Uses the E2B API
   (`AsyncSandbox.connect`) to rehydrate a sandbox by its persisted id. Criteria
   in a different process can reconnect given only the `sandbox_id` column on
   the execution row.
4. **Update criterion path.** `DefaultCriterionRuntime.ensure_sandbox()` at
   `criterion_runtime.py:53-63` stops calling `manager.get_sandbox(task_id)` on
   a shared dict and instead calls `reconnect(context.sandbox_id)` when the
   manager's in-memory dict has no entry.

### Options considered and rejected

See Section 13.

---

## 3. Architecture overview

### 3.1 Before (current state)

```
sandbox_setup_fn (process A)
  │
  ├─ manager_cls = SANDBOX_MANAGERS["minif2f"]      # MiniF2FSandboxManager
  ├─ sandbox_manager = manager_cls()                # returns SAME instance via __new__
  │       MiniF2FSandboxManager._instance cached
  │       MiniF2FSandboxManager._sandboxes[task_id] = <AsyncSandbox>
  │
  └─ returns sandbox_id="sbx-abc123"  (persisted to DB)

worker_execute_fn (process A — must be SAME process)
  │
  ├─ manager = MiniF2FSandboxManager()              # hits __new__, gets cached instance
  └─ sandbox = manager.get_sandbox(context.task_id) # reads class-level _sandboxes dict
                                                     # returns None if different process
```

### 3.2 After (this RFC)

```
sandbox_setup_fn (process A)
  │
  ├─ manager_cls = SANDBOX_MANAGERS["minif2f"]
  ├─ sandbox_manager = manager_cls()                # new fresh instance — no singleton
  │       instance._sandboxes[task_id] = <AsyncSandbox>
  │
  └─ returns sandbox_id="sbx-abc123"  (persisted to DB)

worker_execute_fn (any process)
  │
  ├─ manager = manager_cls()                        # new fresh instance
  └─ sandbox = await manager.reconnect("sbx-abc123") # AsyncSandbox.connect via E2B API
                                                      # works cross-process

DefaultCriterionRuntime.ensure_sandbox() (any process)
  │
  ├─ sandbox = self.sandbox_manager.get_sandbox(task_id)   # in-memory: None in new proc
  └─ if None: sandbox = await manager.reconnect(context.sandbox_id)
```

### 3.3 Data flow change

| Field | Before | After |
|---|---|---|
| `_instance` | `ClassVar` | removed |
| `_sandboxes` | `ClassVar[dict]` — shared | `instance dict` — per-construction |
| `_run_ids` | `ClassVar[dict]` | `instance dict` |
| `_file_registries` | `ClassVar[dict]` | `instance dict` |
| `_created_files_registry` | `ClassVar[dict]` | `instance dict` |
| `_display_task_ids` | `ClassVar[dict]` | `instance dict` |
| `_creation_locks` | `ClassVar[dict]` | `instance dict` |
| `reconnect(sandbox_id)` | does not exist | `async def reconnect(str) -> AsyncSandbox` |

---

## 4. Type / interface definitions

### 4.1 Updated `BaseSandboxManager.__init__`

```python
# ergon_core/ergon_core/core/providers/sandbox/manager.py

class BaseSandboxManager(ABC):
    """Abstract base class for E2B sandbox lifecycle management.

    One instance per sandbox_setup_fn invocation.  Instance-level dicts
    replace the former class-level shared state; the singleton-per-subclass
    pattern (__new__) is removed.

    Cross-process reconnect: call reconnect(sandbox_id) with the sandbox_id
    persisted on the TaskExecution row to rehydrate an AsyncSandbox without
    access to the in-process _sandboxes dict.
    """

    template: str | None = None  # ClassVar stays; it is read-only config

    def __init__(self, event_sink: SandboxEventSink | None = None) -> None:
        # Instance-level state — no class-level shared dicts.
        self._sandboxes: dict[UUID, AsyncSandbox] = {}
        self._file_registries: dict[UUID, dict[str, str]] = {}
        self._created_files_registry: dict[UUID, set[str]] = {}
        self._run_ids: dict[UUID, UUID] = {}
        self._display_task_ids: dict[UUID, UUID] = {}
        self._creation_locks: dict[UUID, asyncio.Lock] = {}
        self._event_sink: SandboxEventSink = event_sink or NoopSandboxEventSink()
```

### 4.2 `reconnect` method signature

```python
# ergon_core/ergon_core/core/providers/sandbox/manager.py

    async def reconnect(self, sandbox_id: str) -> "AsyncSandbox":
        """Rehydrate a running sandbox by its E2B sandbox_id.

        Uses the E2B API directly — does not require the sandbox to have
        been created by this instance or in this process.  Returns a live
        AsyncSandbox handle.

        Does NOT cache the result on self._sandboxes — callers are expected
        to hold the reference for their scope.  Revisit if E2B rate limits
        become a problem (see Open Questions).

        Raises RuntimeError if e2b_code_interpreter is not installed or
        if the sandbox is no longer alive.
        """
        if AsyncSandbox is None:
            raise RuntimeError(
                "e2b_code_interpreter is not installed; cannot reconnect to sandbox."
            )
        return await AsyncSandbox.connect(sandbox_id, api_key=settings.e2b_api_key)
```

### 4.3 `DefaultCriterionRuntime.ensure_sandbox` updated signature

```python
# ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py

    async def ensure_sandbox(self) -> None:
        """Ensure a live sandbox is available for this criterion's context.

        In-process: reads self.sandbox_manager._sandboxes via get_sandbox().
        Cross-process: reconnects via reconnect(context.sandbox_id) if
        get_sandbox returns None and context.sandbox_id is set.
        Creates a fresh sandbox only if both paths yield nothing.
        """
        sandbox = self.sandbox_manager.get_sandbox(self.context.run_id)
        if sandbox is None and self.context.sandbox_id:
            # Cross-process case: sandbox was created in a different process.
            await self.sandbox_manager.reconnect(self.context.sandbox_id)
            return
        if sandbox is None:
            await self.sandbox_manager.create(
                self.context.run_id,
                run_id=self.context.run_id,
                timeout_minutes=30,
            )
            self._owns_sandbox = True
            return
        await self.sandbox_manager.reset_timeout(self.context.run_id, timeout_minutes=30)
```

---

## 5. Full implementations

### 5.1 `BaseSandboxManager` — full diff region

The diff below covers `manager.py:50-90` (the class header and `__init__`):

```diff
 class BaseSandboxManager(ABC):
-    """Abstract base class for E2B sandbox management."""
+    """Abstract base class for E2B sandbox lifecycle management.
+
+    One instance per sandbox_setup_fn invocation.  Instance-level dicts
+    replace the former class-level shared state; the singleton pattern is
+    removed.  Use reconnect(sandbox_id) for cross-process sandbox access.
+    """

     # Optional name or ID of a pre-built E2B template. ClassVar — read-only.
     template: str | None = None

-    # Class-level state: shared across every instance of this subclass.
-    # Entries are only evicted by terminate(). Tasks that crash without
-    # terminate() leak their entries forever.
-    # docs/rfcs/active/2026-04-18-sandbox-manager-process-state.md.
-    _instance: "BaseSandboxManager | None" = None
-    _sandboxes: dict[UUID, "AsyncSandbox"] = {}
-    _file_registries: dict[UUID, dict[str, str]] = {}
-    _created_files_registry: dict[UUID, set[str]] = {}
-    _run_ids: dict[UUID, UUID] = {}
-    _display_task_ids: dict[UUID, UUID] = {}
-    _creation_locks: dict[UUID, asyncio.Lock] = {}
-    _event_sink: SandboxEventSink
-
-    # TODO(2026-04-18): Singleton-per-subclass with class-level state dicts is load-bearing
-    # for same-process criterion reconnect via `get_sandbox(task_id)`. This forecloses
-    # multi-process scale-out and creates a latent stomp risk on `_event_sink` in __init__.
-    # Broader reform tracked in docs/rfcs/active/2026-04-18-sandbox-manager-process-state.md.
-    def __new__(cls, *args: object, **kwargs: object):
-        if cls._instance is None:
-            cls._instance = super().__new__(cls)
-        return cls._instance
-
-    _event_sink: SandboxEventSink = NoopSandboxEventSink()
-
-    def __init__(self, event_sink: SandboxEventSink | None = None):
-        if event_sink is not None:
-            self._event_sink = event_sink
+    def __init__(self, event_sink: SandboxEventSink | None = None) -> None:
+        # Instance-level state — no class-level shared dicts.
+        self._sandboxes: dict[UUID, "AsyncSandbox"] = {}
+        self._file_registries: dict[UUID, dict[str, str]] = {}
+        self._created_files_registry: dict[UUID, set[str]] = {}
+        self._run_ids: dict[UUID, UUID] = {}
+        self._display_task_ids: dict[UUID, UUID] = {}
+        self._creation_locks: dict[UUID, asyncio.Lock] = {}
+        self._event_sink: SandboxEventSink = event_sink or NoopSandboxEventSink()
```

### 5.2 `reconnect` — new method added after `get_sandbox`

Add after `manager.py:396` (after `get_sandbox`):

```diff
+    async def reconnect(self, sandbox_id: str) -> "AsyncSandbox":
+        """Rehydrate a running sandbox by its E2B sandbox_id.
+
+        Uses the E2B API directly — works cross-process.  Does NOT cache the
+        result on self._sandboxes; callers hold the reference.
+        """
+        if AsyncSandbox is None:
+            raise RuntimeError(
+                "e2b_code_interpreter is not installed; cannot reconnect to sandbox."
+            )
+        return await AsyncSandbox.connect(sandbox_id, api_key=settings.e2b_api_key)
+
     def get_sandbox_path(self, task_id: UUID, local_path: str) -> str | None:
```

### 5.3 `DefaultCriterionRuntime.ensure_sandbox` — updated

Diff against `criterion_runtime.py:53-63`:

```diff
-    async def ensure_sandbox(self) -> None:
-        sandbox = self.sandbox_manager.get_sandbox(self.context.run_id)
-        if sandbox is None:
-            await self.sandbox_manager.create(
-                self.context.run_id,
-                run_id=self.context.run_id,
-                timeout_minutes=30,
-            )
-            self._owns_sandbox = True
-            return
-        await self.sandbox_manager.reset_timeout(self.context.run_id, timeout_minutes=30)
+    async def ensure_sandbox(self) -> None:
+        sandbox = self.sandbox_manager.get_sandbox(self.context.run_id)
+        if sandbox is None and self.context.sandbox_id:
+            # Cross-process path: reconnect to the sandbox created in sandbox_setup_fn.
+            await self.sandbox_manager.reconnect(self.context.sandbox_id)
+            return
+        if sandbox is None:
+            await self.sandbox_manager.create(
+                self.context.run_id,
+                run_id=self.context.run_id,
+                timeout_minutes=30,
+            )
+            self._owns_sandbox = True
+            return
+        await self.sandbox_manager.reset_timeout(self.context.run_id, timeout_minutes=30)
```

**Note:** `CriterionContext.sandbox_id` must be a `str | None` field. If it
does not exist today, it must be added to
`ergon_core/ergon_core/core/runtime/evaluation/evaluation_schemas.py` as part
of Stage 3. Check this file before landing Stage 3.

### 5.4 `ResearchRubricsSandboxManager.publisher_for` — no change needed

`publisher_for` at `research_rubrics_manager.py:93-110` calls
`self._sandboxes[task_id]`. Once `_sandboxes` is an instance dict, this is
correct: the caller (a worker's `execute()`) holds the manager instance that
was used to create the sandbox, so `_sandboxes[task_id]` is populated. No
code change needed here; the test fixture cleanup (`_reset_sandbox_singleton`)
is deleted since there is no singleton to reset.

### 5.5 `sandbox_setup_fn` construction site — no change needed

`sandbox_setup.py:57`:

```python
sandbox_manager = manager_cls()
```

This already constructs a fresh instance per invocation. After removing
`__new__`, the call is identical but now returns a genuinely fresh object
rather than the cached singleton. No code change.

### 5.6 Worker construction sites — no change needed

`minif2f_react_worker.py:111`, `swebench_worker.py:123`,
`researcher_worker.py:74`, `stub_worker.py:78`, `criterion.py:72` all do
`ManagerClass()`. After this RFC, those calls produce fresh instances. If a
worker calls `get_sandbox(task_id)` on a fresh instance, the dict will be
empty (reconnect path needed). Stage 3 addresses the criterion path
(`criterion_runtime.py`). For workers that call `get_sandbox` in `execute()`:
the sandbox was created by `sandbox_setup_fn` in a **different** Inngest step,
so the worker's freshly constructed manager has no entry. Workers must either:

- Receive the manager instance via DI (prerequisite:
  `docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md`), or
- Call `reconnect(context.sandbox_id)` directly.

**Stage 3 must update these worker sites.** Until then, keep the singleton
(Stage 1 only) to avoid a regression. Stage 2 (drop singleton) gates on all
worker sites being updated.

---

## 6. Implementation order

Phased into three PRs to avoid a flag day.

### Phase 1 — Extract to instance-level (keep singleton)

**PR 1: "sandbox-manager: instance-state migration (singleton preserved)"**

| Step | What | Files touched |
|---|---|---|
| 1 | Move the six class-level dicts into `__init__` as instance attrs; set `_event_sink` cleanly in `__init__` | `manager.py` |
| 2 | Keep `__new__` in place (singleton preserved) | `manager.py` |
| 3 | Remove the vestigial `_event_sink: SandboxEventSink = NoopSandboxEventSink()` class-level assignment at `manager.py:83` | `manager.py` |
| 4 | Add test: construct same subclass twice; assert both dicts are the same object (singleton still) and are initialized | `tests/state/test_sandbox_manager_instance_state.py` (ADD) |
| 5 | Add test: assert `BaseSandboxManager` has no class-level mutable dicts (inspects `__dict__` and class `__dict__`) — fails if any reappear | `tests/state/test_sandbox_manager_instance_state.py` |
| 6 | Delete the `_reset_sandbox_singleton` autouse fixture from `tests/minif2f/test_sandbox_manager.py` and `tests/swebench_verified/test_sandbox_manager.py` — replace with normal per-test construction | `tests/minif2f/test_sandbox_manager.py`, `tests/swebench_verified/test_sandbox_manager.py` |

Behavior unchanged. Stage 1 is a pure refactor.

### Phase 2 — Remove singleton

**PR 2: "sandbox-manager: remove __new__ singleton" (depends on PR 1)**

| Step | What | Files touched |
|---|---|---|
| 7 | Delete `__new__` from `BaseSandboxManager` | `manager.py` |
| 8 | Delete `_instance: ClassVar` from `BaseSandboxManager` | `manager.py` |
| 9 | Update docstrings in architecture doc (Section 2.2 `03_providers.md`) — remove singleton-per-subclass language | `docs/architecture/03_providers.md` |
| 10 | Add `reconnect(sandbox_id: str) -> AsyncSandbox` to `BaseSandboxManager` | `manager.py` |
| 11 | Add unit test: `reconnect` calls `AsyncSandbox.connect` with correct `sandbox_id` and `api_key`; mock `AsyncSandbox` | `tests/state/test_sandbox_manager_instance_state.py` |
| 12 | Add multi-run isolation test: two manager instances with overlapping `task_id` values do not share sandbox state | `tests/state/test_sandbox_manager_instance_state.py` |

### Phase 3 — Update criterion path

**PR 3: "sandbox-manager: criterion reconnect via sandbox_id" (depends on PR 2)**

| Step | What | Files touched |
|---|---|---|
| 13 | Add `sandbox_id: str | None = None` to `CriterionContext` if absent | `ergon_core/ergon_core/core/runtime/evaluation/evaluation_schemas.py` |
| 14 | Update `DefaultCriterionRuntime.ensure_sandbox()` to call `reconnect` when `get_sandbox` returns None and `context.sandbox_id` is set | `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py` |
| 15 | Update worker sites that call `get_sandbox` in `execute()`: replace with `reconnect(context.sandbox_id)` or receive manager via DI | `minif2f_react_worker.py`, `researcher_worker.py`, `stub_worker.py` (MODIFY) |
| 16 | Update `swebench_verified/criterion.py:72-78` (`_spawn_eval_sandbox`) to construct a standalone fresh manager (already does this — verify no class-level state bleed) | `swebench_verified/criterion.py` |
| 17 | Update `docs/architecture/03_providers.md` Section 2.2 — replace "in-process reconnect via class state" language with cross-process reconnect contract | `docs/architecture/03_providers.md` |
| 18 | Close `docs/bugs/open/2026-04-18-sandbox-manager-shared-state-race.md` — move to `fixed/` | `docs/bugs/` |
| 19 | Integration test: criterion running in a simulated second-process context reconnects via `sandbox_id` and executes a command | `tests/state/test_sandbox_manager_instance_state.py` |

---

## 7. File map

### ADD

| File | Purpose |
|---|---|
| `ergon/tests/state/test_sandbox_manager_instance_state.py` | Unit + integration tests: instance isolation, singleton removal, reconnect, multi-run isolation |

### MODIFY

| File | Changes |
|---|---|
| `ergon/ergon_core/ergon_core/core/providers/sandbox/manager.py` | Stage 1: move six dicts to `__init__`, fix `_event_sink` init; Stage 2: remove `__new__` + `_instance`, add `reconnect()` |
| `ergon/ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py` | Stage 3: update `ensure_sandbox()` to use `reconnect()` on cross-process miss |
| `ergon/ergon_core/ergon_core/core/runtime/evaluation/evaluation_schemas.py` | Stage 3: add `sandbox_id: str \| None = None` to `CriterionContext` if absent |
| `ergon/ergon_builtins/ergon_builtins/workers/baselines/minif2f_react_worker.py` | Stage 3: replace `manager.get_sandbox(context.task_id)` with `reconnect` or DI |
| `ergon/ergon_builtins/ergon_builtins/workers/research_rubrics/researcher_worker.py` | Stage 3: same |
| `ergon/ergon_builtins/ergon_builtins/workers/research_rubrics/stub_worker.py` | Stage 3: same |
| `ergon/tests/minif2f/test_sandbox_manager.py` | Stage 1: remove `_reset_sandbox_singleton` autouse fixture |
| `ergon/tests/swebench_verified/test_sandbox_manager.py` | Stage 1: same |
| `ergon/docs/architecture/03_providers.md` | Stage 2+3: remove singleton-per-subclass language; update Section 2.2, 3, 4, 5.2, 6 |

---

## 8. Testing approach

### 8.1 Unit tests — `test_sandbox_manager_instance_state.py`

```python
# ergon/tests/state/test_sandbox_manager_instance_state.py

"""Tests for sandbox manager instance-state migration (RFC 2026-04-18-process-state)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_core.core.providers.sandbox.manager import BaseSandboxManager


class _MinimalManager(BaseSandboxManager):
    """Concrete subclass for testing — no deps."""

    async def _install_dependencies(self, sandbox, task_id):  # noqa: ANN001, ARG002
        pass


class TestInstanceIsolation:
    """After Stage 1: two instances of the same subclass must not share state."""

    def test_two_instances_have_independent_sandboxes_dicts(self) -> None:
        m1 = _MinimalManager()
        m2 = _MinimalManager()
        # After Stage 2 (singleton removed), these are distinct objects.
        # After Stage 1 (singleton preserved), same object — skip in Stage 1 run.
        assert m1._sandboxes is not m2._sandboxes or m1 is m2  # noqa: S101

    def test_sandbox_added_to_one_not_visible_in_other(self) -> None:
        m1 = _MinimalManager()
        m2 = _MinimalManager()
        if m1 is m2:
            pytest.skip("singleton still present — Stage 1 only")
        fake_sb = MagicMock()
        task_id = uuid4()
        m1._sandboxes[task_id] = fake_sb
        assert m2.get_sandbox(task_id) is None

    def test_no_class_level_mutable_dicts(self) -> None:
        """BaseSandboxManager class dict must not contain mutable dicts."""
        class_dict = vars(BaseSandboxManager)
        mutable_class_attrs = {
            k: v
            for k, v in class_dict.items()
            if isinstance(v, dict) and k.startswith("_") and k != "__dict__"
        }
        assert mutable_class_attrs == {}, (
            f"Found class-level mutable dicts: {list(mutable_class_attrs.keys())}"
        )

    def test_event_sink_initialized_in_init(self) -> None:
        from ergon_core.core.providers.sandbox.event_sink import NoopSandboxEventSink
        m = _MinimalManager()
        assert isinstance(m._event_sink, NoopSandboxEventSink)

    def test_custom_event_sink_set_without_stomp(self) -> None:
        from ergon_core.core.providers.sandbox.event_sink import NoopSandboxEventSink
        sink_a = NoopSandboxEventSink()
        sink_b = NoopSandboxEventSink()
        m1 = _MinimalManager(event_sink=sink_a)
        m2 = _MinimalManager(event_sink=sink_b)
        if m1 is m2:
            pytest.skip("singleton still present — stomp still possible in Stage 1")
        assert m1._event_sink is sink_a
        assert m2._event_sink is sink_b


class TestMultiRunIsolation:
    """Cross-run isolation: two manager instances with overlapping task_ids."""

    def test_overlapping_task_ids_independent(self) -> None:
        m1 = _MinimalManager()
        m2 = _MinimalManager()
        if m1 is m2:
            pytest.skip("singleton still present")
        task_id = uuid4()  # same UUID on both instances
        fake_sb1 = MagicMock()
        fake_sb2 = MagicMock()
        m1._sandboxes[task_id] = fake_sb1
        m2._sandboxes[task_id] = fake_sb2
        assert m1.get_sandbox(task_id) is fake_sb1
        assert m2.get_sandbox(task_id) is fake_sb2


class TestReconnect:
    """Stage 2: reconnect() calls AsyncSandbox.connect with correct args."""

    @pytest.mark.asyncio
    async def test_reconnect_calls_connect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from ergon_core.core.providers.sandbox import manager as mgr_module

        fake_sandbox = MagicMock()
        fake_connect = AsyncMock(return_value=fake_sandbox)
        fake_async_sandbox = MagicMock()
        fake_async_sandbox.connect = fake_connect
        monkeypatch.setattr(mgr_module, "AsyncSandbox", fake_async_sandbox)
        monkeypatch.setattr(mgr_module.settings, "e2b_api_key", "test-key")

        m = _MinimalManager()
        result = await m.reconnect("sbx-xyz-999")

        fake_connect.assert_awaited_once_with("sbx-xyz-999", api_key="test-key")
        assert result is fake_sandbox

    @pytest.mark.asyncio
    async def test_reconnect_raises_when_e2b_not_installed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ergon_core.core.providers.sandbox import manager as mgr_module

        monkeypatch.setattr(mgr_module, "AsyncSandbox", None)

        m = _MinimalManager()
        with pytest.raises(RuntimeError, match="e2b_code_interpreter is not installed"):
            await m.reconnect("sbx-xyz-999")

    @pytest.mark.asyncio
    async def test_reconnect_does_not_cache_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """reconnect() must not populate self._sandboxes (stateless by design)."""
        from ergon_core.core.providers.sandbox import manager as mgr_module

        fake_sandbox = MagicMock()
        fake_connect = AsyncMock(return_value=fake_sandbox)
        monkeypatch.setattr(mgr_module, "AsyncSandbox", MagicMock(connect=fake_connect))
        monkeypatch.setattr(mgr_module.settings, "e2b_api_key", "key")

        m = _MinimalManager()
        await m.reconnect("sbx-001")
        assert len(m._sandboxes) == 0


class TestEnsureSandboxCrossProcess:
    """Stage 3: DefaultCriterionRuntime.ensure_sandbox() uses reconnect."""

    @pytest.mark.asyncio
    async def test_ensure_sandbox_reconnects_when_get_sandbox_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ergon_core.core.runtime.evaluation.criterion_runtime import (
            DefaultCriterionRuntime,
        )
        from ergon_core.core.runtime.evaluation.evaluation_schemas import CriterionContext

        fake_sandbox = MagicMock()
        fake_reconnect = AsyncMock(return_value=fake_sandbox)
        fake_manager = MagicMock()
        fake_manager.get_sandbox = MagicMock(return_value=None)
        fake_manager.reconnect = fake_reconnect

        ctx = CriterionContext(
            run_id=uuid4(),
            task_id=uuid4(),
            sandbox_id="sbx-from-db",
        )
        runtime = DefaultCriterionRuntime(context=ctx, sandbox_manager=fake_manager)
        await runtime.ensure_sandbox()

        fake_reconnect.assert_awaited_once_with("sbx-from-db")
        assert not runtime._owns_sandbox
```

### 8.2 Regression tests

Existing tests in `tests/minif2f/test_sandbox_manager.py` and
`tests/swebench_verified/test_sandbox_manager.py` must continue to pass. The
`_reset_sandbox_singleton` autouse fixtures are deleted in Stage 1; tests
that previously needed them now work naturally because each test constructs
a fresh instance.

After Stage 2, add a regression test that `BaseSandboxManager` has no `__new__`
override (inspect `BaseSandboxManager.__new__ is object.__new__`).

### 8.3 Multi-run isolation test (critical)

The most important behavioral test: two concurrent runs must not share sandbox
entries. Covered by `TestMultiRunIsolation.test_overlapping_task_ids_independent`
above. This test skips under Stage 1 and passes under Stage 2.

---

## 9. Trace / observability impact

### 9.1 Spans

No span schema change. The `sandbox.setup` span emitted at `sandbox_setup.py:76-90`
already records `sandbox_id` as an attribute. After this RFC, that `sandbox_id`
is the durable reconnect key.

### 9.2 Logs

Add one `logger.debug` to `reconnect()`:

```python
logger.debug(
    "sandbox.reconnect sandbox_id=%s",
    sandbox_id,
)
```

This distinguishes reconnect calls from create calls in log output during
Stage 3 rollout, when both paths coexist.

### 9.3 Metrics

No new metrics. The `sandbox.setup` span attributes are sufficient for
observing the lifecycle transition. If reconnect latency becomes a concern,
add a `sandbox.reconnect` span mirroring `sandbox.setup`.

---

## 10. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Worker `execute()` calls `get_sandbox()` on fresh instance — returns None | High (Stage 2) | Task fails at first `sandbox.commands.run` call | Stage 2 gates on worker sites updated to use `reconnect` or DI. Stage 1 keeps singleton — no regression. |
| `AsyncSandbox.connect` fails if sandbox expired | Medium | Criterion or worker fails with `RuntimeError` | E2B 30-minute idle timeout is the canonical safety net. `reconnect` raises `RuntimeError`; callers should surface it with the `sandbox_id` for diagnosis. |
| Stage 2 removes singleton before all callers updated | Medium | Silent `None` return from `get_sandbox` | PR sequence enforced: PR 2 must list updated callers in PR description. CI test `test_no_class_level_mutable_dicts` catches regression. |
| `CriterionContext` missing `sandbox_id` field | Low (field may already exist) | Stage 3 `ensure_sandbox` cannot pass `sandbox_id` to `reconnect` | Verify `evaluation_schemas.py` before Stage 3 PR. Add field if absent. |
| Subclass `__init__` forgets `super().__init__()` | Low | Instance dicts not initialized; `AttributeError` on first `create()` | Add `test_no_class_level_mutable_dicts` which instantiates all registered subclasses and checks `_sandboxes` is an instance attribute. |
| Test suite assumes singleton reset via `_reset_sandbox_singleton` fixture | Low | Flaky tests after Stage 1 fixture deletion | Delete fixture in Stage 1 PR; confirm all tests pass before merging. |

---

## 11. Invariants affected

### 11.1 `docs/architecture/03_providers.md` — invariants to rewrite

**Section 2.2 (Sandbox managers) — changes:**

- Remove: "singleton per subclass" — `BaseSandboxManager` is both abstract and a
  **singleton per subclass**.
- Remove: "This works only because all actors run inside the same Python process."
- Add: "One instance per `sandbox_setup_fn` invocation. Instance-level dicts
  replace class-level shared state. No `__new__` caching."
- Add: "`reconnect(sandbox_id)` provides cross-process access to a running sandbox
  given only the `sandbox_id` string persisted on the `TaskExecution` row."
- Remove footnote: "event_sink stomp" (Section 2.2 last paragraph).

**Section 3 (Control flow diagram) — changes:**

Replace:

```
+-> ManagerClass()                    (singleton; returns cached instance)
|   ManagerClass().create(sandbox_key=task_id, run_id=run_id, ...)
```

With:

```
+-> sandbox_manager = ManagerClass()  (fresh instance per setup invocation)
|   sandbox_manager.create(task_id=task_id, run_id=run_id, ...)
```

And replace:

```
criteria reconnect via ManagerClass().get_sandbox(task_id)
    (works because singleton + shared class state;
     cross-process criteria spawn a fresh sandbox instead)
```

With:

```
criteria reconnect via manager.reconnect(sandbox_id)
    (E2B API call; works cross-process)
```

**Section 4 (Invariants) — changes:**

- Invariant 3 currently: "Singleton managers hold authoritative sandbox state."
  Replace with: "**Manager instances own per-invocation sandbox state.** No
  class-level mutable dicts. Cross-process reconnect uses `reconnect(sandbox_id)`
  against the E2B API."
- Section 4.1 "Known limits" — remove "Constructor `event_sink` stomp" and
  "Class-dict unbounded growth" bullets.
  Add: "**Memory:** each `BaseSandboxManager` instance holds refs to its sandboxes
  for its lifetime. After `terminate()`, all refs are released."

**Section 5.2 (Add a new sandbox manager) — changes:**

Step 4: replace "Treat the class as a singleton — re-instantiation is how callers
acquire the cached instance" with "Construct one instance per run in
`sandbox_setup_fn`; pass it through context or DI to workers and criteria."

Step 5: replace "Do NOT pass `event_sink=` at construction today; the stomp
described in Section 2.2 makes that unsafe" with "Pass `event_sink=` at
construction safely; the stomp is eliminated."

**Section 6 (Anti-patterns) — changes:**

- Remove: "Constructing an `AsyncSandbox` directly from worker or criterion code."
  Replace: keep the anti-pattern but add "use `reconnect(sandbox_id)` to acquire
  a cross-process handle; the manager still owns template pinning and teardown."
- Remove: "Passing `event_sink=` at manager construction." (stomp no longer exists)

---

## 12. Alternatives considered

### Keep the singleton, wrap class-level dicts in a bounded LRU

Rejected. Hides the coupling problem behind an eviction policy and still cannot
scale out of one process. Evicting an entry under load would silently break a
running task. The root cause — shared mutable class state — is not addressed.

### Leave as-is and document the single-process assumption forever

Rejected. The assumption is load-bearing for every rollout path; codifying it
forecloses future scale-out. Ergon is research-grade today but should not
hard-lock itself in with a design that is actively wrong under the most likely
scaling path (multi-replica Inngest).

### Move reconnect into criterion runtime only, keep manager as singleton

Rejected. Partial fix: the unbounded-growth and invisible-coupling problems
remain for every non-criterion code path. The `_reset_sandbox_singleton` test
fixture would still be needed.

### Thread manager instance through `WorkerContext`

A reasonable approach for Stage 3. Workers receive `WorkerContext` in
`execute()` and could receive a `sandbox_manager` field on it. Deferred: this
couples `WorkerContext` (an `ergon_core` public API type) to
`BaseSandboxManager`, which is also in `ergon_core` but has E2B as an optional
dep. The DI path in
`docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md` is the right
vehicle for this — Stage 3 should coordinate with that RFC.

---

## 13. Open questions

- Should `reconnect` cache the rehydrated `AsyncSandbox` on the instance, or
  return a fresh handle each call? Lean stateless for cross-process safety;
  revisit if E2B rate limits bite.
- Do long-running RL training loops want a manager pool keyed by run_id, or
  is per-run construction cheap enough? Defer until measured.
- Stage 3 coordination with
  `docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md`: that RFC
  exposes `get_sandbox()` through `CriterionRuntime`. After this RFC,
  `get_sandbox` becomes an in-process-only convenience; the primary
  cross-process entry point is `reconnect`. The DI container RFC should
  expose `reconnect` or accept a pre-connected `AsyncSandbox` handle.

---

## 14. On acceptance

- Move this RFC to `accepted/`.
- Update `docs/architecture/03_providers.md` per Section 11 above — remove
  singleton-per-subclass paragraphs (`03_providers.md` Section 2.2, line 32
  and line 43–44), Section 3 diagram, Section 4 invariant 3, Section 4.1
  known-limits bullets, Section 5.2 step 4–5, Section 6 anti-patterns.
- Close `docs/bugs/open/2026-04-18-sandbox-manager-shared-state-race.md` — per
  the new invariant, instances cannot race on shared class-level dicts. Move
  to `docs/bugs/fixed/`.
- Address TODO at `manager.py:74-77` referencing this RFC; the comment block
  is deleted along with `__new__`.
- Link the implementation plan under `docs/superpowers/plans/`.
- Coordinate Stage 3 timing with
  `docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md` — both touch
  `criterion_runtime.py`.
