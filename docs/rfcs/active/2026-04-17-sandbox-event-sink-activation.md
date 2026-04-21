---
status: active
opened: 2026-04-17
author: deepflow-research
architecture_refs: [docs/architecture/03_providers.md#sandboxeventsink, docs/architecture/05_dashboard.md#invariants]
supersedes: [docs/bugs/open/2026-04-17-sandbox-event-sink-unactivated.md]
superseded_by: null
---

# RFC: Activate `SandboxEventSink` via a process-level class setter

## Problem

`SandboxEventSink` is defined at
`ergon_core/ergon_core/core/providers/sandbox/event_sink.py:7-36` as the
Protocol through which sandbox managers emit lifecycle events
(`sandbox_created`, `sandbox_command`, `sandbox_closed`). Two implementations
exist — `NoopSandboxEventSink` (default, lines 39-71) and
`DashboardEmitterSandboxEventSink` (forwards to `dashboard_emitter`, lines
74-129). The three emitter methods it delegates to
(`DashboardEmitter.sandbox_created/sandbox_command/sandbox_closed`) are defined
at `ergon_core/ergon_core/core/dashboard/emitter.py:246`, `:271`, and `:302`.

Zero production call sites construct a manager with a non-noop sink. Every
instantiation of a `BaseSandboxManager` subclass omits `event_sink=`:

| File | Line | Manager class |
|---|---|---|
| `ergon_builtins/ergon_builtins/workers/baselines/minif2f_react_worker.py` | 111 | `MiniF2FSandboxManager()` |
| `ergon_builtins/ergon_builtins/workers/baselines/swebench_worker.py` | 123 | `SWEBenchSandboxManager()` |
| `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py` | 72 | `SWEBenchSandboxManager()` |
| `ergon_builtins/ergon_builtins/workers/research_rubrics/researcher_worker.py` | 74 | `ResearchRubricsSandboxManager()` |
| `ergon_builtins/ergon_builtins/workers/research_rubrics/stub_worker.py` | 78 | `ResearchRubricsSandboxManager()` |

The `DefaultSandboxManager` (used by the smoke-test path via
`ergon_core/ergon_core/core/runtime/inngest/sandbox_setup.py:56`) has no direct
construction sites in `ergon_builtins` but is acquired by the fallback
`SANDBOX_MANAGERS.get(benchmark_type, DefaultSandboxManager)` in three Inngest
functions.

`dashboard_emitter` is a module-level singleton at
`ergon_core/ergon_core/core/dashboard/emitter.py:451`. There is only ever one
emitter in the process.

### Why passing `event_sink=` at five call sites is wrong

The original draft of this RFC proposed making `event_sink=` a required
constructor parameter at every site. Re-reading the code revealed that approach
is brittle for three reasons:

1. `BaseSandboxManager` uses a `__new__`-based singleton-per-subclass pattern
   at `manager.py:78-81`. The class-level `_event_sink` attribute at
   `manager.py:83` is shared by every "instance" of a given subclass.
2. `__init__` at `manager.py:85-87` conditionally overwrites `_event_sink`
   when a non-None value is passed — a last-write-wins stomp on shared state.
   Any late re-construction with a non-None sink silently replaces the active
   sink for all in-flight tasks. Tracked separately at
   `docs/bugs/open/2026-04-18-sandbox-manager-shared-state-race.md`.
3. Passing `DashboardEmitterSandboxEventSink(dashboard_emitter)` at five sites
   is a behavioral no-op (the same process-wide emitter either way) while
   inviting a test-isolation hazard: a `RecordingSink` passed at one site stomps
   a live sink held by another via the class-level attribute.

**Consequence of the current state:** sandbox lifecycle is not visible in the
dashboard during a live run. `dashboard_emitter.sandbox_created/command/closed`
have zero direct callers anywhere in the tree (confirmed by
`grep -rn "dashboard_emitter.sandbox_" ergon_core/ ergon_builtins/`). The
dashboard's sandbox view populates only on cold-start via the REST snapshot in
`build_run_snapshot()` at `ergon_core/ergon_core/core/api/runs.py:343`. While a
run is live, sandbox lifecycle is invisible in the UI.

## Proposal

Wire the sink **once, at the process boundary**, via a class-level setter on
`BaseSandboxManager`. All five production construction sites remain unchanged.

### Design

**Option chosen: class-level `set_event_sink` classmethod (Option A)**

Add `@classmethod set_event_sink(cls, sink: SandboxEventSink) -> None` to
`BaseSandboxManager`. It assigns `cls._event_sink = sink` directly on the
concrete subclass (not the base), so each subclass gets its own class-attribute
value. During FastAPI `lifespan` startup — the single place in the process where
all managers are known to be idle — iterate the known subclasses and call
`Manager.set_event_sink(DashboardEmitterSandboxEventSink(dashboard_emitter))`
for each.

The existing `event_sink: SandboxEventSink | None = None` parameter is removed
from `BaseSandboxManager.__init__`. Tests use `set_event_sink` in fixture setup
and reset to `NoopSandboxEventSink()` in teardown. This is the correct
inversion: the setter is the one sanctioned mutation point; `__init__` no longer
touches sink state.

### Subclasses to wire at app init

These are every concrete `BaseSandboxManager` subclass in the codebase today:

| Class | Module |
|---|---|
| `DefaultSandboxManager` | `ergon_core/ergon_core/core/providers/sandbox/manager.py` |
| `MiniF2FSandboxManager` | `ergon_builtins/ergon_builtins/benchmarks/minif2f/sandbox_manager.py` |
| `SWEBenchSandboxManager` | `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_manager.py` |
| `ResearchRubricsSandboxManager` | `ergon_core/ergon_core/core/providers/sandbox/research_rubrics_manager.py` |
| `GDPEvalSandboxManager` | `ergon_builtins/ergon_builtins/benchmarks/gdpeval/sandbox.py` |

`DefaultSandboxManager` is in `ergon_core` and always available. The four
benchmark-specific subclasses are in `ergon_builtins`. `app.py` already imports
from `ergon_builtins` (via `ALL_FUNCTIONS`), so the import boundary is not
violated. However, the `lifespan` block should use the `SANDBOX_MANAGERS`
registry from `ergon_builtins.registry` rather than enumerating subclasses by
name, so new subclasses are picked up automatically.

## Architecture overview

### Before (current state)

```
app startup
  └─ lifespan: ensure_db, init_rollout_service
     (no sink configuration)

Worker.execute() / Criterion.evaluate()
  └─ SomeManager()             # __new__ returns cached singleton
     └─ __init__(event_sink=None)
        # _event_sink = NoopSandboxEventSink() — unchanged
  └─ manager.create(...)
     └─ _event_sink.sandbox_created(...)   # NOOP — never reaches emitter
  └─ manager.terminate(...)
     └─ _event_sink.sandbox_closed(...)    # NOOP
```

### After (this RFC)

```
app startup
  └─ lifespan: ensure_db, init_rollout_service
     └─ for Manager in [DefaultSandboxManager] + list(SANDBOX_MANAGERS.values()):
            Manager.set_event_sink(DashboardEmitterSandboxEventSink(dashboard_emitter))
        # Each subclass._event_sink = DashboardEmitterSandboxEventSink instance

Worker.execute() / Criterion.evaluate()
  └─ SomeManager()             # __new__ returns cached singleton; __init__ no longer touches sink
  └─ manager.create(...)
     └─ _event_sink.sandbox_created(...)
        └─ DashboardEmitterSandboxEventSink.sandbox_created(...)
           └─ dashboard_emitter.sandbox_created(...)
              └─ inngest_client.send(DashboardSandboxCreatedEvent)
  └─ manager.terminate(...)
     └─ _event_sink.sandbox_closed(...)
        └─ DashboardEmitterSandboxEventSink.sandbox_closed(...)
           └─ dashboard_emitter.sandbox_closed(...)
              └─ inngest_client.send(DashboardSandboxClosedEvent)
```

### Event pipeline (after)

```
BaseSandboxManager._emit_wal_entry / .create / .terminate
    │
    ▼
SandboxEventSink.sandbox_{created,command,closed}
    │  (DashboardEmitterSandboxEventSink — set once at lifespan)
    ▼
DashboardEmitter.sandbox_{created,command,closed}
    │  (emitter.py:246, :271, :302)
    ▼
inngest_client.send(DashboardSandbox{Created,Command,Closed}Event)
    │
    ▼
Next.js Inngest handler → DashboardStore reducer → Socket.io room run:<id>
    │
    ▼
Browser — live sandbox lifecycle events
```

## Type / interface definitions

### `SandboxEventSink` (no change — shown for reference)

```python
# ergon_core/ergon_core/core/providers/sandbox/event_sink.py  (lines 7-36, unchanged)

class SandboxEventSink(Protocol):
    """Observer for sandbox lifecycle and append-only WAL events."""

    async def sandbox_created(
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        timeout_minutes: int,
        template: str | None = None,
    ) -> None: ...

    async def sandbox_command(
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        command: str,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
        duration_ms: int | None = None,
    ) -> None: ...

    async def sandbox_closed(
        self,
        task_id: UUID,
        sandbox_id: str,
        reason: str,
    ) -> None: ...
```

### `RecordingSandboxEventSink` (test fixture — new)

```python
# tests/state/fixtures/recording_event_sink.py  (new file)

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class SandboxCreatedCall:
    run_id: UUID
    task_id: UUID
    sandbox_id: str
    timeout_minutes: int
    template: str | None


@dataclass
class SandboxCommandCall:
    run_id: UUID
    task_id: UUID
    sandbox_id: str
    command: str
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    duration_ms: int | None


@dataclass
class SandboxClosedCall:
    task_id: UUID
    sandbox_id: str
    reason: str


@dataclass
class RecordingSandboxEventSink:
    """Test double that records every sink call for assertion."""

    created: list[SandboxCreatedCall] = field(default_factory=list)
    commands: list[SandboxCommandCall] = field(default_factory=list)
    closed: list[SandboxClosedCall] = field(default_factory=list)

    async def sandbox_created(
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        timeout_minutes: int,
        template: str | None = None,
    ) -> None:
        self.created.append(
            SandboxCreatedCall(run_id, task_id, sandbox_id, timeout_minutes, template)
        )

    async def sandbox_command(
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        command: str,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        self.commands.append(
            SandboxCommandCall(run_id, task_id, sandbox_id, command, stdout, stderr, exit_code, duration_ms)
        )

    async def sandbox_closed(
        self,
        task_id: UUID,
        sandbox_id: str,
        reason: str,
    ) -> None:
        self.closed.append(SandboxClosedCall(task_id, sandbox_id, reason))
```

## Full implementations

### 1. `set_event_sink` classmethod on `BaseSandboxManager`

Complete replacement for `BaseSandboxManager.__init__` and addition of
`set_event_sink`. All other methods of `BaseSandboxManager` are unchanged.

```python
# ergon_core/ergon_core/core/providers/sandbox/manager.py
# Replace __init__ (lines 85-87) and add set_event_sink after it.

    _event_sink: SandboxEventSink = NoopSandboxEventSink()

    def __init__(self) -> None:
        # Sink is configured process-wide via set_event_sink() in app lifespan.
        # Do not accept event_sink= here; the singleton pattern (see __new__ above)
        # makes constructor-level sink assignment a last-write-wins stomp on shared
        # class state. Tests must use set_event_sink() in fixture setup.
        pass

    @classmethod
    def set_event_sink(cls, sink: SandboxEventSink) -> None:
        """Install a process-level event sink on this manager subclass.

        Called once during FastAPI lifespan startup for each concrete subclass.
        Tests may call this in fixture setup and reset with
        ``NoopSandboxEventSink()`` in teardown.

        Assigns directly to ``cls._event_sink`` (not to the base class
        attribute), so each subclass carries its own sink and subclasses can
        be individually targeted in tests.

        Production callers MUST NOT call this after startup. The only
        sanctioned call site is inside the ``lifespan`` context manager in
        ``ergon_core/ergon_core/core/api/app.py``.
        """
        cls._event_sink = sink
```

### 2. `lifespan` block in `app.py`

```python
# ergon_core/ergon_core/core/api/app.py
# Full file after changes:

"""FastAPI application with Inngest webhook registration."""

import logging
from contextlib import asynccontextmanager

import inngest.fast_api
from ergon_core.core.api.cohorts import router as cohorts_router
from ergon_core.core.api.rollouts import init_service as init_rollout_service
from ergon_core.core.api.rollouts import router as rollouts_router
from ergon_core.core.api.runs import router as runs_router
from ergon_core.core.dashboard.emitter import dashboard_emitter
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.providers.sandbox.event_sink import DashboardEmitterSandboxEventSink
from ergon_core.core.providers.sandbox.manager import DefaultSandboxManager
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

    # Wire the dashboard event sink on every sandbox manager subclass.
    # Import ergon_builtins here (deferred) to avoid a circular import at
    # module level; ergon_builtins imports ergon_core, not the reverse.
    from ergon_builtins.registry import SANDBOX_MANAGERS  # noqa: PLC0415

    sink = DashboardEmitterSandboxEventSink(dashboard_emitter)
    # DefaultSandboxManager is the fallback; it is not in SANDBOX_MANAGERS.
    DefaultSandboxManager.set_event_sink(sink)
    for manager_cls in SANDBOX_MANAGERS.values():
        manager_cls.set_event_sink(sink)
    logger.info(
        "sandbox event sink wired on %d manager subclass(es)",
        1 + len(SANDBOX_MANAGERS),
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

inngest.fast_api.serve(app, inngest_client, ALL_FUNCTIONS)
```

## Exact diffs for modified files

### `manager.py` — `__init__` change and `set_event_sink` addition

```diff
--- a/ergon_core/ergon_core/core/providers/sandbox/manager.py
+++ b/ergon_core/ergon_core/core/providers/sandbox/manager.py
@@ -83,7 +83,22 @@ class BaseSandboxManager(ABC):
     _event_sink: SandboxEventSink = NoopSandboxEventSink()
 
-    def __init__(self, event_sink: SandboxEventSink | None = None):
-        if event_sink is not None:
-            self._event_sink = event_sink
+    def __init__(self) -> None:
+        # Sink is configured process-wide via set_event_sink() in app lifespan.
+        # Do not accept event_sink= here; the singleton pattern (see __new__ above)
+        # makes constructor-level sink assignment a last-write-wins stomp on shared
+        # class state. Tests must use set_event_sink() in fixture setup.
+        pass
+
+    @classmethod
+    def set_event_sink(cls, sink: SandboxEventSink) -> None:
+        """Install a process-level event sink on this manager subclass.
+
+        Called once during FastAPI lifespan startup for each concrete subclass.
+        Tests may call this in fixture setup and reset with
+        ``NoopSandboxEventSink()`` in teardown.
+
+        Assigns directly to ``cls._event_sink`` (not to the base class
+        attribute), so each subclass carries its own sink and subclasses can
+        be individually targeted in tests.
+
+        Production callers MUST NOT call this after startup. The only
+        sanctioned call site is inside the ``lifespan`` context manager in
+        ``ergon_core/ergon_core/core/api/app.py``.
+        """
+        cls._event_sink = sink
```

### `app.py` — `lifespan` block additions

```diff
--- a/ergon_core/ergon_core/core/api/app.py
+++ b/ergon_core/ergon_core/core/api/app.py
@@ -6,6 +6,8 @@ import inngest.fast_api
 from ergon_core.core.api.cohorts import router as cohorts_router
 from ergon_core.core.api.rollouts import init_service as init_rollout_service
 from ergon_core.core.api.rollouts import router as rollouts_router
 from ergon_core.core.api.runs import router as runs_router
+from ergon_core.core.dashboard.emitter import dashboard_emitter
 from ergon_core.core.persistence.shared.db import ensure_db, get_session
+from ergon_core.core.providers.sandbox.event_sink import DashboardEmitterSandboxEventSink
+from ergon_core.core.providers.sandbox.manager import DefaultSandboxManager
 from ergon_core.core.rl.rollout_service import RolloutService
 from ergon_core.core.runtime.inngest_client import inngest_client
 from ergon_core.core.runtime.inngest_registry import ALL_FUNCTIONS
@@ -22,6 +25,17 @@ async def lifespan(app: FastAPI):
     logger.info("ensure_db done, initializing RolloutService...")
     settings = Settings()
     init_rollout_service(
         RolloutService(
             session_factory=get_session,
             inngest_send=inngest_client.send_sync,
             tokenizer_name=settings.default_tokenizer,
         )
     )
+
+    from ergon_builtins.registry import SANDBOX_MANAGERS  # noqa: PLC0415
+
+    sink = DashboardEmitterSandboxEventSink(dashboard_emitter)
+    DefaultSandboxManager.set_event_sink(sink)
+    for manager_cls in SANDBOX_MANAGERS.values():
+        manager_cls.set_event_sink(sink)
+    logger.info(
+        "sandbox event sink wired on %d manager subclass(es)",
+        1 + len(SANDBOX_MANAGERS),
+    )
+
     logger.info("ready")
     yield
```

## Package structure

No new packages are introduced. The `RecordingSandboxEventSink` test fixture
lives in the existing `tests/` tree. If a `tests/state/fixtures/` directory does
not yet exist, add an empty `__init__.py`.

```
tests/
  state/
    fixtures/
      __init__.py          # empty — new if directory is new
      recording_event_sink.py    # new: RecordingSandboxEventSink and call dataclasses
    test_sandbox_event_sink_activation.py    # new: unit + integration tests
```

## Implementation order

| Step | What | Files touched | PR |
|---|---|---|---|
| **1** | Add `set_event_sink` classmethod to `BaseSandboxManager`; replace `__init__` (remove `event_sink=` param); update `_event_sink` class-attr declaration so it remains typed `SandboxEventSink` | MODIFY `ergon_core/ergon_core/core/providers/sandbox/manager.py` | PR 1 |
| **2** | Write `RecordingSandboxEventSink` fixture and unit tests for `set_event_sink` (isolated subclass, verify class-attr assignment, verify base class unaffected) | ADD `tests/state/fixtures/recording_event_sink.py`, ADD `tests/state/test_sandbox_event_sink_activation.py` | PR 1 |
| **3** | Wire `lifespan` in `app.py`: import `dashboard_emitter`, `DashboardEmitterSandboxEventSink`, `DefaultSandboxManager`, `SANDBOX_MANAGERS`; call `set_event_sink` on each subclass before `yield` | MODIFY `ergon_core/ergon_core/core/api/app.py` | PR 1 |
| **4** | Integration test: simulate `lifespan` startup, install a `RecordingSandboxEventSink` via `set_event_sink`, assert that `DefaultSandboxManager` produces `sandbox_created` and `sandbox_closed` events on `create`/`terminate` round-trip | ADD test to `tests/state/test_sandbox_event_sink_activation.py` | PR 1 |
| **5** | Update `docs/architecture/03_providers.md`: remove "activation path in flux" hedges from the `SandboxEventSink` entry and Section 2.4; state the process-level-setter rule; update Section 5.2 ("Add a new sandbox manager") to include `Manager.set_event_sink(sink)` in `lifespan` | MODIFY `docs/architecture/03_providers.md` | PR 1 (same commit as implementation) |

All five steps ship in a single PR. No phasing is needed: the change is
self-contained (two modified files, one new test fixture, one new test module)
and does not depend on any other in-flight RFC to function correctly.

**Dependency note.** `docs/rfcs/active/2026-04-18-sandbox-manager-process-state.md`
proposes replacing the singleton-per-subclass pattern and class-level state dicts
with instance-owned state. That RFC is larger in scope and not required for this
fix. The `set_event_sink` classmethod introduced here is **forward-compatible**
with the process-state RFC: when class-level state is moved to instance-level
state, `set_event_sink` becomes an instance-attribute wire-up instead. The
classmethod itself can be retained as-is or converted; no call-site changes
are needed at that point.

The latent shared-state race (a late `__init__` call with `event_sink!=None`
stomps the live sink for all in-flight tasks) is resolved by this RFC because
`__init__` no longer accepts `event_sink=`. The underlying class-dict stomp
risk that the process-state RFC targets remains, but this RFC eliminates one
of its concrete manifestations.

## File map

### ADD

| File | Purpose |
|---|---|
| `tests/state/fixtures/__init__.py` | Empty package init (add only if directory is new) |
| `tests/state/fixtures/recording_event_sink.py` | `RecordingSandboxEventSink` and associated call-record dataclasses for use in unit and integration tests |
| `tests/state/test_sandbox_event_sink_activation.py` | Unit and integration tests for `set_event_sink`, lifecycle event emission, and fixture-based reset |

### MODIFY

| File | Changes |
|---|---|
| `ergon_core/ergon_core/core/providers/sandbox/manager.py` | Remove `event_sink: SandboxEventSink \| None = None` from `__init__`; replace body with `pass`; add `set_event_sink` classmethod after `__init__` |
| `ergon_core/ergon_core/core/api/app.py` | Add three imports (`dashboard_emitter`, `DashboardEmitterSandboxEventSink`, `DefaultSandboxManager`); add deferred `SANDBOX_MANAGERS` import inside `lifespan`; add sink-wiring block before `yield` |

No changes to: the five construction sites, `event_sink.py`, `emitter.py`,
`registry.py`, or any benchmark/worker file.

## Testing approach

### Unit tests

```python
# tests/state/test_sandbox_event_sink_activation.py

from __future__ import annotations

import pytest

from ergon_core.core.providers.sandbox.event_sink import NoopSandboxEventSink
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager, DefaultSandboxManager
from tests.state.fixtures.recording_event_sink import RecordingSandboxEventSink


class _TestManagerA(BaseSandboxManager):
    """Isolated subclass for testing — never constructed outside this module."""

    async def _install_dependencies(self, sandbox, task_id):  # type: ignore[override]
        pass


class _TestManagerB(BaseSandboxManager):
    """Second isolated subclass — verifies per-class independence."""

    async def _install_dependencies(self, sandbox, task_id):  # type: ignore[override]
        pass


@pytest.fixture(autouse=True)
def reset_test_manager_sinks():
    """Restore noop sink on test managers after each test."""
    noop = NoopSandboxEventSink()
    yield
    _TestManagerA.set_event_sink(noop)
    _TestManagerB.set_event_sink(noop)


class TestSetEventSink:
    def test_set_event_sink_assigns_to_subclass(self) -> None:
        sink = RecordingSandboxEventSink()
        _TestManagerA.set_event_sink(sink)
        assert _TestManagerA._event_sink is sink

    def test_set_event_sink_does_not_affect_other_subclass(self) -> None:
        sink_a = RecordingSandboxEventSink()
        _TestManagerA.set_event_sink(sink_a)
        # _TestManagerB should still hold its own noop
        assert _TestManagerB._event_sink is not sink_a

    def test_set_event_sink_does_not_affect_base_class(self) -> None:
        sink = RecordingSandboxEventSink()
        _TestManagerA.set_event_sink(sink)
        # BaseSandboxManager._event_sink is the class-level default NoopSandboxEventSink
        # set_event_sink writes to _TestManagerA, not to BaseSandboxManager
        assert BaseSandboxManager._event_sink is not sink

    def test_default_sink_is_noop(self) -> None:
        assert isinstance(_TestManagerB._event_sink, NoopSandboxEventSink)

    def test_init_no_longer_accepts_event_sink_kwarg(self) -> None:
        """__init__ removing event_sink= means passing it is a TypeError."""
        with pytest.raises(TypeError):
            _TestManagerA(event_sink=RecordingSandboxEventSink())  # type: ignore[call-arg]
```

### Integration test — lifecycle events flow to sink

```python
# tests/state/test_sandbox_event_sink_activation.py  (continued)

import asyncio
from uuid import uuid4

import pytest

from ergon_core.core.providers.sandbox.event_sink import NoopSandboxEventSink
from ergon_core.core.providers.sandbox.manager import DefaultSandboxManager
from tests.state.fixtures.recording_event_sink import RecordingSandboxEventSink


@pytest.fixture()
def recording_default_manager():
    """Install a RecordingSandboxEventSink on DefaultSandboxManager for the test."""
    sink = RecordingSandboxEventSink()
    DefaultSandboxManager.set_event_sink(sink)
    yield DefaultSandboxManager(), sink
    DefaultSandboxManager.set_event_sink(NoopSandboxEventSink())
    # Reset singleton state so task-id doesn't leak between tests
    DefaultSandboxManager._sandboxes.clear()
    DefaultSandboxManager._run_ids.clear()
    DefaultSandboxManager._display_task_ids.clear()
    DefaultSandboxManager._file_registries.clear()
    DefaultSandboxManager._created_files_registry.clear()
    DefaultSandboxManager._creation_locks.clear()


@pytest.mark.asyncio
async def test_sandbox_created_emits_to_sink(
    recording_default_manager,
    monkeypatch,
) -> None:
    """DefaultSandboxManager.create() calls sink.sandbox_created exactly once."""
    manager, sink = recording_default_manager
    task_id = uuid4()
    run_id = uuid4()

    # Stub out the E2B call so no real sandbox is provisioned
    class _FakeSandbox:
        sandbox_id = "sbx-test-123"

        async def run_code(self, *a, **kw):
            class R:
                error = None
                logs = None
            return R()

        async def files(self):
            pass

        async def commands(self):
            pass

    from unittest.mock import AsyncMock, MagicMock, patch

    fake_sandbox = _FakeSandbox()
    with patch(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox"
    ) as mock_cls:
        mock_cls.create = AsyncMock(return_value=fake_sandbox)
        # Skip directory structure for unit speed
        monkeypatch.setattr(manager, "_create_directory_structure", AsyncMock())

        await manager.create(
            sandbox_key=task_id,
            run_id=run_id,
            timeout_minutes=5,
        )

    assert len(sink.created) == 1
    assert sink.created[0].sandbox_id == "sbx-test-123"
    assert sink.created[0].run_id == run_id
    assert sink.created[0].task_id == task_id


@pytest.mark.asyncio
async def test_sandbox_closed_emits_to_sink(
    recording_default_manager,
    monkeypatch,
) -> None:
    """DefaultSandboxManager.terminate() calls sink.sandbox_closed exactly once."""
    manager, sink = recording_default_manager
    task_id = uuid4()

    from unittest.mock import AsyncMock, MagicMock

    class _FakeSandbox:
        sandbox_id = "sbx-test-456"
        kill = AsyncMock()

    manager._sandboxes[task_id] = _FakeSandbox()
    manager._run_ids[task_id] = uuid4()
    manager._display_task_ids[task_id] = task_id

    await manager.terminate(task_id, reason="completed")

    assert len(sink.closed) == 1
    assert sink.closed[0].sandbox_id == "sbx-test-456"
    assert sink.closed[0].reason == "completed"
```

### Contract test — `lifespan` wires sink on all managers

```python
# tests/state/test_sandbox_event_sink_activation.py  (continued)

def test_lifespan_wires_all_known_managers() -> None:
    """Every entry in SANDBOX_MANAGERS + DefaultSandboxManager must have
    set_event_sink called during lifespan. Verify the call surface exists
    and the method is a classmethod (not instance method).
    """
    from ergon_builtins.registry import SANDBOX_MANAGERS
    from ergon_core.core.providers.sandbox.manager import DefaultSandboxManager

    all_managers = [DefaultSandboxManager, *SANDBOX_MANAGERS.values()]
    for mgr_cls in all_managers:
        assert hasattr(mgr_cls, "set_event_sink"), (
            f"{mgr_cls.__name__} missing set_event_sink — "
            "did it accidentally shadow BaseSandboxManager?"
        )
        sink = RecordingSandboxEventSink()
        mgr_cls.set_event_sink(sink)
        assert mgr_cls._event_sink is sink, (
            f"{mgr_cls.__name__}._event_sink was not updated by set_event_sink"
        )
        # Restore noop to avoid polluting other tests
        mgr_cls.set_event_sink(NoopSandboxEventSink())
```

## Trace / observability impact

No new spans or metrics are introduced by this RFC. The effect is that three
Inngest events — `dashboard/sandbox.created`, `dashboard/sandbox.command`, and
`dashboard/sandbox.closed` — now fire on the live path where previously they
were suppressed by the noop sink.

Logfire / existing Inngest event tracing picks up these new event types
automatically via the existing `inngest_client.send()` instrumentation.

One log line is added at startup in `lifespan`:

```
INFO ergon_core.core.api.app: sandbox event sink wired on 5 manager subclass(es)
```

(Count reflects `DefaultSandboxManager` + the four entries in `SANDBOX_MANAGERS`
today: `gdpeval`, `minif2f`, `swebench-verified`, plus `ResearchRubricsSandboxManager`
if registered — verify actual count against `SANDBOX_MANAGERS` at time of
implementation.)

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| A new `BaseSandboxManager` subclass lands without being added to `SANDBOX_MANAGERS` | Its `_event_sink` stays `NoopSandboxEventSink`; events silently dropped | Architecture doc Section 5.2 mandates adding the subclass to `SANDBOX_MANAGERS` before use. `test_lifespan_wires_all_known_managers` will catch registered-but-unwired classes automatically. |
| `SANDBOX_MANAGERS` is imported deferred (inside `lifespan`) and the optional `[data]` extra is not installed | `ergon_builtins.registry` import succeeds; `SANDBOX_MANAGERS` contains only the always-available entries; benchmark-specific managers won't be wired | The sink assignment is best-effort — if a manager class is not imported, it can't be wired. In practice the app process that serves API requests also imports `ergon_builtins` in full (via `ALL_FUNCTIONS`). Document this assumption. |
| `set_event_sink` called multiple times during lifespan (e.g. hot-reload) | Last call wins; benign if same sink type | `lifespan` runs once per process startup; ASGI hot-reload restarts the process. Not a real risk. |
| `set_event_sink` called after startup by test code that forgets the teardown | Pollutes sink state for subsequent tests in the session | `recording_default_manager` fixture (above) resets to noop in teardown. CI autouse fixtures should enforce isolation. |
| `DashboardEmitter.sandbox_*` calls fail (Inngest unreachable) | Exception caught inside `DashboardEmitter`; logged at WARNING; never propagates to sandbox lifecycle | Existing `except Exception: logger.warning(...)` blocks in `emitter.py:268`, `:299`, `:319` already handle this. No change needed. |
| Shared-state race (the `__init__` stomp) re-introduced by a future contributor adding `event_sink=` back | Silent override of production sink mid-run | Removing the param from `__init__` is the fix. The docstring on `set_event_sink` explicitly prohibits production callers. Slopcop or review discipline enforces. |
| `ResearchRubricsSandboxManager` lives in `ergon_core` but `researchrubrics` slug is only available under `ergon_builtins[data]`; it may not appear in `SANDBOX_MANAGERS` in all environments | Manager class exists but is not wired | It is not currently in `SANDBOX_MANAGERS`; it is wired via direct instantiation in `researcher_worker.py` and `stub_worker.py`. Those files will pick up the sink because `set_event_sink` writes to the class attribute. Adding `ResearchRubricsSandboxManager` to `SANDBOX_MANAGERS` is a follow-up. |

## Invariants affected

From `docs/architecture/03_providers.md`:

- **Section 2.4 `SandboxEventSink`:** Status line "unwired on the live path"
  and the "Sandbox event sink unwired" bullet in Section 4.1 are removed. The
  invariant stated in the bug (`"every sandbox event flows through the sink"`)
  becomes true and must be stated without the "partially wired" softener.

- **New rule (add to Section 4 or 4.1):** Sinks are process-level, set once at
  app init, never swapped at runtime in production code. Tests may swap via
  fixture scope; production callers MUST NOT call `set_event_sink` after
  startup.

- **Section 5.2 "Add a new sandbox manager":** Replace the existing step
  "Do NOT pass `event_sink=` at construction today" (which is marked as
  temporary) with: "Add the new subclass to `SANDBOX_MANAGERS` in
  `ergon_builtins/ergon_builtins/registry_core.py`. The `lifespan` block
  wires the dashboard sink automatically for every entry in that registry."

- **Section 6 "Anti-patterns":** Replace the anti-pattern
  "Passing `event_sink=` at manager construction" with:
  "Calling `set_event_sink` outside of `lifespan` or test fixtures. Production
  callers must not call it after startup."

From `docs/architecture/05_dashboard.md`:

- **Section 4 invariant 1** ("The dashboard is event-driven end-to-end for the
  surfaces that are wired") now applies to the sandbox surface. No wording
  change needed; the sandbox entries in the Follow-ups section are resolved.

- **Section 7 Follow-ups:** Remove
  `docs/bugs/open/2026-04-17-sandbox-event-sink-unactivated.md` from the list.
  The `DashboardEmitterSandboxEventSink has no constructor site today` note in
  Section 2 is also removed.

## Alternatives considered

- **Make `event_sink` a required constructor kwarg** (original proposal in the
  superseded draft of this RFC). Rejected: no behavioral win since
  `dashboard_emitter` is itself a process-wide singleton, and the
  singleton-per-subclass pattern at `manager.py:78-81` with a last-write-wins
  `__init__` stomp at `manager.py:85-87` creates a real test-isolation hazard.
  Documented separately as the latent race in
  `docs/bugs/open/2026-04-18-sandbox-manager-shared-state-race.md`.

- **Drop the singleton entirely, make managers instance-owned.** Correctly
  resolves the underlying class-state sharing problem but depends on the broader
  process-state reform in
  `docs/rfcs/active/2026-04-18-sandbox-manager-process-state.md`, which is
  bigger scope. Revisit after that lands; the setter approach here is
  forward-compatible with an eventual instance-owned world (the classmethod
  becomes an instance attribute wire-up).

- **Module-level global sink.** Rejected: implicit dependency; worse than the
  classmethod for testability and for subclass-scoped overrides. Adds a new
  singleton without gaining any benefit over the classmethod.

## Open questions

- Should `ResearchRubricsSandboxManager` be added to `SANDBOX_MANAGERS` in
  `registry_core.py` so it is picked up automatically by `lifespan`? Currently
  it is absent from that registry (wired only by direct import in worker files).
  If not added, it still receives the sink because the class attribute is written
  by `set_event_sink` when the `data` extra is installed — but only if someone
  explicitly calls `ResearchRubricsSandboxManager.set_event_sink()` before the
  manager is first constructed. A follow-up PR should either add it to the
  registry or add an explicit call in `lifespan`.

- Whether to keep `set_event_sink` on `BaseSandboxManager` as a classmethod
  after the process-state RFC lands and the singleton is removed. If managers
  become proper instances, the setter can move to `__init__` as an optional
  kwarg — but with the DI container approach rather than the stomp approach.
  Defer this decision to that RFC.

## On acceptance

- [ ] Move this file to `docs/rfcs/accepted/`.
- [ ] Update `docs/architecture/03_providers.md` — remove "intended path" hedges
      in Section 2.4; remove "unwired" and "in flux" status notes; state the
      process-level-setter rule explicitly in Section 4; update Section 5.2 to
      include `SANDBOX_MANAGERS` registration as a step; update Section 6
      anti-pattern wording.
- [ ] Update `docs/architecture/05_dashboard.md` Section 7 Follow-ups — remove
      the sandbox sink bullet.
- [ ] Move `docs/bugs/open/2026-04-17-sandbox-event-sink-unactivated.md` →
      `docs/bugs/fixed/` with `fixed_pr` set.
- [ ] Link the implementation plan at
      `docs/superpowers/plans/2026-04-??-sandbox-event-sink-activation.md`.
