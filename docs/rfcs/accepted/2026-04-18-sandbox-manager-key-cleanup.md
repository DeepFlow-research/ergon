---
status: accepted
opened: 2026-04-18
author: deepflow-research
architecture_refs:
  - docs/architecture/03_providers.md#sandbox-managers
supersedes: []
superseded_by: null
---

# RFC: Sandbox manager — collapse `sandbox_key` / `display_task_id` to a single `task_id`

## Relationship to the process-state RFC

`docs/rfcs/active/2026-04-18-sandbox-manager-process-state.md` is a broader
reform that removes the singleton, moves class-level state to instances, and
adds cross-process reconnect. This RFC is scoped narrowly to the naming debt in
`create()`'s parameter list. The two RFCs are independent — either can land
first — but this RFC's changes are purely additive cleanup that simplifies the
surface the process-state RFC will later restructure. Landing this one first
reduces the diff size for that RFC.

---

## Problem

`BaseSandboxManager.create()`
(`ergon_core/ergon_core/core/providers/sandbox/manager.py:226-233`) takes three
conceptual task-keys as positional/keyword arguments:

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

Every production call site passes `sandbox_key == display_task_id`, either
explicitly or via the default-collapse at `manager.py:241`:

```python
display_task_id = display_task_id or sandbox_key
```

The three call sites:

1. **`sandbox_setup.py:103-108`** — passes positional `task_id` as `sandbox_key`
   and then `display_task_id=task_id` explicitly (both the same UUID).
2. **`evaluation/criterion_runtime.py:56-60`** — calls
   `manager.create(self.context.run_id, run_id=self.context.run_id, ...)`
   omitting `display_task_id`; the default-to-`sandbox_key` branch fires.
3. **`benchmarks/swebench_verified/criterion.py:74`** — calls
   `manager.create(sandbox_key=sandbox_key, run_id=run_id)` omitting
   `display_task_id`; same default fires.

The `_display_task_ids: dict[UUID, UUID]` class-level dict at `manager.py:70`
is written only in `create()` at line 275 and read only by
`_get_display_task_id()` at `manager.py:96-97`, which is only called from
`_emit_wal_entry()` at `manager.py:124` and `terminate()` at `manager.py:444`.

The indirection was introduced to support a hypothetical "subtask reuses parent
sandbox, emits events under parent's task_id" case. That case is unrealized
anywhere in the codebase. The split actively hurts readability: `create()`'s
first parameter is named `sandbox_key` while every other method in the class
names the same concept `task_id` (`get_sandbox(task_id)`, `upload_inputs(task_id,
...)`, `terminate(task_id, ...)`).

This inconsistency is explicitly called out as debt in
`docs/architecture/03_providers.md:42` ("The `sandbox_key` / `task_id` /
`display_task_id` triplet is **debt**") and in the Known Limits section at
`03_providers.md:142`.

Additionally, the class-level `_display_task_ids` dict is one of six dicts
whose unbounded growth is tracked as a latent issue in
`docs/bugs/open/2026-04-18-sandbox-manager-shared-state-race.md`. Deleting
it is a small but real reduction in that surface.

---

## Proposal

### Option chosen: collapse to `task_id`, delete `display_task_id` (YAGNI)

Rename `sandbox_key` → `task_id` throughout `create()` and its internals.
Delete the `display_task_id` parameter and the backing `_display_task_ids`
dict. If a future use case genuinely needs "emit under a different task id,"
implement it at the caller with an explicit `parent_task_id` parameter at that
time.

Concrete steps:

1. `BaseSandboxManager.create()` (`manager.py:226-295`): rename first param
   `sandbox_key` → `task_id`; remove `display_task_id` param; delete line 241
   (`display_task_id = display_task_id or sandbox_key`); write
   `self._display_task_ids[task_id] = task_id` is eliminated (just remove).
2. Delete `_display_task_ids: dict[UUID, UUID] = {}` class attribute
   (`manager.py:70`).
3. Delete `_get_display_task_id()` method (`manager.py:96-97`).
4. Simplify `_emit_wal_entry()` (`manager.py:99-131`): rename `sandbox_key`
   param to `task_id`; replace `self._get_display_task_id(sandbox_key)` at
   line 124 with bare `task_id`.
5. Simplify `terminate()` (`manager.py:429-469`): delete
   `display_task_id = self._get_display_task_id(task_id)` at line 444; delete
   `self._display_task_ids.pop(task_id, None)` at lines 440 and 454; replace
   `display_task_id` with `task_id` in `sandbox_closed()` and
   `_emit_wal_entry()` calls at lines 457 and 468.
6. `DefaultSandboxManager.create()` (`manager.py:503-526`): rename
   `sandbox_key` → `task_id`; remove `display_task_id` param; update
   `super().create()` call accordingly.
7. Update production call sites:
   - `sandbox_setup.py:103-108`: drop `display_task_id=task_id` kwarg (already
     redundant; positional arg is `task_id`).
   - `criterion_runtime.py:56-60`: no rename needed (already passes
     `self.context.run_id` positionally; just drop the `display_task_id` kwarg
     if present — it is absent today).
   - `swebench_verified/criterion.py:74`: rename `sandbox_key=sandbox_key` →
     `task_id=sandbox_key` (the local variable name `sandbox_key` can remain or
     be renamed to `task_id` at the caller's discretion).
8. Update tests that reset `BaseSandboxManager._display_task_ids = {}`:
   - `tests/minif2f/test_sandbox_manager.py:30`
   - `tests/swebench_verified/test_sandbox_manager.py:31`
   - Remove those lines (the attribute no longer exists).
9. Update tests that call `create(sandbox_key=...)`:
   - `tests/minif2f/test_sandbox_manager.py:121,172,206`
   - `tests/swebench_verified/test_sandbox_manager.py:129,180`
   - `tests/minif2f/test_verification_integration.py:79`
   - Rename `sandbox_key=` → `task_id=` at each call.

---

## Architecture overview

### Before

```
create(sandbox_key, run_id, timeout_minutes, envs, display_task_id)
    │
    ├─ display_task_id = display_task_id or sandbox_key   ← always collapses
    ├─ self._sandboxes[sandbox_key] = sandbox
    ├─ self._run_ids[sandbox_key] = run_id
    ├─ self._display_task_ids[sandbox_key] = display_task_id   ← always == sandbox_key
    │
    ├─ _emit_wal_entry(sandbox_key, ...)
    │       task_id = self._get_display_task_id(sandbox_key)   ← reads _display_task_ids
    │
    └─ terminate(task_id)
            display_task_id = self._get_display_task_id(task_id)   ← reads again
            self._display_task_ids.pop(task_id, None)              ← deleted twice
            sandbox_closed(task_id=display_task_id, ...)
```

### After

```
create(task_id, run_id, timeout_minutes, envs)
    │
    ├─ self._sandboxes[task_id] = sandbox
    ├─ self._run_ids[task_id] = run_id
    │                                         ← _display_task_ids gone
    ├─ _emit_wal_entry(task_id, ...)
    │       task_id used directly             ← _get_display_task_id gone
    │
    └─ terminate(task_id)
            sandbox_closed(task_id=task_id, ...)   ← direct
```

No behavioral change. The only observable difference is that the `task_id`
argument to `sandbox_closed()` and `sandbox_command()` was previously
`_display_task_ids.get(sandbox_key, sandbox_key)` — i.e. `sandbox_key` in all
production cases — which is exactly what `task_id` is after the rename.

---

## Full implementation

### Modified file: `ergon_core/ergon_core/core/providers/sandbox/manager.py`

#### 1. Remove `_display_task_ids` class attribute

```diff
-    _display_task_ids: dict[UUID, UUID] = {}
     _creation_locks: dict[UUID, asyncio.Lock] = {}
```

Location: `manager.py:70`. The line is between `_run_ids` and `_creation_locks`.

#### 2. Delete `_get_display_task_id()`

```diff
-    def _get_display_task_id(self, sandbox_key: UUID) -> UUID:
-        return self._display_task_ids.get(sandbox_key, sandbox_key)
-
     async def _emit_wal_entry(  # slopcop: ignore[max-function-params]
```

Location: `manager.py:96-98`.

#### 3. Rename `sandbox_key` → `task_id` in `_emit_wal_entry()` and remove lookup

```diff
     async def _emit_wal_entry(  # slopcop: ignore[max-function-params]
         self,
-        sandbox_key: UUID,
+        task_id: UUID,
         command: str,
         stdout: str | None = None,
         stderr: str | None = None,
         exit_code: int | None = 0,
         started_at: float | None = None,
         duration_ms: int | None = None,
         sandbox_id: str | None = None,
         task_id: UUID | None = None,
     ) -> None:
-        raw_sandbox = self._sandboxes.get(sandbox_key)
+        raw_sandbox = self._sandboxes.get(task_id)
         resolved_sandbox_id = sandbox_id or (raw_sandbox.sandbox_id if raw_sandbox else None)
         if resolved_sandbox_id is None:
             return

         resolved_duration_ms = duration_ms
         if resolved_duration_ms is None and started_at is not None:
             resolved_duration_ms = int((time.time() - started_at) * 1000)

         max_len = settings.otel_stdout_stderr_max_length
-        resolved_run_id = self._run_ids.get(sandbox_key, sandbox_key)
+        resolved_run_id = self._run_ids.get(task_id, task_id)
         await self._event_sink.sandbox_command(
             run_id=resolved_run_id,
-            task_id=task_id or self._get_display_task_id(sandbox_key),
+            task_id=task_id,
             sandbox_id=resolved_sandbox_id,
```

**Note:** The `task_id` parameter in the current signature (`manager.py:109`) is
an optional override for the WAL `task_id` field. After this change, that param
is still present as an explicit override but is never used by the existing
callers (all pass `task_id=None` or omit it). It can be removed as a follow-up
cleanup but is kept here to avoid broadening the diff.

Wait — the current signature has a naming collision: the method parameter
`sandbox_key: UUID` at position 2 and the optional param `task_id: UUID | None`
at position 9. After renaming `sandbox_key` → `task_id` at position 2, the
optional override at position 9 must be renamed to avoid collision. Rename it
to `override_task_id`:

```diff
     async def _emit_wal_entry(  # slopcop: ignore[max-function-params]
         self,
-        sandbox_key: UUID,
+        task_id: UUID,
         command: str,
         stdout: str | None = None,
         stderr: str | None = None,
         exit_code: int | None = 0,
         started_at: float | None = None,
         duration_ms: int | None = None,
         sandbox_id: str | None = None,
-        task_id: UUID | None = None,
+        override_task_id: UUID | None = None,
     ) -> None:
-        raw_sandbox = self._sandboxes.get(sandbox_key)
+        raw_sandbox = self._sandboxes.get(task_id)
         resolved_sandbox_id = sandbox_id or (raw_sandbox.sandbox_id if raw_sandbox else None)
         if resolved_sandbox_id is None:
             return

         resolved_duration_ms = duration_ms
         if resolved_duration_ms is None and started_at is not None:
             resolved_duration_ms = int((time.time() - started_at) * 1000)

         max_len = settings.otel_stdout_stderr_max_length
-        resolved_run_id = self._run_ids.get(sandbox_key, sandbox_key)
+        resolved_run_id = self._run_ids.get(task_id, task_id)
         await self._event_sink.sandbox_command(
             run_id=resolved_run_id,
-            task_id=task_id or self._get_display_task_id(sandbox_key),
+            task_id=override_task_id or task_id,
             sandbox_id=resolved_sandbox_id,
```

#### 4. Rename `sandbox_key` → `task_id` in `BaseSandboxManager.create()`, remove `display_task_id`

```diff
     async def create(
         self,
-        sandbox_key: UUID,
+        task_id: UUID,
         run_id: UUID,
         timeout_minutes: int = 30,
         envs: dict[str, str] | None = None,
-        display_task_id: UUID | None = None,
     ) -> str:
         """Create a new E2B sandbox, set up directories, install deps."""
         if AsyncSandbox is None:
             raise RuntimeError(
                 "e2b_code_interpreter is not installed. "
                 "Install it with: pip install e2b-code-interpreter"
             )

-        display_task_id = display_task_id or sandbox_key
-        lock = self._creation_locks.setdefault(sandbox_key, asyncio.Lock())
+        lock = self._creation_locks.setdefault(task_id, asyncio.Lock())
         async with lock:
-            if sandbox_key in self._sandboxes:
-                return self._sandboxes[sandbox_key].sandbox_id
+            if task_id in self._sandboxes:
+                return self._sandboxes[task_id].sandbox_id

             if not settings.e2b_api_key:
                 raise ValueError(
                     "E2B_API_KEY is not set. "
                     "Please set E2B_API_KEY in your .env file or environment variables."
                 )

             try:
                 timeout_seconds = timeout_minutes * 60
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
-                    f"Failed to create sandbox for sandbox_key={sandbox_key}: {e}"
+                    f"Failed to create sandbox for task_id={task_id}: {e}"
                 ) from e

             if not sandbox:
                 raise RuntimeError("Sandbox object is None after creation")

-            self._sandboxes[sandbox_key] = sandbox
-            self._ensure_registries(sandbox_key)
-            self._run_ids[sandbox_key] = run_id
-            self._display_task_ids[sandbox_key] = display_task_id
+            self._sandboxes[task_id] = sandbox
+            self._ensure_registries(task_id)
+            self._run_ids[task_id] = run_id

             await self._event_sink.sandbox_created(
                 run_id=run_id,
-                task_id=display_task_id,
+                task_id=task_id,
                 sandbox_id=sandbox.sandbox_id,
                 timeout_minutes=timeout_minutes,
             )
             await self._emit_wal_entry(
-                sandbox_key,
+                task_id,
                 command="sandbox.created",
                 stdout=f"sandbox_id={sandbox.sandbox_id}\ntimeout={timeout_minutes}m",
                 exit_code=0,
                 duration_ms=0,
             )

-            await self._create_directory_structure(sandbox, sandbox_key)
-            await self._install_dependencies(sandbox, display_task_id)
-            await self._verify_setup(sandbox, display_task_id)
+            await self._create_directory_structure(sandbox, task_id)
+            await self._install_dependencies(sandbox, task_id)
+            await self._verify_setup(sandbox, task_id)

             return sandbox.sandbox_id
```

#### 5. Simplify `terminate()`: remove `_display_task_ids` pops and rename

```diff
     async def terminate(self, task_id: UUID, reason: str = "completed") -> None:
         """Terminate sandbox by task_id key and clean up all registries."""
         sandbox = self._sandboxes.pop(task_id, None)
         if sandbox is None:
             logger.warning(
                 "Sandbox not found for task_id=%s. Already terminated or never created.",
                 task_id,
             )
             self._file_registries.pop(task_id, None)
             self._created_files_registry.pop(task_id, None)
             self._run_ids.pop(task_id, None)
-            self._display_task_ids.pop(task_id, None)
             return

         sandbox_id = sandbox.sandbox_id
-        display_task_id = self._get_display_task_id(task_id)
         try:
             await sandbox.kill()
         except Exception as e:  # slopcop: ignore[no-broad-except]
             logger.warning("Error killing sandbox for task_id=%s: %s", task_id, e)
             reason = "error"
         finally:
             self._file_registries.pop(task_id, None)
             self._created_files_registry.pop(task_id, None)
             self._run_ids.pop(task_id, None)
-            self._display_task_ids.pop(task_id, None)

             await self._event_sink.sandbox_closed(
-                task_id=display_task_id,
+                task_id=task_id,
                 sandbox_id=sandbox_id,
                 reason=reason,
             )
             await self._emit_wal_entry(
                 task_id,
                 command=f"sandbox.closed: {reason}",
                 stdout=f"sandbox_id={sandbox_id}",
                 exit_code=0,
                 duration_ms=0,
                 sandbox_id=sandbox_id,
-                task_id=display_task_id,
+                override_task_id=task_id,
             )
```

#### 6. Update `DefaultSandboxManager.create()`

```diff
     async def create(
         self,
-        sandbox_key: UUID,
+        task_id: UUID,
         run_id: UUID,
         timeout_minutes: int = 30,
         envs: dict[str, str] | None = None,
-        display_task_id: UUID | None = None,
     ) -> str:
         if not settings.e2b_api_key:
             from ergon_core.core.runtime.events.task_events import SANDBOX_SKIPPED

             logger.info(
                 "E2B_API_KEY not set — skipping sandbox creation for task %s (stub mode)",
-                sandbox_key,
+                task_id,
             )
             return SANDBOX_SKIPPED
         return await super().create(
-            sandbox_key,
+            task_id,
             run_id=run_id,
             timeout_minutes=timeout_minutes,
             envs=envs,
-            display_task_id=display_task_id,
         )
```

---

### Modified file: `ergon_core/ergon_core/core/runtime/inngest/sandbox_setup.py`

Drop the redundant `display_task_id=task_id` kwarg (`sandbox_setup.py:108`):

```diff
     sandbox_id = await sandbox_manager.create(
         task_id,
         run_id=run_id,
         timeout_minutes=30,
         envs=envs,
-        display_task_id=task_id,
     )
```

The first positional argument is already `task_id`; no other change needed.

---

### Modified file: `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py`

`ensure_sandbox()` at `criterion_runtime.py:53-60` already passes
`self.context.run_id` positionally with no `display_task_id` kwarg. No
parameter rename is needed at the call site. No change required.

---

### Modified file: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py`

Rename the keyword argument at `criterion.py:74`:

```diff
-    await manager.create(sandbox_key=sandbox_key, run_id=run_id)
+    await manager.create(task_id=sandbox_key, run_id=run_id)
```

The local variable `sandbox_key` retains its name (it is a freshly-generated
`uuid4()` at line 73 used only for this call and the subsequent `get_sandbox`
call at line 75).

---

### Modified files: tests

**`tests/minif2f/test_sandbox_manager.py`**

```diff
-    BaseSandboxManager._display_task_ids = {}
```
Remove line 30 from the `_reset_sandbox_singleton` fixture. Also remove it from
the yield-teardown block if present.

Rename keyword arg at three call sites (lines 121, 172, 206):
```diff
-    sandbox_id = await mgr.create(sandbox_key=uuid4(), run_id=uuid4(), timeout_minutes=5)
+    sandbox_id = await mgr.create(task_id=uuid4(), run_id=uuid4(), timeout_minutes=5)

-    await mgr.create(sandbox_key=uuid4(), run_id=uuid4())  # line 172
+    await mgr.create(task_id=uuid4(), run_id=uuid4())

-    await mgr.create(sandbox_key=uuid4(), run_id=uuid4())  # line 206
+    await mgr.create(task_id=uuid4(), run_id=uuid4())
```

**`tests/swebench_verified/test_sandbox_manager.py`**

```diff
-    BaseSandboxManager._display_task_ids = {}
```
Remove line 31 from the fixture.

Rename keyword arg at two call sites (lines 129, 180):
```diff
-    sandbox_id = await mgr.create(sandbox_key=uuid4(), run_id=uuid4(), timeout_minutes=5)
+    sandbox_id = await mgr.create(task_id=uuid4(), run_id=uuid4(), timeout_minutes=5)

-    await mgr.create(sandbox_key=uuid4(), run_id=uuid4())  # line 180
+    await mgr.create(task_id=uuid4(), run_id=uuid4())
```

**`tests/minif2f/test_verification_integration.py`**

```diff
     await sandbox_manager.create(
-        sandbox_key=run_id,
+        task_id=run_id,
         run_id=run_id,
         timeout_minutes=10,
     )
```

---

## Package structure

No new packages. No `__init__.py` changes. This RFC modifies existing files only.

---

## Implementation order

| Step | Phase | What | Files touched |
|---|---|---|---|
| 1 | PR 1 | Delete `_display_task_ids` class attr and `_get_display_task_id()` method; rename `sandbox_key` → `task_id` and remove `display_task_id` param in `BaseSandboxManager.create()`; rename `override_task_id` in `_emit_wal_entry()`; simplify `terminate()` | MODIFY `manager.py` |
| 2 | PR 1 | Update `DefaultSandboxManager.create()` to match | MODIFY `manager.py` |
| 3 | PR 1 | Drop `display_task_id=task_id` in `sandbox_setup.py` | MODIFY `sandbox_setup.py` |
| 4 | PR 1 | Rename `sandbox_key=` → `task_id=` in SWEBench criterion | MODIFY `swebench_verified/criterion.py` |
| 5 | PR 1 | Update all tests: remove `_display_task_ids` resets; rename `sandbox_key=` → `task_id=` at call sites | MODIFY `test_sandbox_manager.py` (×2), `test_verification_integration.py` |
| 6 | PR 1 | Grep-verify: zero remaining occurrences of `sandbox_key`, `display_task_id`, `_display_task_ids`, `_get_display_task_id` anywhere under `ergon/` (docs and tests included) | No file changes |

All steps fit a single PR. No staged rollout needed — the rename is mechanical
and all call sites are in-repo.

---

## File map

### ADD

None.

### MODIFY

| File | Changes |
|---|---|
| `ergon_core/ergon_core/core/providers/sandbox/manager.py` | Delete `_display_task_ids` attr (line 70); delete `_get_display_task_id()` (lines 96-97); rename `sandbox_key`→`task_id` + remove `display_task_id` in `BaseSandboxManager.create()` (lines 226-295); rename `sandbox_key`→`task_id` + rename `task_id`→`override_task_id` in `_emit_wal_entry()` (lines 99-131); simplify `terminate()` (lines 429-469); rename + remove `display_task_id` in `DefaultSandboxManager.create()` (lines 503-526) |
| `ergon_core/ergon_core/core/runtime/inngest/sandbox_setup.py` | Drop `display_task_id=task_id` kwarg at line 108 |
| `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py` | Rename `sandbox_key=` → `task_id=` at line 74 |
| `tests/minif2f/test_sandbox_manager.py` | Remove `BaseSandboxManager._display_task_ids = {}` at line 30; rename `sandbox_key=` → `task_id=` at lines 121, 172, 206 |
| `tests/swebench_verified/test_sandbox_manager.py` | Remove `BaseSandboxManager._display_task_ids = {}` at line 31; rename `sandbox_key=` → `task_id=` at lines 129, 180 |
| `tests/minif2f/test_verification_integration.py` | Rename `sandbox_key=run_id` → `task_id=run_id` at line 79 |

---

## Testing approach

### Unit — verifying the rename does not break existing behavior

The existing test suites in `tests/minif2f/test_sandbox_manager.py` and
`tests/swebench_verified/test_sandbox_manager.py` already exercise
`create()`/`terminate()` paths against a mocked `AsyncSandbox`. After the
keyword-arg renames, all existing tests must pass unchanged (aside from the
fixture cleanup and call-site renames listed above).

Representative new assertions to add to `test_sandbox_manager.py`:

```python
# tests/minif2f/test_sandbox_manager.py

async def test_create_uses_task_id_as_event_task_id(
    fake_create: AsyncMock,
    recording_sink: RecordingSandboxEventSink,
) -> None:
    """After the rename, sandbox_created fires with task_id equal to the
    task_id arg — no display_task_id indirection."""
    mgr = MiniF2FSandboxManager()
    task_id = uuid4()
    run_id = uuid4()
    await mgr.create(task_id=task_id, run_id=run_id)

    assert len(recording_sink.created_events) == 1
    event = recording_sink.created_events[0]
    assert event["task_id"] == task_id
    assert event["run_id"] == run_id


async def test_terminate_fires_closed_with_same_task_id(
    fake_create: AsyncMock,
    recording_sink: RecordingSandboxEventSink,
) -> None:
    """terminate() emits sandbox_closed with the same task_id passed to create()."""
    mgr = MiniF2FSandboxManager()
    task_id = uuid4()
    await mgr.create(task_id=task_id, run_id=uuid4())
    await mgr.terminate(task_id)

    assert len(recording_sink.closed_events) == 1
    assert recording_sink.closed_events[0]["task_id"] == task_id


def test_display_task_ids_attr_absent() -> None:
    """Class-level _display_task_ids must not exist after this RFC."""
    assert not hasattr(BaseSandboxManager, "_display_task_ids")


def test_get_display_task_id_method_absent() -> None:
    """_get_display_task_id must not exist after this RFC."""
    assert not hasattr(BaseSandboxManager, "_get_display_task_id")
```

### Integration — no new integration tests required

The three production call sites are each covered by the existing test suites
once the keyword-arg renames are applied. No new integration test surface is
introduced because no behavior changes.

### Regression grep check

Before merging, run:

```bash
grep -rn "sandbox_key\|display_task_id\|_display_task_ids\|_get_display_task_id" \
    ergon_core ergon_builtins ergon_cli ergon_infra tests
```

Expected: zero matches. Any remaining hit is a missed call site.

---

## Trace / observability impact

`_emit_wal_entry()` emits `task_id` to `sandbox_command()` on the event sink.
Before this RFC, it passed `self._get_display_task_id(sandbox_key)` which
resolved to `sandbox_key` in every production case. After this RFC it passes
`task_id` directly. The value is identical in all current production cases,
so no span or event payload changes.

The `override_task_id` optional parameter in `_emit_wal_entry()` is only used
by `terminate()`'s own `_emit_wal_entry()` call (passing the explicit `task_id`
again). That is a no-op equivalent and exists for forward compatibility if a
future caller genuinely needs to override the emitted task id.

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| External `BaseSandboxManager` subclass overriding `create(sandbox_key, ...)` | `TypeError` on mismatch after rename | No external subclasses exist in-repo. Architecture doc Section 5.2 says subclasses are owned per-benchmark inside `ergon_builtins/`. The change is intra-repo only. |
| `_emit_wal_entry`'s `task_id` / `override_task_id` rename breaks a test that passes it as a keyword | Test-only `TypeError` | Grep confirms only `terminate()` calls `_emit_wal_entry()` with the positional `task_id` — and that positional slot is now the first `task_id` param, not the old optional one. No callers use the optional by name today. |
| The swebench criterion local variable `sandbox_key` (line 73) confuses future readers | Minor readability cost | Acceptable: the local var is used for two lines only. A follow-up can rename it. Does not affect behavior. |
| Missing call site — a test helper passes `sandbox_key=` to a manager subclass we haven't grepped | Silent wrong kwarg → `TypeError` at test time | The post-PR grep check (`grep -rn sandbox_key ...`) is mandatory before merge. CI will also catch any `TypeError` at test time. |
| `DefaultSandboxManager.create()` log line still says "task %s" after rename | No behavioral impact | Line already says "task %s" (not "sandbox_key %s"); the variable passed changes from `sandbox_key` to `task_id` — correct after rename. |

---

## Invariants affected

**`docs/architecture/03_providers.md` — updates required on acceptance:**

- **Section 2.2, line 42** ("The `sandbox_key` / `task_id` / `display_task_id` triplet is **debt**"): replace with "Collapsed to `task_id` in
  `docs/rfcs/accepted/2026-04-18-sandbox-manager-key-cleanup.md`."
- **Section 2.2, control-flow block** (`03_providers.md:93`):
  `create(sandbox_key=task_id, ...)` → `create(task_id, ...)`.
- **Section 4, invariant 4** (`03_providers.md:131`): "Enforced by `create`
  accepting `sandbox_key`" → "Enforced by `create` accepting `task_id`."
- **Section 4.1 Known Limits** (`03_providers.md:142`): drop the
  "Key-triplet debt" bullet.
- **Section 6 Anti-patterns**: no change needed.

The `_display_task_ids` class-level dict is one of the six class-level mutable
dicts flagged in `docs/bugs/open/2026-04-18-sandbox-manager-shared-state-race.md`
and in the process-state RFC. Removing it reduces the unbounded-growth surface
without requiring the broader singleton reform. The bug report's scope statement
should be updated to reflect that `_display_task_ids` is gone; the remaining
five dicts are still addressed by the process-state RFC.

---

## Alternatives considered

- **Rename `sandbox_key` → `task_id` but keep `display_task_id` for future
  flexibility.** Rejected: YAGNI. If the subtask-sharing case appears, solve it
  when it is real — with an explicit `parent_task_id` at the caller.
- **Rename everywhere but keep `_display_task_ids` around as dead structure.**
  Rejected: a dict that is always `{k: k}` is noise and contributes to the
  unbounded-growth surface.
- **Keep `sandbox_key` as-is and just alias `task_id` as an alternate param.**
  Rejected: two names for the same concept in the same class hierarchy is the
  exact problem being solved; adding a third alias makes it worse.

---

## Open questions

- Interaction with `docs/rfcs/active/2026-04-18-sandbox-manager-process-state.md`:
  light coupling only — that RFC will restructure the class-level dicts this RFC
  cleans up. The rename is purely additive from that RFC's perspective; it will
  see `task_id` everywhere and fewer dicts to move.

---

## On acceptance

- Move this RFC to `accepted/`.
- Update `docs/architecture/03_providers.md` as described in "Invariants
  affected" above: simplify the `create()` signature documentation; remove the
  key-triplet debt bullet; update the control-flow block.
- Update `docs/bugs/open/2026-04-18-sandbox-manager-shared-state-race.md`: note
  that `_display_task_ids` has been removed; the remaining class-level dicts are
  still addressed by the process-state RFC.
- Grep for remaining uses of the terms `sandbox_key`, `display_task_id`,
  `_display_task_ids`, `_get_display_task_id` in `docs/` and `tests/` and update
  to `task_id`.
- No Alembic migration needed — all changed state is in-memory.
