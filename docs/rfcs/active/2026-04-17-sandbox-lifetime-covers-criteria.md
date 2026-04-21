---
status: active
opened: 2026-04-17
author: deepflow-research
architecture_refs: [docs/architecture/03_providers.md#invariants, docs/architecture/cross_cutting/sandbox_lifecycle.md]
supersedes: []
superseded_by: null
---

# RFC: Sandbox timeout must cover task + criteria; expose `BaseSandboxManager.reconnect`

## Problem

### Current state

`BaseSandboxManager.create()` at
`ergon_core/ergon_core/core/providers/sandbox/manager.py:226` accepts a single
`timeout_minutes: int = 30` parameter. Every call site passes a literal or
relies on the default:

- `ergon_core/ergon_core/core/runtime/inngest/sandbox_setup.py:103` —
  `timeout_minutes=30` (literal)
- `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py:56` —
  `timeout_minutes=30` (literal)
- `tests/swebench_verified/test_sandbox_manager.py:129` — `timeout_minutes=5`
- `tests/minif2f/test_sandbox_manager.py:121` — `timeout_minutes=5`

After the task finishes, `check_and_run_evaluators`
(`ergon_core/ergon_core/core/runtime/inngest/check_evaluators.py:42`) fans out
criteria sequentially. Each criterion runs inside the **same** sandbox via
in-process reconnect through `BaseSandboxManager.get_sandbox(task_id)` at
`manager.py:394`, which reads the singleton's class-level `_sandboxes` dict.
The sandbox's timeout counter started at `Manager.create()` and has been
ticking ever since. If the task runtime + at least one agentic criterion's
wall-clock > `timeout_minutes`, E2B kills the sandbox mid-criterion. The next
`sandbox.commands.run(...)` raises. The criterion marks the task
`evaluation-failed`; the trajectory is silently dropped from RL training (see
`docs/architecture/08_rl_loop.md`).

This is a data-loss bug class: the worker produced correct output; the system
failed to evaluate it.

### Missing `reconnect`

There is no `BaseSandboxManager.reconnect(sandbox_id: str)` method today. This
is documented as a known limit at `docs/architecture/03_providers.md:143`:

> **No `reconnect()` method.** Cross-process criteria must spawn their own
> sandbox (see `ergon_builtins/benchmarks/swebench_verified/criterion.py:66`).

The SWE-bench criterion works around this at
`ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py:66-78`
by calling `_spawn_eval_sandbox(run_id)` which constructs a fresh
`SWEBenchSandboxManager()` (line 72) and calls `manager.create(...)` (line 74)
for a brand-new sandbox on every criterion invocation. Consequences:

1. Every SWE-bench eval pays the full sandbox cold-start cost (clone + install).
2. The criterion grades the agent patch against a **clean** environment, not
   the worker's actual on-disk state — breaking the "criterion sees what the
   worker produced" invariant.
3. The pattern is contagious: it is being used as a template by future
   criterion authors (tracked as P2 bug
   `docs/bugs/open/2026-04-18-swebench-criterion-spawns-sandbox.md`).
4. `docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md` will enforce
   the "criteria go through `CriterionRuntime`" invariant; without a
   `reconnect` method on the manager, `CriterionRuntime.ensure_sandbox()` at
   `criterion_runtime.py:53` cannot correctly reconnect cross-process criteria
   — it calls `manager.create(...)` unconditionally when `get_sandbox()` returns
   `None`, provisioning a fresh sandbox instead.

The `cross_cutting/sandbox_lifecycle.md` invariant 3 states:

> Criteria MUST reconnect via the manager, never by constructing `AsyncSandbox`
> directly. ... The reconnect path through the manager is the only correct way
> to attach to a live sandbox.

That invariant cannot be enforced while `reconnect` is absent.

---

## Proposal

### Option chosen: split `timeout_minutes` into two typed parameters; add `reconnect`

Three coordinated changes, shipped as two PRs (see Implementation order):

**Change 1 — Split `create()` timeout.**
Change `BaseSandboxManager.create()`'s signature from:

```python
async def create(
    self,
    sandbox_key: UUID,
    run_id: UUID,
    timeout_minutes: int = 30,
    envs: dict[str, str] | None = None,
    display_task_id: UUID | None = None,
) -> str:
```

to:

```python
async def create(
    self,
    sandbox_key: UUID,
    run_id: UUID,
    task_timeout_minutes: int = 30,
    max_criterion_timeout_minutes: int = 10,
    envs: dict[str, str] | None = None,
    display_task_id: UUID | None = None,
) -> str:
```

The E2B sandbox is provisioned with
`timeout = task_timeout_minutes + max_criterion_timeout_minutes` minutes.
Callers that previously passed `timeout_minutes=N` must be migrated to
`task_timeout_minutes=N` (default `max_criterion_timeout_minutes=10` adds
headroom automatically). No caller today passes a custom `timeout_minutes` to
`create()` other than tests; the migration is mechanical.

`DefaultSandboxManager.create()` at `manager.py:503` overrides the base method;
it must be updated to the same signature, forwarding both new params to
`super().create(...)`.

**Change 2 — Add `BaseSandboxManager.reconnect(sandbox_id)`.**
Add a concrete method:

```python
async def reconnect(self, sandbox_id: str) -> "AsyncSandbox":
    """Attach to a running sandbox by its E2B sandbox_id.

    Returns the AsyncSandbox handle. Raises SandboxExpiredError if the
    sandbox is not found or has already timed out. Idempotent: calling
    reconnect twice for the same sandbox_id is safe — both calls return
    equivalent handles.
    """
```

Implementation calls `AsyncSandbox.connect(sandbox_id=sandbox_id,
api_key=settings.e2b_api_key)`. On E2B "not found" / "expired" error, raises
`SandboxExpiredError` (Change 3). This is the single blessed cross-process
reconnect path; `CriterionRuntime.ensure_sandbox()` will call it once RFC
`2026-04-17-criterion-runtime-di-container` lands.

**Change 3 — Define `SandboxExpiredError`.**
New exception class at
`ergon_core/ergon_core/core/providers/sandbox/errors.py`. Subclasses the base
`Exception` (not `ErgonNonRetriableError` — sandbox expiry is not a
definition-level error; it is a transient infrastructure condition). Criteria
that catch it should surface a `"sandbox-expired"` evaluation outcome rather
than a generic failure.

**Change 4 — Update `sandbox_setup_fn` call site.**
`ergon_core/ergon_core/core/runtime/inngest/sandbox_setup.py:103`:
- Change `timeout_minutes=30` to `task_timeout_minutes=30` (no semantic change
  for now; the new default `max_criterion_timeout_minutes=10` adds 10 min
  automatically).

**Change 5 — Update `DefaultCriterionRuntime.ensure_sandbox` call site.**
`ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py:56`:
- Same mechanical rename.

---

## Architecture overview

### Before (timeout bug path)

```
sandbox_setup_fn
  └─ BaseSandboxManager.create(task_id, timeout_minutes=30)
       └─ E2B provisions sandbox with timeout=30m

Worker.execute() runs ... wall-clock 25m elapsed ...

task/completed fires
  └─ check_and_run_evaluators
       └─ evaluate_task_run
            └─ SWEBenchTestCriterion.evaluate()
                 └─ _spawn_eval_sandbox()        ← FRESH sandbox (WRONG)
                      └─ SWEBenchSandboxManager.create(...)
                 └─ sandbox.commands.run(...)    ← may hit timeout at 30m
                      └─ E2B kills sandbox       ← SILENT DATA LOSS
```

### After (this RFC)

```
sandbox_setup_fn
  └─ BaseSandboxManager.create(task_id,
         task_timeout_minutes=30,
         max_criterion_timeout_minutes=10)
       └─ E2B provisions sandbox with timeout=40m

Worker.execute() runs ... wall-clock 25m elapsed ...

task/completed fires
  └─ check_and_run_evaluators
       └─ evaluate_task_run
            └─ CriterionRuntime.ensure_sandbox()   ← via RFC criterion-runtime-di-container
                 └─ BaseSandboxManager.reconnect(sandbox_id)
                      └─ AsyncSandbox.connect(sandbox_id)
                      └─ raises SandboxExpiredError → criterion returns "sandbox-expired" score
                 └─ sandbox.commands.run(...)        ← 10m of headroom remaining
       └─ _terminate_sandbox(sandbox_id)            ← unchanged teardown path
```

### Data flow: `timeout_minutes` parameter through the stack

```
SandboxSetupRequest (payload)
  └─ sandbox_setup_fn (_create_sandbox)
       └─ BaseSandboxManager.create(
              task_timeout_minutes=30,     ← from payload / default
              max_criterion_timeout_minutes=10)  ← default; overridable per-subclass
              │
              ├─ timeout_seconds = (task_timeout_minutes + max_criterion_timeout_minutes) * 60
              └─ AsyncSandbox.create(timeout=timeout_seconds)
                   └─ E2B sandbox: will live for 40 minutes from create
```

---

## Type / interface definitions

```python
# ergon_core/ergon_core/core/providers/sandbox/errors.py

"""Sandbox-specific exception types."""


class SandboxError(Exception):
    """Base for sandbox infrastructure errors."""


class SandboxExpiredError(SandboxError):
    """Raised when a sandbox is not reachable because it has timed out or
    been terminated.

    Callers (criteria, CriterionRuntime) should catch this and surface a
    ``"sandbox-expired"`` evaluation outcome rather than a generic error.
    The underlying task output is not lost — the sandbox's state was already
    published to the blob store by the worker's resource publisher before the
    sandbox timed out.
    """

    def __init__(self, sandbox_id: str, detail: str = "") -> None:
        self.sandbox_id = sandbox_id
        msg = f"Sandbox {sandbox_id!r} is expired or not found"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)
```

---

## Full implementations

### `errors.py` (new file)

```python
# ergon_core/ergon_core/core/providers/sandbox/errors.py

"""Sandbox-specific exception types."""


class SandboxError(Exception):
    """Base for sandbox infrastructure errors."""


class SandboxExpiredError(SandboxError):
    """Raised when a sandbox is not reachable because it has timed out or
    been terminated.

    Callers (criteria, CriterionRuntime) should catch this and surface a
    ``"sandbox-expired"`` evaluation outcome rather than a generic error.
    The underlying task output is not lost — the sandbox's state was already
    published to the blob store by the worker's resource publisher before the
    sandbox timed out.
    """

    def __init__(self, sandbox_id: str, detail: str = "") -> None:
        self.sandbox_id = sandbox_id
        msg = f"Sandbox {sandbox_id!r} is expired or not found"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)
```

### `reconnect` method (added to `BaseSandboxManager`)

```python
# Added to: ergon_core/ergon_core/core/providers/sandbox/manager.py
# Location: after get_sandbox() at line 394, before get_sandbox_path()

async def reconnect(self, sandbox_id: str) -> "AsyncSandbox":
    """Attach to a running sandbox by its E2B sandbox_id.

    Returns an AsyncSandbox handle connected to the running sandbox.
    Raises SandboxExpiredError if the sandbox is not found or has already
    timed out.  Idempotent: calling reconnect twice for the same sandbox_id
    is safe — both calls invoke AsyncSandbox.connect() which returns an
    equivalent handle.

    Use this for cross-process criterion reconnect.  In-process criteria
    should prefer get_sandbox(task_id) (reads shared class state).
    This method does NOT register the sandbox in class-level state;
    callers should not assume it shows up in _sandboxes.
    """
    from ergon_core.core.providers.sandbox.errors import SandboxExpiredError

    if AsyncSandbox is None:
        raise RuntimeError(
            "e2b_code_interpreter is not installed. "
            "Install it with: pip install e2b-code-interpreter"
        )
    try:
        sandbox = await AsyncSandbox.connect(
            sandbox_id=sandbox_id,
            api_key=settings.e2b_api_key,
        )
    except Exception as exc:  # slopcop: ignore[no-broad-except]
        err = str(exc).lower()
        if "not found" in err or "404" in err or "expired" in err or "timeout" in err:
            raise SandboxExpiredError(sandbox_id, detail=str(exc)) from exc
        raise
    return sandbox
```

### Updated `create()` signature — `BaseSandboxManager`

```python
# ergon_core/ergon_core/core/providers/sandbox/manager.py
# Replace lines 226-295 (existing create method)

async def create(
    self,
    sandbox_key: UUID,
    run_id: UUID,
    task_timeout_minutes: int = 30,
    max_criterion_timeout_minutes: int = 10,
    envs: dict[str, str] | None = None,
    display_task_id: UUID | None = None,
) -> str:
    """Create a new E2B sandbox, set up directories, install deps.

    The sandbox is provisioned with a timeout of
    ``task_timeout_minutes + max_criterion_timeout_minutes`` to ensure
    criteria running after the task has finished still have a live sandbox
    to reconnect to.  See RFC 2026-04-17-sandbox-lifetime-covers-criteria.
    """
    if AsyncSandbox is None:
        raise RuntimeError(
            "e2b_code_interpreter is not installed. "
            "Install it with: pip install e2b-code-interpreter"
        )

    display_task_id = display_task_id or sandbox_key
    lock = self._creation_locks.setdefault(sandbox_key, asyncio.Lock())
    async with lock:
        if sandbox_key in self._sandboxes:
            return self._sandboxes[sandbox_key].sandbox_id

        if not settings.e2b_api_key:
            raise ValueError(
                "E2B_API_KEY is not set. "
                "Please set E2B_API_KEY in your .env file or environment variables."
            )

        try:
            # Provision for task + criterion headroom.
            total_timeout_minutes = task_timeout_minutes + max_criterion_timeout_minutes
            timeout_seconds = total_timeout_minutes * 60
            create_kwargs: dict[str, str | int] = {
                "api_key": settings.e2b_api_key,
                "timeout": timeout_seconds,
            }
            if envs:
                create_kwargs["envs"] = envs
            if self.template:
                create_kwargs["template"] = self.template
            sandbox = await AsyncSandbox.create(**create_kwargs)
        except Exception as e:  # slopcop: ignore[no-broad-except]
            raise RuntimeError(
                f"Failed to create sandbox for sandbox_key={sandbox_key}: {e}"
            ) from e

        if not sandbox:
            raise RuntimeError("Sandbox object is None after creation")

        self._sandboxes[sandbox_key] = sandbox
        self._ensure_registries(sandbox_key)
        self._run_ids[sandbox_key] = run_id
        self._display_task_ids[sandbox_key] = display_task_id

        await self._event_sink.sandbox_created(
            run_id=run_id,
            task_id=display_task_id,
            sandbox_id=sandbox.sandbox_id,
            timeout_minutes=total_timeout_minutes,
        )
        await self._emit_wal_entry(
            sandbox_key,
            command="sandbox.created",
            stdout=(
                f"sandbox_id={sandbox.sandbox_id}\n"
                f"task_timeout={task_timeout_minutes}m\n"
                f"max_criterion_timeout={max_criterion_timeout_minutes}m\n"
                f"total_timeout={total_timeout_minutes}m"
            ),
            exit_code=0,
            duration_ms=0,
        )

        await self._create_directory_structure(sandbox, sandbox_key)
        await self._install_dependencies(sandbox, display_task_id)
        await self._verify_setup(sandbox, display_task_id)

        return sandbox.sandbox_id
```

### Updated `DefaultSandboxManager.create()` override

```python
# ergon_core/ergon_core/core/providers/sandbox/manager.py
# Replace lines 503-526 (existing DefaultSandboxManager.create override)

async def create(
    self,
    sandbox_key: UUID,
    run_id: UUID,
    task_timeout_minutes: int = 30,
    max_criterion_timeout_minutes: int = 10,
    envs: dict[str, str] | None = None,
    display_task_id: UUID | None = None,
) -> str:
    if not settings.e2b_api_key:
        # Deferred: avoid a circular import between providers and runtime events.
        from ergon_core.core.runtime.events.task_events import SANDBOX_SKIPPED

        logger.info(
            "E2B_API_KEY not set — skipping sandbox creation for task %s (stub mode)",
            sandbox_key,
        )
        return SANDBOX_SKIPPED
    return await super().create(
        sandbox_key,
        run_id=run_id,
        task_timeout_minutes=task_timeout_minutes,
        max_criterion_timeout_minutes=max_criterion_timeout_minutes,
        envs=envs,
        display_task_id=display_task_id,
    )
```

### Updated `__init__.py` (sandbox package)

```python
# ergon_core/ergon_core/core/providers/sandbox/__init__.py
# Add SandboxExpiredError, SandboxError to exports

"""Sandbox management: provisioning, file I/O, lifecycle."""

from ergon_core.core.providers.sandbox.errors import (
    SandboxError,
    SandboxExpiredError,
)
from ergon_core.core.providers.sandbox.event_sink import (
    DashboardEmitterSandboxEventSink,
    NoopSandboxEventSink,
    SandboxEventSink,
)
from ergon_core.core.providers.sandbox.manager import (
    BaseSandboxManager,
    DefaultSandboxManager,
    DownloadedFile,
    DownloadedFiles,
)

__all__ = [
    "BaseSandboxManager",
    "DashboardEmitterSandboxEventSink",
    "DefaultSandboxManager",
    "DownloadedFile",
    "DownloadedFiles",
    "NoopSandboxEventSink",
    "SandboxError",
    "SandboxEventSink",
    "SandboxExpiredError",
]
```

---

## Exact diffs for modified files

### `ergon_core/ergon_core/core/providers/sandbox/manager.py`

```diff
@@ -226,13 +226,16 @@ class BaseSandboxManager(ABC):
     async def create(
         self,
         sandbox_key: UUID,
         run_id: UUID,
-        timeout_minutes: int = 30,
+        task_timeout_minutes: int = 30,
+        max_criterion_timeout_minutes: int = 10,
         envs: dict[str, str] | None = None,
         display_task_id: UUID | None = None,
     ) -> str:
-        """Create a new E2B sandbox, set up directories, install deps."""
+        """Create a new E2B sandbox, set up directories, install deps.
+
+        The sandbox is provisioned with a timeout of
+        ``task_timeout_minutes + max_criterion_timeout_minutes`` to ensure
+        criteria running after the task has finished still have a live sandbox
+        to reconnect to.  See RFC 2026-04-17-sandbox-lifetime-covers-criteria.
+        """
         if AsyncSandbox is None:
             raise RuntimeError(...)
 
@@ -250,7 +253,8 @@ class BaseSandboxManager(ABC):
             try:
-                timeout_seconds = timeout_minutes * 60
+                total_timeout_minutes = task_timeout_minutes + max_criterion_timeout_minutes
+                timeout_seconds = total_timeout_minutes * 60
                 create_kwargs: dict[str, str | int] = {
                     "api_key": settings.e2b_api_key,
                     "timeout": timeout_seconds,
                 }
 
@@ -278,8 +283,12 @@ class BaseSandboxManager(ABC):
             await self._event_sink.sandbox_created(
                 run_id=run_id,
                 task_id=display_task_id,
                 sandbox_id=sandbox.sandbox_id,
-                timeout_minutes=timeout_minutes,
+                timeout_minutes=total_timeout_minutes,
             )
             await self._emit_wal_entry(
                 sandbox_key,
                 command="sandbox.created",
-                stdout=f"sandbox_id={sandbox.sandbox_id}\ntimeout={timeout_minutes}m",
+                stdout=(
+                    f"sandbox_id={sandbox.sandbox_id}\n"
+                    f"task_timeout={task_timeout_minutes}m\n"
+                    f"max_criterion_timeout={max_criterion_timeout_minutes}m\n"
+                    f"total_timeout={total_timeout_minutes}m"
+                ),
                 exit_code=0,
                 duration_ms=0,
             )

+    async def reconnect(self, sandbox_id: str) -> "AsyncSandbox":
+        """Attach to a running sandbox by its E2B sandbox_id.
+
+        Returns an AsyncSandbox handle. Raises SandboxExpiredError if the
+        sandbox is not found or has already timed out. Idempotent.
+        Does NOT register in class-level _sandboxes state.
+        """
+        from ergon_core.core.providers.sandbox.errors import SandboxExpiredError
+
+        if AsyncSandbox is None:
+            raise RuntimeError(
+                "e2b_code_interpreter is not installed. "
+                "Install it with: pip install e2b-code-interpreter"
+            )
+        try:
+            sandbox = await AsyncSandbox.connect(
+                sandbox_id=sandbox_id,
+                api_key=settings.e2b_api_key,
+            )
+        except Exception as exc:  # slopcop: ignore[no-broad-except]
+            err = str(exc).lower()
+            if "not found" in err or "404" in err or "expired" in err or "timeout" in err:
+                raise SandboxExpiredError(sandbox_id, detail=str(exc)) from exc
+            raise
+        return sandbox

 @@ -503,10 +543,12 @@ class DefaultSandboxManager(BaseSandboxManager):
     async def create(
         self,
         sandbox_key: UUID,
         run_id: UUID,
-        timeout_minutes: int = 30,
+        task_timeout_minutes: int = 30,
+        max_criterion_timeout_minutes: int = 10,
         envs: dict[str, str] | None = None,
         display_task_id: UUID | None = None,
     ) -> str:
         if not settings.e2b_api_key:
             ...
             return SANDBOX_SKIPPED
         return await super().create(
             sandbox_key,
             run_id=run_id,
-            timeout_minutes=timeout_minutes,
+            task_timeout_minutes=task_timeout_minutes,
+            max_criterion_timeout_minutes=max_criterion_timeout_minutes,
             envs=envs,
             display_task_id=display_task_id,
         )
```

### `ergon_core/ergon_core/core/runtime/inngest/sandbox_setup.py`

```diff
@@ -103,7 +103,8 @@ async def _create_sandbox(...) -> SandboxReadyResult:
     sandbox_id = await sandbox_manager.create(
         task_id,
         run_id=run_id,
-        timeout_minutes=30,
+        task_timeout_minutes=30,
+        # max_criterion_timeout_minutes uses default (10)
         envs=envs,
         display_task_id=task_id,
     )
```

### `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py`

```diff
@@ -53,8 +53,9 @@ class DefaultCriterionRuntime:
     async def ensure_sandbox(self) -> None:
         sandbox = self.sandbox_manager.get_sandbox(self.context.run_id)
         if sandbox is None:
             await self.sandbox_manager.create(
                 self.context.run_id,
                 run_id=self.context.run_id,
-                timeout_minutes=30,
+                task_timeout_minutes=30,
+                # max_criterion_timeout_minutes uses default (10)
             )
             self._owns_sandbox = True
             return
-        await self.sandbox_manager.reset_timeout(self.context.run_id, timeout_minutes=30)
+        await self.sandbox_manager.reset_timeout(self.context.run_id, timeout_minutes=40)
```

Note: `reset_timeout` call changes from 30 to 40 to match the new provisioned total. The signature of `reset_timeout` at `manager.py:407` is unchanged (still accepts `timeout_minutes`).

### `ergon_core/ergon_core/core/providers/sandbox/__init__.py`

```diff
@@ -1,6 +1,11 @@
 """Sandbox management: provisioning, file I/O, lifecycle."""
 
+from ergon_core.core.providers.sandbox.errors import (
+    SandboxError,
+    SandboxExpiredError,
+)
 from ergon_core.core.providers.sandbox.event_sink import (
     DashboardEmitterSandboxEventSink,
     NoopSandboxEventSink,
     SandboxEventSink,
 )
 from ergon_core.core.providers.sandbox.manager import (
     BaseSandboxManager,
     DefaultSandboxManager,
     DownloadedFile,
     DownloadedFiles,
 )
 
 __all__ = [
     "BaseSandboxManager",
     "DashboardEmitterSandboxEventSink",
     "DefaultSandboxManager",
     "DownloadedFile",
     "DownloadedFiles",
     "NoopSandboxEventSink",
+    "SandboxError",
     "SandboxEventSink",
+    "SandboxExpiredError",
 ]
```

---

## Package structure

New file, no new package. The errors module sits alongside the existing sandbox
package files:

```
ergon_core/ergon_core/core/providers/sandbox/
├── __init__.py          MODIFY  (add SandboxError, SandboxExpiredError exports)
├── errors.py            ADD     (SandboxError, SandboxExpiredError)
├── event_sink.py        no change
├── instrumentation.py   no change
├── manager.py           MODIFY  (create signature, reconnect method)
├── research_rubrics_manager.py  no change
├── resource_publisher.py        no change
└── utils.py             no change
```

---

## Implementation order

| Step | Phase | What | Files touched |
|------|-------|------|---------------|
| 1 | PR 1 | Create `errors.py` with `SandboxError` and `SandboxExpiredError` | ADD `ergon_core/ergon_core/core/providers/sandbox/errors.py` |
| 2 | PR 1 | Add `errors` imports to sandbox `__init__.py` | MODIFY `ergon_core/ergon_core/core/providers/sandbox/__init__.py` |
| 3 | PR 1 | Update `BaseSandboxManager.create()` signature: `timeout_minutes` → `task_timeout_minutes + max_criterion_timeout_minutes`; update WAL entry log | MODIFY `ergon_core/ergon_core/core/providers/sandbox/manager.py` |
| 4 | PR 1 | Update `DefaultSandboxManager.create()` override with same signature change | MODIFY `ergon_core/ergon_core/core/providers/sandbox/manager.py` |
| 5 | PR 1 | Migrate `sandbox_setup.py` call site: `timeout_minutes=30` → `task_timeout_minutes=30` | MODIFY `ergon_core/ergon_core/core/runtime/inngest/sandbox_setup.py` |
| 6 | PR 1 | Migrate `criterion_runtime.py` call sites: same rename; `reset_timeout` 30 → 40 | MODIFY `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py` |
| 7 | PR 1 | Migrate test call sites: `timeout_minutes=5` → `task_timeout_minutes=5` in `tests/swebench_verified/test_sandbox_manager.py` and `tests/minif2f/test_sandbox_manager.py` | MODIFY 2 test files |
| 8 | PR 1 | Unit tests: `create()` passes correct total timeout to E2B; `task_timeout + max_criterion_timeout` arithmetic | ADD `tests/unit/test_sandbox_timeout.py` |
| 9 | PR 2 | Add `BaseSandboxManager.reconnect(sandbox_id)` method | MODIFY `ergon_core/ergon_core/core/providers/sandbox/manager.py` |
| 10 | PR 2 | Unit tests for `reconnect`: successful connect, E2B-not-found raises `SandboxExpiredError`, non-expired E2B error re-raises | ADD to `tests/unit/test_sandbox_reconnect.py` |
| 11 | PR 2 | Canary e2e test: deliberately-slow criterion (sleep > task_timeout) still finds sandbox reachable | ADD `tests/e2e/test_sandbox_criterion_timeout_canary.py` |
| 12 | PR 2 | (Deferred — depends on `2026-04-17-criterion-runtime-di-container`) Migrate `DefaultCriterionRuntime.ensure_sandbox()` to use `reconnect` when `get_sandbox` returns `None`, handling `SandboxExpiredError` | MODIFY `criterion_runtime.py` |

Steps 1–8 land as PR 1 ("sandbox-lifetime/split-timeout"). Steps 9–11 land as PR 2
("sandbox-lifetime/reconnect"). Step 12 is gated on the DI container RFC.

---

## File map

### ADD

| File | Purpose |
|------|---------|
| `ergon_core/ergon_core/core/providers/sandbox/errors.py` | `SandboxError` base class; `SandboxExpiredError` raised by `reconnect()` on expired sandbox |
| `tests/unit/test_sandbox_timeout.py` | Unit tests: `create()` arithmetic, `task_timeout + max_criterion_timeout` passed to E2B |
| `tests/unit/test_sandbox_reconnect.py` | Unit tests: `reconnect()` success, not-found raises `SandboxExpiredError`, other errors re-raise |
| `tests/e2e/test_sandbox_criterion_timeout_canary.py` | E2e canary: slow criterion still reaches sandbox when timeout is correctly provisioned |

### MODIFY

| File | Changes |
|------|---------|
| `ergon_core/ergon_core/core/providers/sandbox/manager.py` | Split `timeout_minutes` into `task_timeout_minutes + max_criterion_timeout_minutes` in `BaseSandboxManager.create()` and `DefaultSandboxManager.create()`; add `reconnect()` method |
| `ergon_core/ergon_core/core/providers/sandbox/__init__.py` | Export `SandboxError`, `SandboxExpiredError` |
| `ergon_core/ergon_core/core/runtime/inngest/sandbox_setup.py` | Rename `timeout_minutes=30` → `task_timeout_minutes=30` at line 106 |
| `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py` | Rename `timeout_minutes=30` → `task_timeout_minutes=30` at line 59; `reset_timeout(..., timeout_minutes=30)` → `timeout_minutes=40` at line 63 |
| `tests/swebench_verified/test_sandbox_manager.py` | Rename `timeout_minutes=5` → `task_timeout_minutes=5`; update assertion `call_kwargs["timeout"] == 5 * 60` → `== (5 + 10) * 60` |
| `tests/minif2f/test_sandbox_manager.py` | Same rename and timeout assertion update |

---

## Testing approach

### Unit tests — `tests/unit/test_sandbox_timeout.py`

```python
# tests/unit/test_sandbox_timeout.py

"""Unit tests: BaseSandboxManager.create() provisions task + criterion timeout."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ergon_core.core.providers.sandbox.manager import BaseSandboxManager, DefaultSandboxManager


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}
    BaseSandboxManager._creation_locks = {}
    BaseSandboxManager._run_ids = {}
    BaseSandboxManager._display_task_ids = {}
    BaseSandboxManager._file_registries = {}
    BaseSandboxManager._created_files_registry = {}
    yield
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}


class _MinimalManager(BaseSandboxManager):
    """Concrete manager with no-op hooks for unit testing."""

    async def _install_dependencies(self, sandbox, task_id):  # type: ignore[override]
        pass

    async def _create_directory_structure(self, sandbox, sandbox_key):  # type: ignore[override]
        pass


@pytest.mark.asyncio
async def test_create_passes_total_timeout_to_e2b(monkeypatch: pytest.MonkeyPatch) -> None:
    """E2B AsyncSandbox.create receives task + criterion timeout in seconds."""
    fake_sandbox = MagicMock()
    fake_sandbox.sandbox_id = "sbx-test"
    fake_create = AsyncMock(return_value=fake_sandbox)
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(create=fake_create),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = _MinimalManager()
    await mgr.create(
        sandbox_key=uuid4(),
        run_id=uuid4(),
        task_timeout_minutes=30,
        max_criterion_timeout_minutes=10,
    )

    call_kwargs = fake_create.await_args.kwargs
    assert call_kwargs["timeout"] == 40 * 60, "Should be (30 + 10) * 60 = 2400s"


@pytest.mark.asyncio
async def test_create_default_max_criterion_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default max_criterion_timeout_minutes=10 is applied when not supplied."""
    fake_sandbox = MagicMock()
    fake_sandbox.sandbox_id = "sbx-default"
    fake_create = AsyncMock(return_value=fake_sandbox)
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(create=fake_create),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = _MinimalManager()
    await mgr.create(sandbox_key=uuid4(), run_id=uuid4(), task_timeout_minutes=20)

    call_kwargs = fake_create.await_args.kwargs
    assert call_kwargs["timeout"] == 30 * 60, "Should be (20 + 10) * 60 = 1800s"


@pytest.mark.asyncio
async def test_create_zero_criterion_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Caller can pass max_criterion_timeout_minutes=0 to opt out of headroom."""
    fake_sandbox = MagicMock()
    fake_sandbox.sandbox_id = "sbx-zero"
    fake_create = AsyncMock(return_value=fake_sandbox)
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(create=fake_create),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = _MinimalManager()
    await mgr.create(
        sandbox_key=uuid4(),
        run_id=uuid4(),
        task_timeout_minutes=15,
        max_criterion_timeout_minutes=0,
    )

    call_kwargs = fake_create.await_args.kwargs
    assert call_kwargs["timeout"] == 15 * 60, "Zero criterion timeout: total = task only"
```

### Unit tests — `tests/unit/test_sandbox_reconnect.py`

```python
# tests/unit/test_sandbox_reconnect.py

"""Unit tests: BaseSandboxManager.reconnect()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ergon_core.core.providers.sandbox.errors import SandboxExpiredError
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}
    yield
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}


class _MinimalManager(BaseSandboxManager):
    async def _install_dependencies(self, sandbox, task_id):  # type: ignore[override]
        pass

    async def _create_directory_structure(self, sandbox, sandbox_key):  # type: ignore[override]
        pass


@pytest.mark.asyncio
async def test_reconnect_returns_sandbox_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """reconnect() returns the AsyncSandbox handle on successful connect."""
    fake_sandbox = MagicMock()
    fake_connect = AsyncMock(return_value=fake_sandbox)
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(connect=fake_connect),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = _MinimalManager()
    result = await mgr.reconnect("sbx-live-001")

    assert result is fake_sandbox
    fake_connect.assert_awaited_once_with(sandbox_id="sbx-live-001", api_key="test-key")


@pytest.mark.asyncio
async def test_reconnect_raises_sandbox_expired_on_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reconnect() raises SandboxExpiredError when E2B returns 'not found'."""
    fake_connect = AsyncMock(side_effect=Exception("sandbox not found (404)"))
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(connect=fake_connect),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = _MinimalManager()
    with pytest.raises(SandboxExpiredError) as exc_info:
        await mgr.reconnect("sbx-expired-001")

    assert exc_info.value.sandbox_id == "sbx-expired-001"
    assert "sbx-expired-001" in str(exc_info.value)


@pytest.mark.asyncio
async def test_reconnect_reraises_non_expiry_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """reconnect() re-raises unexpected E2B errors unchanged."""
    fake_connect = AsyncMock(side_effect=ConnectionError("network blip"))
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(connect=fake_connect),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-key",
    )

    mgr = _MinimalManager()
    with pytest.raises(ConnectionError, match="network blip"):
        await mgr.reconnect("sbx-network-error")
```

### E2e canary — `tests/e2e/test_sandbox_criterion_timeout_canary.py`

This test confirms the invariant end-to-end. It requires a live E2B key and is
gated behind the `e2e` marker.

```python
# tests/e2e/test_sandbox_criterion_timeout_canary.py

"""Canary: a sandbox provisioned with task+criterion timeout survives a slow criterion.

If this test starts failing, we have regressed on the invariant that
sandbox_timeout >= task_timeout + max_criterion_timeout.

Requires E2B_API_KEY.  Only runs in CI on feature/* branches (e2e suite).
"""

import asyncio
import pytest
from uuid import uuid4

from ergon_core.core.providers.sandbox.manager import DefaultSandboxManager, BaseSandboxManager


@pytest.fixture(autouse=True)
def _reset_singleton():
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}
    BaseSandboxManager._creation_locks = {}
    BaseSandboxManager._run_ids = {}
    BaseSandboxManager._display_task_ids = {}
    BaseSandboxManager._file_registries = {}
    BaseSandboxManager._created_files_registry = {}
    yield
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_sandbox_survives_slow_criterion() -> None:
    """Provision sandbox with task_timeout=1m, max_criterion_timeout=2m.
    Sleep for 90s (longer than task_timeout alone), then reconnect.
    Confirm sandbox is still reachable.
    """
    mgr = DefaultSandboxManager()
    task_id = uuid4()
    run_id = uuid4()

    sandbox_id = await mgr.create(
        sandbox_key=task_id,
        run_id=run_id,
        task_timeout_minutes=1,
        max_criterion_timeout_minutes=2,
    )

    # Simulate task completion + slow criterion: wait 90s (> 1-minute task timeout)
    await asyncio.sleep(90)

    # Criterion reconnects via manager.reconnect — sandbox must still be live.
    sandbox = await mgr.reconnect(sandbox_id)
    result = await sandbox.commands.run("echo 'sandbox alive'", timeout=10)
    assert result.exit_code == 0, "Sandbox must be reachable after criterion headroom"
    assert "sandbox alive" in (result.stdout or "")

    await BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)
```

---

## Trace / observability impact

### Updated WAL entry log

`BaseSandboxManager.create()` currently emits a `sandbox.created` WAL entry
with `stdout=f"sandbox_id=...\ntimeout={timeout_minutes}m"`. After this RFC,
it emits:

```
sandbox_id=sbx-abc123
task_timeout=30m
max_criterion_timeout=10m
total_timeout=40m
```

This is a log content change only; no schema migration or DB change. Operators
inspecting sandbox WAL events in the dashboard will now see the split values.

### `sandbox_created` event sink

`SandboxEventSink.sandbox_created` receives `timeout_minutes: int`
(`event_sink.py:15`). After this RFC, the value passed is
`total_timeout_minutes` (= `task_timeout + max_criterion_timeout`). The
contract is unchanged (the field is "how many minutes this sandbox was
provisioned for"); the value now correctly reflects actual provisioned lifetime
rather than the mistaken task-only value.

### Span attributes

`sandbox_setup_fn` emits a `sandbox.setup` span with `timeout_minutes` absent
today (it emits `sandbox_id`, `benchmark_type`, `input_resource_count`). No
new span attributes are required. If observability of the split is needed, add
`task_timeout_minutes` and `max_criterion_timeout_minutes` to span attributes
in a follow-up.

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `AsyncSandbox.connect()` API not available in installed `e2b_code_interpreter` version | `reconnect()` raises `AttributeError` at runtime | Check against current E2B SDK before merge; the method exists in `e2b-code-interpreter>=0.7`. Pin if needed. |
| Callers passing positional `timeout_minutes` break at rename | `TypeError` at call site | Grep confirms no positional callers; all call sites use `timeout_minutes=N` kwargs. Migration is mechanical. |
| `max_criterion_timeout_minutes=10` default is insufficient for long agentic criteria | Sandbox expires; criterion returns `"sandbox-expired"` | Default is conservative; benchmarks with longer criteria override at their `create()` call site. Calibrate via p99 criterion wall-clock. |
| `reconnect()` does not update `_sandboxes` class dict | `get_sandbox(task_id)` returns `None` after reconnect | Documented: `reconnect()` is for cross-process use; in-process criteria continue to use `get_sandbox(task_id)`. Cross-process callers hold the returned handle directly. |
| Test call sites forget to update `timeout_minutes=5` → `task_timeout_minutes=5` | Tests break with `TypeError` | Grep for `timeout_minutes=` before merge; all affected files listed in the file map. |
| `SandboxExpiredError` swallowed by `CriterionRuntime.ensure_sandbox` before RFC `2026-04-17-criterion-runtime-di-container` lands | Criterion gets `None` sandbox and raises a generic `RuntimeError` | Acceptable interim state; `reconnect` is not wired into `ensure_sandbox` until the DI container RFC. Until then, `ensure_sandbox` provisions a fresh sandbox on `None`, which is the current behavior. |
| `DefaultSandboxManager` stub mode (`SANDBOX_SKIPPED`) short-circuits before reaching the new timeout logic | No effect; stub mode returns early before any E2B call | No change to behavior; `SANDBOX_SKIPPED` path is unaffected. |

---

## Invariants affected

### `docs/architecture/03_providers.md#invariants`

**Invariant 5** currently reads:

> **Sandbox lives across evaluator fan-out.** Teardown runs at the end of
> `check_evaluators`, not at task completion, not in `finalize_success`.
> Enforced by the evaluator harness, not by the manager itself.

Tighten to:

> **Sandbox lives across evaluator fan-out.** Teardown runs at the end of
> `check_evaluators`, not at task completion, not in `finalize_success`.
> Enforced by the evaluator harness. **The sandbox timeout on create MUST be at
> least `task_timeout + max_criterion_timeout`; `BaseSandboxManager.create()`
> enforces this by accepting both parameters and passing their sum to E2B.**

**Known limits section** — remove:

> **No `reconnect()` method.** Cross-process criteria must spawn their own
> sandbox (see `ergon_builtins/benchmarks/swebench_verified/criterion.py:66`).

Replace with:

> **`reconnect()` does not update class-level `_sandboxes` state.** It is
> intended for cross-process criterion use. In-process criteria should use
> `get_sandbox(task_id)` which reads shared class state. The reconnect path
> for cross-process criteria is gated on RFC
> `2026-04-17-criterion-runtime-di-container` landing.

### `docs/architecture/cross_cutting/sandbox_lifecycle.md`

**Invariant 2** currently reads:

> **Sandbox timeout on creation MUST be at least `task_timeout + max_criterion_timeout`.**
> ... Pending enforcement in RFC 2026-04-17-sandbox-lifetime-covers-criteria.
> Today this is a convention.

Update to:

> **Sandbox timeout on creation MUST be at least `task_timeout +
> max_criterion_timeout`.** Enforced by `BaseSandboxManager.create()` which
> accepts `task_timeout_minutes` and `max_criterion_timeout_minutes`
> separately and passes their sum to E2B. The invariant is machine-checked
> by `tests/unit/test_sandbox_timeout.py`.

**Invariant 3** currently reads:

> **Criteria MUST reconnect via the manager, never by constructing `AsyncSandbox`
> directly.** ... The reconnect path through the manager is the only correct way
> to attach to a live sandbox.

Update anti-pattern list (Section 8) to add:

> **Calling `BaseSandboxManager.reconnect(sandbox_id)` from in-process
> criteria.** In-process criteria should use `get_sandbox(task_id)`; `reconnect`
> is for cross-process use and does not register the sandbox in class-level state.

---

## Alternatives considered

- **Leave timeout at `task_timeout`; have criteria pause and re-create the
  sandbox if expired.** Rejected: complicated, loses in-sandbox state (file
  contents, mounted volumes, process state), forces criteria to handle a new
  failure mode.
- **Use a separate "evaluation sandbox" spawned by criteria.** Rejected: system
  owner explicitly does not want criteria spawning sandboxes (see
  `docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md`). Also
  doubles sandbox cost per task.
- **Globally configure a generous timeout (e.g. `task_timeout * 3`).** Rejected:
  opaque; per-benchmark overrides are easier to tune. Multiplicative defaults
  also scale poorly for very short or very long tasks.
- **Keep a single `timeout` arg but document that callers should pre-add
  criterion headroom.** Rejected: the policy leaks out of the manager; every
  caller implements it slightly differently.
- **Add `reconnect` return value to class-level `_sandboxes` state.** Rejected:
  would require passing `task_id` to `reconnect`, which is not always known
  cross-process. The design explicitly keeps cross-process use (reconnect) and
  in-process use (get_sandbox) separate.

---

## Open questions

- What is the right default for `max_criterion_timeout`? 10 minutes is a guess;
  needs empirical calibration against existing benchmarks. Proposed calibration:
  log p99 criterion wall-clock across a week of runs, set default to p99 * 1.5,
  round up to the nearest minute.
- Should `reconnect()` retry once on transient E2B platform errors (e.g. 502s),
  or raise immediately? Recommend raise; callers can retry at their level.
  Retries in the manager hide backpressure signals.
- Is there a use case where a benchmark needs `max_criterion_timeout_minutes=0`
  (no criteria run in-sandbox)? If yes, `create()` should skip the addition and
  pass `timeout=task_timeout`. Today all benchmarks run at least one in-sandbox
  criterion, but this is worth supporting for future criterion-free benchmarks.
  The current implementation already supports `max_criterion_timeout_minutes=0`
  correctly (total = task timeout only).
- How does this interact with sandbox-pool reuse (if the codebase grows one)?
  A pooled sandbox has its own lifetime independent of a specific task; out of
  scope for this RFC, flagged for later.

---

## On acceptance

- Update `docs/architecture/03_providers.md#invariants` — tighten sandbox-lifetime
  invariant 5 and remove the "no reconnect" known limit per the text above.
- Update `docs/architecture/cross_cutting/sandbox_lifecycle.md` invariants 2 and 3,
  and the anti-patterns section, per the text above.
- Link the implementation plan at `docs/superpowers/plans/2026-04-17-sandbox-lifetime-covers-criteria.md`.
- Move this file to `docs/rfcs/accepted/`.
