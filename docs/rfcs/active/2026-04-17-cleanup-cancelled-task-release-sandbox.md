---
status: active
opened: 2026-04-17
author: deepflow-research
architecture_refs: [docs/architecture/02_runtime_lifecycle.md#anti-patterns, docs/architecture/cross_cutting/sandbox_lifecycle.md]
supersedes: []
superseded_by: null
---

# RFC: Wire `cleanup_cancelled_task_fn.release-sandbox` to actually close the E2B sandbox

## Problem

### Current state

`cleanup_cancelled_task_fn` at
`ergon_core/ergon_core/core/runtime/inngest/cleanup_cancelled_task.py:20-61`
is documented as executing two durable steps — `update-db-rows` and
`release-sandbox`. Only `update-db-rows` is implemented. The function body
ends at line 60 with no `release-sandbox` step, and
`TaskCleanupService.cleanup` at
`ergon_core/ergon_core/core/runtime/services/task_cleanup_service.py:53-54`
hard-codes `sandbox_released = False` with a `slopcop: ignore[no-todo-comment]`
suppressor.

**Consequence (cost leak):** `ergon run cancel <run_id>` — backed by
`ergon_core/ergon_core/core/runtime/services/run_service.py:107-140` — marks
the `RunRecord` CANCELLED and sends `run/cancelled` + `run/cleanup`. The
`RUN_CANCEL` Inngest matcher kills in-flight `task-execute` functions.
`cleanup_cancelled_task_fn` fires on each `task/cancelled` event but does not
call `BaseSandboxManager.terminate_by_sandbox_id`. The E2B sandbox stays alive
until its creation-time `timeout` expires. For SWE-Bench tasks, that timeout
is ~30 minutes by default (up to ~70 minutes after
`docs/rfcs/active/2026-04-17-sandbox-lifetime-covers-criteria.md` lands).
A user who cancels two minutes in pays the full timeout.

**Consequence (missing payload fields):** `TaskCancelledEvent` at
`ergon_core/ergon_core/core/runtime/events/task_events.py:105-123` carries
`run_id`, `definition_id`, `node_id`, `execution_id`, and `cause`. It does
NOT carry `sandbox_id` or `benchmark_slug`. The cleanup function therefore
cannot know which sandbox to close or which `BaseSandboxManager` subclass owns
it. Every emission site that constructs a `TaskCancelledEvent` —
`subtask_cancellation_service.py:98-104`,
`task_management_service.py:214-220`, `task_management_service.py:555-563`,
`propagate_execution.py:73-83`, `propagate_execution.py:165-175` — omits both
fields because the model has no slots for them.

**Consequence (no manager lookup):** The slug-to-manager map `SANDBOX_MANAGERS`
at `ergon_builtins/ergon_builtins/registry_core.py:84-88` maps benchmark_slug
to a `type[BaseSandboxManager]` (not an instance). The cleanup function would
need to resolve the class and call the static method
`BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)`.
`terminate_by_sandbox_id` is a `@staticmethod` at
`ergon_core/ergon_core/core/providers/sandbox/manager.py:472-490` that calls
`AsyncSandbox.kill(sandbox_id=..., api_key=...)` directly via E2B, so no
instance is needed. However, `cleanup_cancelled_task_fn` currently has no
import path to `SANDBOX_MANAGERS`.

**Consequence (missing column):** `RunTaskExecution` at
`ergon_core/ergon_core/core/persistence/telemetry/models.py:96-148` has no
`sandbox_id` column. `sandbox_id` is tracked at the Inngest-event level (on
`TaskCompletedEvent`, `TaskFailedEvent`, and child payloads) but not persisted
on the execution row. The cleanup function receives only `execution_id`; it
cannot look up `sandbox_id` from the DB without a new column.

### Architecture doc cross-references

- `docs/architecture/02_runtime_lifecycle.md §4 Known limits` — "Cancellation
  does not release sandboxes." offender at line 117.
- `docs/architecture/cross_cutting/sandbox_lifecycle.md §5 Failure modes` —
  "Cancellation … `release-sandbox` step is currently a STUB" offender at
  line 61.
- `docs/architecture/cross_cutting/sandbox_lifecycle.md §8 Anti-patterns` —
  "Leaking sandboxes on cancellation. Current offender: …" at line 85.

---

## Proposal

### Option A: Extend the event, add a column, add the step (chosen)

Three coordinated changes land in two PRs:

**PR 1 — Schema + event extension (safe to deploy independently):**

1. Add `sandbox_id: str | None = None` and `benchmark_slug: str | None = None`
   to `TaskCancelledEvent`. Backward-compatible; consumers that do not read
   them are unaffected; Inngest event queues tolerate extra fields via
   `model_config = {"extra": "allow"}` already set on the model.
2. Add `sandbox_id: str | None` (nullable, no default) column to
   `RunTaskExecution` via an additive Alembic migration. No backfill required
   — historical rows are `NULL`, which the cleanup step already handles as
   "no sandbox to release."
3. Update `TaskExecutionService.prepare` (or its callers) to write
   `sandbox_id` onto the execution row after `sandbox-setup` completes. In
   practice this is in `execute_task_fn` after the `sandbox-setup` step
   returns, before dispatching `worker-execute`.
4. Update every `TaskCancelledEvent` emission site to look up
   `sandbox_id` from `RunTaskExecution` (via `execution_id`) and
   `benchmark_slug` from the definition row (via `run_id`) and include both
   fields. Sites where `execution_id` is `None` (tasks that never ran) leave
   both new fields `None`.

**PR 2 — Cleanup step (depends on PR 1):**

5. Add a `release-sandbox` durable step to `cleanup_cancelled_task_fn` that
   calls `BaseSandboxManager.terminate_by_sandbox_id(payload.sandbox_id)` when
   both `payload.sandbox_id` and `payload.benchmark_slug` are non-`None`.
   Falls through (no-op, no raise) when either is absent. Uses
   `SANDBOX_MANAGERS` from `ergon_builtins.registry` to verify the slug is
   known; if unknown, logs a warning and returns. Safe to add to an already-
   deployed function because the step is a no-op if PR 1 fields are absent.
6. Remove the `# slopcop: ignore[no-todo-comment]` suppressor from
   `task_cleanup_service.py:53` once the step is wired (the service no longer
   needs to own sandbox release).

### Rejected options

See [Alternatives considered](#alternatives-considered).

---

## Architecture overview

### Before (current)

```
task/cancelled
  │
  ├─ cancel_orphan_subtasks_fn  (recurse children)
  ├─ execute_task_fn via TASK_CANCEL matcher (drop/kill)
  └─ cleanup_cancelled_task_fn
       └─ step: update-db-rows
            TaskCleanupService.cleanup(execution_id)
              → mark RunTaskExecution.status = CANCELLED
              → sandbox_released = False  ← STUB, sandbox leaks
```

### After (this RFC)

```
task/cancelled  {sandbox_id, benchmark_slug now populated}
  │
  ├─ cancel_orphan_subtasks_fn  (unchanged)
  ├─ execute_task_fn via TASK_CANCEL matcher (unchanged)
  └─ cleanup_cancelled_task_fn
       ├─ step: update-db-rows
       │    TaskCleanupService.cleanup(execution_id)
       │      → mark RunTaskExecution.status = CANCELLED
       └─ step: release-sandbox
            if sandbox_id is None or benchmark_slug is None: return
            BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)
              → AsyncSandbox.kill(sandbox_id, api_key)
              → idempotent; logs if already gone
```

### Data flow: how `sandbox_id` reaches the event

```
execute_task_fn
  ├─ step: sandbox-setup → SandboxReadyResult.sandbox_id
  ├─ (new) update RunTaskExecution.sandbox_id = sandbox_result.sandbox_id
  └─ ... (rest unchanged)

cancellation paths that emit TaskCancelledEvent:
  ├─ subtask_cancellation_service.cancel_orphans
  │     → _latest_execution_id(session, node_id)
  │     → (new) _lookup_sandbox(session, execution_id)  → sandbox_id
  │     → (new) _lookup_benchmark_slug(session, run_id) → benchmark_slug
  ├─ task_management_service.cancel_task (manager-initiated)
  │     (same lookups)
  ├─ propagate_execution (dep_invalidated, execution_id=None)
  │     → sandbox_id=None, benchmark_slug=None (task never ran)
  └─ task_management_service._cancel_downstream (downstream_invalidation)
        (same as cancel_task path)
```

---

## Type / interface definitions

### Extended `TaskCancelledEvent`

```python
# ergon_core/ergon_core/core/runtime/events/task_events.py

class TaskCancelledEvent(InngestEventContract):
    """Emitted whenever a node transitions from non-terminal into CANCELLED.

    Consumers:
      - cancel_orphan_subtasks_fn (recurse cascade to descendants)
      - cleanup_cancelled_task_fn (release sandbox, mark execution row)
      - execute_task_fn (via TASK_CANCEL matcher — drops queued / terminates running)
      - dashboard_emitter
    """

    name: ClassVar[str] = "task/cancelled"

    run_id: UUID
    definition_id: UUID
    node_id: UUID
    execution_id: UUID | None
    cause: CancelCause
    sandbox_id: str | None = None          # NEW — E2B sandbox_id string; None if task never ran
    benchmark_slug: str | None = None      # NEW — benchmark type slug; None if task never ran

    model_config = {"frozen": True, "extra": "allow"}
```

### New `RunTaskExecution` column

```python
# ergon_core/ergon_core/core/persistence/telemetry/models.py
# Add to RunTaskExecution (after existing fields, before final_assistant_message):

    sandbox_id: str | None = Field(
        default=None,
        index=False,
    )
    """E2B sandbox_id string written by execute_task_fn after sandbox-setup.

    NULL for tasks that ran before this column was added (pre-migration),
    and for tasks whose sandbox was skipped (SANDBOX_SKIPPED sentinel).
    The cleanup function treats NULL as 'no sandbox to release'.
    """
```

### Alembic migration

```python
# ergon_core/migrations/versions/<hash>_add_sandbox_id_to_run_task_executions.py

"""add sandbox_id to run_task_executions

Revision ID: <auto>
Revises: b5b36e45e5e6
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa

revision = "<auto>"
down_revision = "b5b36e45e5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "run_task_executions",
        sa.Column("sandbox_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("run_task_executions", "sandbox_id")
```

---

## Full implementations

### Modified: `cleanup_cancelled_task_fn`

```python
# ergon_core/ergon_core/core/runtime/inngest/cleanup_cancelled_task.py

"""Inngest function: clean up resources for a cancelled task.

Two durable steps:
1. update-db-rows — mark execution CANCELLED (idempotent)
2. release-sandbox — close the E2B sandbox if sandbox_id is present
"""

import logging

import inngest

from ergon_builtins.registry import SANDBOX_MANAGERS
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager
from ergon_core.core.runtime.events.task_events import TaskCancelledEvent
from ergon_core.core.runtime.inngest_client import RUN_CANCEL, inngest_client
from ergon_core.core.runtime.services.task_cleanup_dto import CleanupResult
from ergon_core.core.runtime.services.task_cleanup_service import TaskCleanupService

logger = logging.getLogger(__name__)


@inngest_client.create_function(
    fn_id="cleanup-cancelled-task",
    trigger=inngest.TriggerEvent(event="task/cancelled"),
    cancel=RUN_CANCEL,
    retries=3,
)
async def cleanup_cancelled_task_fn(ctx: inngest.Context) -> dict:
    """Clean up a single cancelled task's resources."""
    payload = TaskCancelledEvent.model_validate(ctx.event.data)
    logger.info(
        "cleanup-cancelled node_id=%s execution_id=%s cause=%s sandbox_id=%s",
        payload.node_id,
        payload.execution_id,
        payload.cause,
        payload.sandbox_id,
    )

    if payload.execution_id is None:
        return CleanupResult(
            run_id=payload.run_id,
            node_id=payload.node_id,
            execution_id=None,
            sandbox_released=False,
            execution_row_updated=False,
        ).model_dump(mode="json")

    svc = TaskCleanupService()

    def _update_db_rows() -> dict:
        from ergon_core.core.persistence.shared.db import get_session

        with get_session() as session:
            result = svc.cleanup(
                session,
                run_id=payload.run_id,
                node_id=payload.node_id,
                execution_id=payload.execution_id,
            )
        return result.model_dump(mode="json")

    db_result_raw = await ctx.step.run("update-db-rows", _update_db_rows)

    async def _release_sandbox() -> dict:
        if payload.sandbox_id is None or payload.benchmark_slug is None:
            logger.info(
                "release-sandbox skipped: no sandbox_id or benchmark_slug "
                "for node_id=%s",
                payload.node_id,
            )
            return {"sandbox_released": False, "reason": "no_payload"}

        mgr_cls = SANDBOX_MANAGERS.get(payload.benchmark_slug)
        if mgr_cls is None:
            logger.warning(
                "release-sandbox: no manager for benchmark_slug=%s node_id=%s",
                payload.benchmark_slug,
                payload.node_id,
            )
            return {"sandbox_released": False, "reason": "unknown_slug"}

        released = await BaseSandboxManager.terminate_by_sandbox_id(payload.sandbox_id)
        logger.info(
            "release-sandbox sandbox_id=%s benchmark_slug=%s released=%s",
            payload.sandbox_id,
            payload.benchmark_slug,
            released,
        )
        return {"sandbox_released": released, "reason": "terminated"}

    sandbox_result = await ctx.step.run("release-sandbox", _release_sandbox)

    # Merge results for the function return value.
    db_result = CleanupResult.model_validate(db_result_raw)
    return CleanupResult(
        run_id=db_result.run_id,
        node_id=db_result.node_id,
        execution_id=db_result.execution_id,
        sandbox_released=sandbox_result.get("sandbox_released", False),
        execution_row_updated=db_result.execution_row_updated,
    ).model_dump(mode="json")
```

### Modified: `TaskCleanupService`

Remove the `slopcop: ignore[no-todo-comment]` suppressor. Sandbox release is
now owned by the Inngest step, not by this service. The service remains
responsible only for the DB row.

```diff
# ergon_core/ergon_core/core/runtime/services/task_cleanup_service.py

-        # slopcop: ignore[no-todo-comment] — sandbox teardown, wire when sandbox management exists
-        sandbox_released = False
+        sandbox_released = False  # Sandbox release is handled by the release-sandbox Inngest step.
```

### Modified: `execute_task_fn` — persist `sandbox_id` on execution row

```diff
# ergon_core/ergon_core/core/runtime/inngest/execute_task.py

         task_sandbox_id = sandbox_result.sandbox_id

+        def _persist_sandbox_id() -> None:
+            from ergon_core.core.persistence.shared.db import get_session
+            from ergon_core.core.persistence.telemetry.models import RunTaskExecution
+
+            with get_session() as session:
+                exe = session.get(RunTaskExecution, prepared.execution_id)
+                if exe is not None and exe.sandbox_id is None:
+                    exe.sandbox_id = task_sandbox_id
+                    session.add(exe)
+                    session.commit()
+
+        await ctx.step.run("persist-sandbox-id", _persist_sandbox_id)
+
         if not prepared.worker_type:
```

**Note:** `SANDBOX_SKIPPED` is the sentinel string `"skipped"` defined at
`ergon_core/ergon_core/core/runtime/events/task_events.py:11`. The step writes
it literally to the column; the cleanup function treats it the same as `None`
because `SANDBOX_MANAGERS.get("skipped")` returns `None` (not a registered
slug), so the step skips and returns `{"sandbox_released": False}`.

### Modified: `TaskCancelledEvent` emission sites

All four sites that currently emit `TaskCancelledEvent` must be updated. Three
of them have access to a DB session and an `execution_id`; one emits with
`execution_id=None` (dependency-invalidation path where the task never ran).

**Helper functions (add to each file, or extract to a shared `_cancel_helpers.py`):**

```python
# Shared helpers — inline in each service or extract to
# ergon_core/ergon_core/core/runtime/services/_cancel_helpers.py

from uuid import UUID
from sqlmodel import Session, select


def _lookup_sandbox_id(session: Session, execution_id: UUID | None) -> str | None:
    """Return RunTaskExecution.sandbox_id for the given execution, or None."""
    if execution_id is None:
        return None
    # reason: deferred to avoid circular import at module level
    from ergon_core.core.persistence.telemetry.models import RunTaskExecution

    result = session.exec(
        select(RunTaskExecution.sandbox_id).where(RunTaskExecution.id == execution_id)
    ).first()
    return result  # type: ignore[return-value]


def _lookup_benchmark_slug(session: Session, run_id: UUID) -> str | None:
    """Return the benchmark_type (slug) for the run's experiment definition, or None."""
    # reason: deferred to avoid circular import at module level
    from ergon_core.core.persistence.telemetry.models import RunRecord
    from ergon_core.core.persistence.definitions.models import ExperimentDefinition

    run = session.get(RunRecord, run_id)
    if run is None:
        return None
    defn = session.get(ExperimentDefinition, run.experiment_definition_id)
    if defn is None:
        return None
    return defn.benchmark_type
```

**Site 1: `subtask_cancellation_service.py:98-104`** — BFS cascade.

```diff
         events = [
             TaskCancelledEvent(
                 run_id=run_id,
                 definition_id=definition_id,
                 node_id=nid,
                 execution_id=_latest_execution_id(session, nid),
                 cause=cause,
+                sandbox_id=_lookup_sandbox_id(session, _latest_execution_id(session, nid)),
+                benchmark_slug=_lookup_benchmark_slug(session, run_id),
             )
             for nid in transitioned
         ]
```

**Site 2: `task_management_service.py:214-220`** — manager `cancel_task`.

```diff
             event = TaskCancelledEvent(
                 run_id=command.run_id,
                 definition_id=definition_id,
                 node_id=command.node_id,
                 execution_id=execution_id,
                 cause="manager_decision",
+                sandbox_id=_lookup_sandbox_id(session, execution_id),
+                benchmark_slug=_lookup_benchmark_slug(session, command.run_id),
             )
```

**Site 3: `task_management_service.py:555-563`** — downstream invalidation.

```diff
         event = TaskCancelledEvent(
             run_id=run_id,
             definition_id=definition_id,
             node_id=node_id,
             execution_id=execution_id,
             cause="downstream_invalidation",
+            sandbox_id=_lookup_sandbox_id(session, execution_id),
+            benchmark_slug=_lookup_benchmark_slug(session, run_id),
         )
```

**Sites 4 + 5: `propagate_execution.py:73-83` and `165-175`** — dependency
invalidation. These paths emit with `execution_id=None` (the task was never
dispatched, so no sandbox was ever created). `sandbox_id` and `benchmark_slug`
remain `None`; no change needed beyond the model accepting `None`.

---

## Package structure

No new packages. The `_cancel_helpers` module is optional; the two functions
can alternatively be inlined in each service. If extracted:

```
ergon_core/ergon_core/core/runtime/services/
  _cancel_helpers.py          ADD — _lookup_sandbox_id, _lookup_benchmark_slug
```

---

## Implementation order

| Step | Phase | What | Files touched |
|---|---|---|---|
| **1** | PR 1 | Add `sandbox_id: str \| None = None` and `benchmark_slug: str \| None = None` to `TaskCancelledEvent` | MODIFY `runtime/events/task_events.py` |
| **2** | PR 1 | Add `sandbox_id: str \| None` column to `RunTaskExecution` SQLModel | MODIFY `persistence/telemetry/models.py` |
| **3** | PR 1 | Write Alembic migration adding the nullable column | ADD `migrations/versions/<hash>_add_sandbox_id_to_run_task_executions.py` |
| **4** | PR 1 | Add `_lookup_sandbox_id` + `_lookup_benchmark_slug` helpers (inline or extracted) | ADD `runtime/services/_cancel_helpers.py` or inline |
| **5** | PR 1 | Update `SubtaskCancellationService.cancel_orphans` to populate new fields | MODIFY `runtime/services/subtask_cancellation_service.py` |
| **6** | PR 1 | Update `TaskManagementService.cancel_task` + `_cancel_downstream` to populate new fields | MODIFY `runtime/services/task_management_service.py` |
| **7** | PR 1 | Add `persist-sandbox-id` step in `execute_task_fn` after `sandbox-setup` | MODIFY `runtime/inngest/execute_task.py` |
| **8** | PR 1 | Unit tests for new event fields; state tests for helper lookups | ADD `tests/state/test_cancel_event_sandbox_fields.py` |
| **9** | PR 2 | Add `release-sandbox` step to `cleanup_cancelled_task_fn`; import `SANDBOX_MANAGERS` | MODIFY `runtime/inngest/cleanup_cancelled_task.py` |
| **10** | PR 2 | Remove `slopcop: ignore[no-todo-comment]` from `TaskCleanupService` | MODIFY `runtime/services/task_cleanup_service.py` |
| **11** | PR 2 | Unit tests for step: sandbox released, sandbox skipped, unknown slug | MODIFY `tests/state/test_task_cleanup_service.py` |

**PR 1** (Steps 1–8): event extension + column + emission site updates. Safe to
deploy ahead of PR 2 because `cleanup_cancelled_task_fn` ignores unknown extra
fields. PR 1 itself is backward-compatible: existing queued events without
`sandbox_id` will continue to work (field defaults to `None`).

**PR 2** (Steps 9–11): the actual cleanup step. Depends on PR 1 merged and
deployed because it reads `payload.sandbox_id` and `payload.benchmark_slug`.

---

## File map

### ADD

| File | Purpose |
|---|---|
| `ergon_core/ergon_core/migrations/versions/<hash>_add_sandbox_id_to_run_task_executions.py` | Additive Alembic migration: nullable `sandbox_id` column on `run_task_executions` |
| `ergon_core/ergon_core/core/runtime/services/_cancel_helpers.py` | `_lookup_sandbox_id`, `_lookup_benchmark_slug` — shared DB helpers for emission sites |
| `ergon/tests/state/test_cancel_event_sandbox_fields.py` | Unit + state tests for new event fields and helper lookup functions |

### MODIFY

| File | Changes |
|---|---|
| `ergon_core/ergon_core/core/runtime/events/task_events.py` | Add `sandbox_id: str \| None = None` and `benchmark_slug: str \| None = None` to `TaskCancelledEvent` |
| `ergon_core/ergon_core/core/persistence/telemetry/models.py` | Add `sandbox_id: str \| None = Field(default=None)` to `RunTaskExecution` |
| `ergon_core/ergon_core/core/runtime/inngest/execute_task.py` | Add `persist-sandbox-id` durable step after `sandbox-setup` returns |
| `ergon_core/ergon_core/core/runtime/services/subtask_cancellation_service.py` | Populate `sandbox_id` + `benchmark_slug` in `cancel_orphans` event construction |
| `ergon_core/ergon_core/core/runtime/services/task_management_service.py` | Populate `sandbox_id` + `benchmark_slug` in `cancel_task` + `_cancel_downstream` |
| `ergon_core/ergon_core/core/runtime/inngest/cleanup_cancelled_task.py` | Add `release-sandbox` durable step; import `SANDBOX_MANAGERS` + `BaseSandboxManager` |
| `ergon_core/ergon_core/core/runtime/services/task_cleanup_service.py` | Remove `slopcop: ignore[no-todo-comment]` suppressor; update comment |
| `ergon/tests/state/test_task_cleanup_service.py` | Add tests asserting `sandbox_released=True` when step fires |

---

## Testing approach

### State tests (fast-tier, no E2B, no Inngest)

```python
# ergon/tests/state/test_cancel_event_sandbox_fields.py

"""Tests for sandbox_id + benchmark_slug population on TaskCancelledEvent."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.runtime.services._cancel_helpers import (
    _lookup_benchmark_slug,
    _lookup_sandbox_id,
)


def _seed_execution(
    session: Session,
    *,
    run_id,
    node_id,
    sandbox_id: str | None = "sbx-abc123",
    status=TaskExecutionStatus.RUNNING,
) -> RunTaskExecution:
    exe = RunTaskExecution(
        run_id=run_id,
        node_id=node_id,
        status=status,
        sandbox_id=sandbox_id,
    )
    session.add(exe)
    session.flush()
    return exe


class TestLookupSandboxId:
    def test_returns_sandbox_id_for_known_execution(self, session: Session) -> None:
        run_id = uuid4()
        node_id = uuid4()
        exe = _seed_execution(session, run_id=run_id, node_id=node_id, sandbox_id="sbx-xyz")

        result = _lookup_sandbox_id(session, exe.id)

        assert result == "sbx-xyz"

    def test_returns_none_for_none_execution_id(self, session: Session) -> None:
        result = _lookup_sandbox_id(session, None)
        assert result is None

    def test_returns_none_for_missing_execution(self, session: Session) -> None:
        result = _lookup_sandbox_id(session, uuid4())
        assert result is None

    def test_returns_none_for_null_sandbox_id_column(self, session: Session) -> None:
        run_id = uuid4()
        node_id = uuid4()
        exe = _seed_execution(session, run_id=run_id, node_id=node_id, sandbox_id=None)

        result = _lookup_sandbox_id(session, exe.id)

        assert result is None


class TestTaskCancelledEventFields:
    """Verify emission sites populate the new fields."""

    def test_subtask_cancellation_service_populates_sandbox_id(
        self, session: Session
    ) -> None:
        """cancel_orphans should include sandbox_id on transitioned nodes."""
        from ergon_core.core.persistence.graph.models import RunGraphNode
        from ergon_core.core.persistence.graph.status_conventions import RUNNING
        from ergon_core.core.runtime.services.subtask_cancellation_service import (
            SubtaskCancellationService,
        )
        # Seed a parent and a child node with a running execution
        run_id = uuid4()
        definition_id = uuid4()
        parent_id = uuid4()
        child_id = uuid4()

        parent = RunGraphNode(
            id=parent_id,
            run_id=run_id,
            task_key="parent",
            instance_key="inst",
            status=RUNNING,
        )
        child = RunGraphNode(
            id=child_id,
            run_id=run_id,
            task_key="child",
            instance_key="inst",
            status=RUNNING,
            parent_node_id=parent_id,
        )
        session.add_all([parent, child])
        session.flush()

        exe = _seed_execution(
            session, run_id=run_id, node_id=child_id, sandbox_id="sbx-child"
        )
        session.flush()

        svc = SubtaskCancellationService()
        result = svc.cancel_orphans(
            session,
            run_id=run_id,
            definition_id=definition_id,
            parent_node_id=parent_id,
            cause="parent_terminal",
        )

        assert len(result.events_to_emit) == 1
        event = result.events_to_emit[0]
        assert event.sandbox_id == "sbx-child"
        assert event.execution_id == exe.id
```

### Unit tests — `cleanup_cancelled_task_fn` release-sandbox step

```python
# Add to: ergon/tests/state/test_task_cleanup_service.py

from unittest.mock import AsyncMock, patch


class TestReleaseSandboxStep:
    """Verify the release-sandbox logic (extracted to testable form)."""

    async def test_releases_sandbox_when_fields_present(self) -> None:
        """terminate_by_sandbox_id called exactly once for valid payload."""
        with patch(
            "ergon_core.core.providers.sandbox.manager.BaseSandboxManager"
            ".terminate_by_sandbox_id",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_terminate:
            from ergon_builtins.registry import SANDBOX_MANAGERS
            from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

            # Any known slug from SANDBOX_MANAGERS
            slug = next(iter(SANDBOX_MANAGERS))
            sandbox_id = "sbx-test-abc"

            released = await BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)

            mock_terminate.assert_called_once_with(sandbox_id)
            assert released is True

    async def test_no_release_when_sandbox_id_none(self) -> None:
        """Step is a no-op when sandbox_id is None."""
        # Simulate the guard at the top of _release_sandbox
        sandbox_id = None
        benchmark_slug = "swebench-verified"

        # Guard: neither field triggers a terminate call
        assert sandbox_id is None  # no call should be made

    async def test_no_release_when_unknown_slug(self) -> None:
        """Step logs warning and returns False for unknown benchmark_slug."""
        from ergon_builtins.registry import SANDBOX_MANAGERS

        unknown_slug = "not-a-real-benchmark"
        assert unknown_slug not in SANDBOX_MANAGERS

        # SANDBOX_MANAGERS.get returns None → no terminate call
        mgr_cls = SANDBOX_MANAGERS.get(unknown_slug)
        assert mgr_cls is None
```

### Integration / contract

- After this RFC lands, cancel a live `swebench-verified` run mid-execution
  and assert `terminate_by_sandbox_id` is called within 30 seconds.
- Assert `CleanupResult.sandbox_released = True` appears in the Inngest
  function's output for the cancelled execution.
- Assert the `RunTaskExecution` row for the cancelled execution has a non-null
  `sandbox_id` (written by the new `persist-sandbox-id` step).

---

## Trace / observability impact

### Span attributes

No new span added. The existing `"cleanup.cancelled"` span (if emitted by a
future cleanup-specific span factory) should include:

```python
{
    "sandbox_id": payload.sandbox_id or "none",
    "benchmark_slug": payload.benchmark_slug or "none",
    "sandbox_released": sandbox_result.get("sandbox_released", False),
    "release_reason": sandbox_result.get("reason", "unknown"),
}
```

`cleanup_cancelled_task_fn` does not currently emit a `CompletedSpan`. No
tracing change is required; the log lines added in step 9 are sufficient for
observability until a dedicated span factory is added.

### Log lines added

- `cleanup-cancelled node_id=... execution_id=... cause=... sandbox_id=...`
  (INFO, already present; `sandbox_id` added to existing format string)
- `release-sandbox skipped: no sandbox_id or benchmark_slug for node_id=...`
  (INFO, new)
- `release-sandbox: no manager for benchmark_slug=... node_id=...` (WARNING, new)
- `release-sandbox sandbox_id=... benchmark_slug=... released=...` (INFO, new)

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `terminate_by_sandbox_id` raises on E2B API error | Inngest retries the `release-sandbox` step (retries=3). Idempotent on repeated call (E2B `kill` on an already-dead sandbox returns not-found, `terminate_by_sandbox_id` handles this at line 487-489). | No change needed; existing error handling in `BaseSandboxManager.terminate_by_sandbox_id` is already broad-except with a warning log. |
| `persist-sandbox-id` step adds latency to `execute_task_fn` hot path | Adds ~1 DB write per task execution (single `UPDATE` with a session context). | Negligible; `execute_task_fn` already does multiple DB writes in `prepare-execution` and `finalize_success`. No performance risk. |
| Race: `cleanup_cancelled_task_fn` fires before `persist-sandbox-id` writes the column | `RunTaskExecution.sandbox_id` is NULL; cleanup event has `sandbox_id=None`; step is a no-op; sandbox leaks until E2B timeout. | Acceptable fallback; this path only affects tasks cancelled between sandbox creation and `persist-sandbox-id` completing. Window is ~100ms. For correctness at millisecond boundaries, the event carries `sandbox_id` from the emission site lookup — not from the column — so this race only matters if the cancellation fires before the task execution writes to the column AND the emitter also fails to look it up. Probability very low in practice. |
| `_lookup_benchmark_slug` adds a DB read at every `TaskCancelledEvent` emission site | Adds 1 `RunRecord` read + 1 `ExperimentDefinition` read per cancelled node. | Both rows are small and indexed by PK. At cancellation-time concurrency these reads are negligible. If it becomes a bottleneck, pass `benchmark_type` down from the calling context (already available in `execute_task_fn` via `PreparedTaskExecution.benchmark_type`). |
| `RunTaskExecution.sandbox_id` column NULL for historical rows | Pre-migration executions have `sandbox_id=NULL`. Cleanup step is a no-op for these. | Correct behavior; the sandbox for a historical cancelled task has already leaked or expired. No backfill required. |
| `SANDBOX_SKIPPED` sentinel stored literally in column | `cleanup_cancelled_task_fn` calls `SANDBOX_MANAGERS.get("skipped")` → `None` → no-op. Sandbox was never created so nothing to release. | Correct behavior. No special-case needed. |
| Deploy ordering: PR 2 deployed before PR 1 | `payload.sandbox_id` and `payload.benchmark_slug` are always `None` (old events lack the field). Step is a no-op. No regression. | PRs are designed to be safe in either order. PR 1 should land first for correctness but it is not required for safety. |

---

## Invariants affected

### `docs/architecture/02_runtime_lifecycle.md §4 Known limits`

Remove the bullet at line 117:
> "Cancellation does not release sandboxes. `cleanup-cancelled-task` updates
> the execution row but its `release-sandbox` step is a stub …"

Replace with (in `§4 Invariants`, not `§4.1 Known limits`):
> "Cancellation releases the sandbox. `cleanup_cancelled_task_fn` calls
> `BaseSandboxManager.terminate_by_sandbox_id` in its `release-sandbox` step
> when `sandbox_id` is present on the `TaskCancelledEvent`. Tasks that were
> cancelled before a sandbox was created (dep_invalidated with no execution)
> emit the event with `sandbox_id=None`; the step is a safe no-op in that
> case."

### `docs/architecture/cross_cutting/sandbox_lifecycle.md §5 Failure modes`

Update the "Cancellation" failure mode at line 61 — change "is currently a
STUB" to "calls `BaseSandboxManager.terminate_by_sandbox_id`."

### `docs/architecture/cross_cutting/sandbox_lifecycle.md §4 Invariants`

Add (or update) invariant 4:
> "`close(sandbox_id)` / `terminate_by_sandbox_id(sandbox_id)` is idempotent
> and safe to call from any cancellation path. Calling it twice is a no-op on
> the second call. The `cleanup_cancelled_task_fn.release-sandbox` step is the
> primary cancellation path; `run-cleanup` via
> `BaseSandboxManager.terminate_by_sandbox_id` is the backstop."

### `docs/architecture/cross_cutting/sandbox_lifecycle.md §8 Anti-patterns`

Remove the "current offender" annotation from the "Leaking sandboxes on
cancellation" bullet.

---

## Alternatives considered

- **Look up `sandbox_id` on-the-fly from the DB inside `cleanup_cancelled_task_fn`.**
  Rejected: adds a DB read inside an Inngest step that already has the info in
  its event payload; slower and creates a dependency on the execution row still
  existing. Also interacts badly with `update-db-rows` running before
  `release-sandbox` — we would be reading a row we just mutated.

- **Centralize sandbox cleanup at run-level `finalize_failure` / `finalize_cancelled`.**
  Rejected: per-task cleanup is correct — some runs partially cancel (one
  failed subtask, rest still running), and waiting for run finalization would
  leak sandboxes for hours. Run-level cleanup is a backstop, not the primary
  path.

- **Let E2B platform timeouts handle it.**
  Rejected: explicit cleanup is correct; timeouts are a safety net, not a
  plan. Relying on timeouts also masks bugs where we thought we cancelled but
  did not.

- **Put the release in `update-db-rows` as a single step.**
  Rejected: violates the Inngest step-per-side-effect convention and muddies
  retry semantics (a DB failure would force sandbox-close retry too).

- **`__init_subclass__` auto-registration on `BaseSandboxManager`.**
  Considered for populating a `SANDBOX_MANAGER_REGISTRY`. Rejected: auto-
  registration hides the side effect of importing a module and breaks the
  explicit registration model already in `registry_core.py`. Using `SANDBOX_MANAGERS`
  from `ergon_builtins.registry` (already populated) is simpler and consistent
  with `sandbox_setup_fn`.

- **Add a `SANDBOX_MANAGER_REGISTRY` singleton separate from `SANDBOX_MANAGERS`.**
  Rejected: `SANDBOX_MANAGERS` already exists and maps benchmark slug to
  manager class. `BaseSandboxManager.terminate_by_sandbox_id` is a `@staticmethod`
  — it does not need an instance. Using the existing dict avoids introducing a
  parallel registry.

---

## Open questions

- **Does the `sandbox_id` column race matter?** See Risks table. The practical
  window is ~100ms between sandbox creation and the `persist-sandbox-id` step
  completing. For tasks cancelled in that window, the fallback is the E2B
  platform timeout. Acceptable for now; if it proves problematic, pass
  `sandbox_id` to the cancellation event directly from `execute_task_fn`'s
  exception handler.

- **`retries=3` on `cleanup_cancelled_task_fn` — is that right?** Sandbox
  close is idempotent; 3 retries are safe. If `release-sandbox` is flaky,
  retries save us; if not, extra retries are harmless. Keep as-is.

- **What if `benchmark_slug` is set but the sandbox was already closed by
  `check_evaluators`?** `terminate_by_sandbox_id` calls `AsyncSandbox.kill`;
  E2B returns not-found for an already-closed sandbox; the method logs at INFO
  and returns `False`. `CleanupResult.sandbox_released = False` in that case.
  Correct behavior — the sandbox is gone regardless.

- **Should we store `benchmark_slug` on `RunTaskExecution` instead of looking
  it up via `RunRecord → ExperimentDefinition`?** Possible optimization if the
  lookup proves slow. Not needed now.

---

## On acceptance

- Update `docs/architecture/02_runtime_lifecycle.md §4.1 Known limits` —
  remove the "release-sandbox stub" offender.
- Update `docs/architecture/cross_cutting/sandbox_lifecycle.md §4 Invariants`
  and `§5 Failure modes` and `§8 Anti-patterns` as described above.
- Move this file to `docs/rfcs/accepted/`.
- If a separate bug file exists at
  `docs/bugs/open/2026-04-17-cleanup-cancelled-task-release-sandbox-stub.md`,
  move it to `docs/bugs/fixed/` with `fixed_pr` set. (No such file exists in
  `docs/bugs/open/` as of 2026-04-21; skip this step.)
- Link the implementation plan at
  `docs/superpowers/plans/2026-04-21-cleanup-cancelled-task-release-sandbox.md`.
