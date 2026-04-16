# Subtask Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured subtask containment, cancellation cascading, and dependency edges to Ergon's dynamic delegation system, enabling DAG-shaped subtask plans and bounded compute.

**Architecture:** Containment is stored on `RunGraphNode` (`parent_node_id` + `level`). Edges become pure dependencies. `ABANDONED` is replaced by `CANCELLED` everywhere. When a parent reaches terminal, an Inngest-driven cascade cancels all live descendants. New toolkit provides `add_subtask`, `plan_subtasks`, `cancel_task`, `refine_task`, `list_subtasks`, `get_subtask`, and sandboxed `bash`.

**Tech Stack:** Python 3.13, SQLModel, Alembic, Inngest (>=0.3.0), Pydantic v2, pydantic-ai, PostgreSQL

**Decisions (from RFC open questions):**
- Q6 (in-flight runs): Drain runs before deploy. Migration is offline-only.
- Q8 (toolkit rename): Delete `task_management_toolkit.py` entirely. No shim/re-export.
- Q9 (multi-trigger): Keep three separate Inngest functions (SDK 0.3 doesn't support `triggers=[]` list cleanly).

**Coding standard (§4.7):** Every new class and public method must include a docstring explaining *why* the design choice was made. Class docstrings state why the class exists as a separate unit. Method docstrings explain non-obvious design choices. Copy the docstrings from the RFC code blocks verbatim — they were reviewed and approved.

**Reference:** Full spec at `ergon_paper_plans/roadmap/code/C2_dynamic-delegation/SUBTASK_LIFECYCLE_RFC.md` (branch `feature/subtask-lifecycle-rfc`). Extract to /tmp if needed: `git -C /path/to/ergon_paper_plans show feature/subtask-lifecycle-rfc:roadmap/code/C2_dynamic-delegation/SUBTASK_LIFECYCLE_RFC.md > /tmp/RFC.md`

**Branch:** `feature/type-tightening-prep` on `ergon` repo (4 prep commits already landed: UUID NewType aliases in `shared/types.py`, NodeStatus/EdgeStatus Literals in `status_conventions.py`, keyword-only UUID args in `graph_repository.py`, typed aliases on graph/task DTOs).

---

## File Map

### New files

| Path | Purpose | Phase |
|------|---------|-------|
| `ergon_core/migrations/versions/<rev>_add_containment_and_cancelled.py` | Alembic migration: add `parent_node_id` + `level`, backfill, delete delegation edges, rename ABANDONED→CANCELLED | 0 |
| `ergon_core/ergon_core/core/runtime/services/subtask_cancellation_service.py` | Cascade-cancel orphaned children (§7.2) | 2 |
| `ergon_core/ergon_core/core/runtime/services/subtask_cancellation_dto.py` | `CancelOrphansResult` | 2 |
| `ergon_core/ergon_core/core/runtime/services/task_cleanup_service.py` | Sandbox/execution/context teardown (§7.3) | 2 |
| `ergon_core/ergon_core/core/runtime/services/task_cleanup_dto.py` | `CleanupResult` | 2 |
| `ergon_core/ergon_core/core/runtime/services/task_inspection_service.py` | Read-only listing/snapshotting (§7.4) | 2 |
| `ergon_core/ergon_core/core/runtime/services/task_inspection_dto.py` | `SubtaskInfo`, `SubtaskStatus` | 2 |
| `ergon_core/ergon_core/core/runtime/inngest/cancel_orphan_subtasks.py` | Three `cancel_orphans_on_*_fn` Inngest functions (§9.1) | 3 |
| `ergon_core/ergon_core/core/runtime/inngest/cleanup_cancelled_task.py` | `cleanup_cancelled_task_fn` (§9.2) | 3 |
| `ergon_builtins/ergon_builtins/tools/subtask_lifecycle_toolkit.py` | New toolkit replacing `TaskManagementToolkit` (§8) | 4 |
| `ergon_builtins/ergon_builtins/tools/bash_sandbox_tool.py` | Sandboxed `bash` tool (§8) | 4 |
| `tests/state/test_subtask_cancellation_service.py` | Unit: cascade cancel | 2 |
| `tests/state/test_task_inspection_service.py` | Unit: listing, ordering, excerpt | 2 |
| `tests/state/test_plan_subtasks.py` | Unit: plan_subtasks validation + execution | 2 |
| `tests/state/test_conditional_status_writes.py` | Unit: only_if_not_terminal guard | 1 |
| `tests/state/test_task_cleanup_service.py` | Unit: idempotent cleanup, `execution_id=None` path | 2 |

### Modified files

| Path | Change | Phase |
|------|--------|-------|
| `ergon_core/ergon_core/core/persistence/graph/models.py` | Add `parent_node_id` + `level` to `RunGraphNode` | 0 |
| `ergon_core/ergon_core/core/persistence/graph/status_conventions.py` | `ABANDONED`→`CANCELLED`, `EDGE_ACTIVE`→remove, add `EDGE_INVALIDATED` | 0 |
| `ergon_core/ergon_core/core/persistence/shared/enums.py` | Add `TaskExecutionStatus.CANCELLED` | 0 |
| `ergon_core/ergon_core/core/runtime/events/task_events.py` | Add `TaskCancelledEvent` + `CancelCause` | 0 |
| `ergon_core/ergon_core/core/runtime/inngest_client.py` | Add `TASK_CANCEL` export | 1 |
| `ergon_core/ergon_core/core/runtime/services/graph_repository.py` | `update_node_status` returns bool + `only_if_not_terminal`; `add_node` grows `parent_node_id`/`level` | 1 |
| `ergon_core/ergon_core/core/runtime/errors/delegation_errors.py` | Add `CycleDetectedError`, `DuplicateLocalKeyError`, `UnknownLocalKeyError` | 2 |
| `ergon_core/ergon_core/core/runtime/services/task_management_service.py` | Rewrite: `add_task`→`add_subtask`, `abandon_task`→`cancel_task`, add `plan_subtasks` | 2 |
| `ergon_core/ergon_core/core/runtime/services/task_management_dto.py` | Replace all DTOs with RFC §6.1 versions | 2 |
| `ergon_core/ergon_core/core/runtime/execution/propagation.py` | Relaxed `is_workflow_complete`; propagation returns `(ready, invalidated)` | 3 |
| `ergon_core/ergon_core/core/runtime/inngest/execute_task.py` | Add `TASK_CANCEL` to cancel list | 3 |
| `ergon_core/ergon_core/core/runtime/inngest/propagate_execution.py` | Emit `task/cancelled(cause="dep_invalidated")` for invalidated targets | 3 |
| `ergon_core/ergon_core/core/api/runs.py` | Rewrite `_build_task_map` for stored containment | 3 |
| `ergon_core/ergon_core/core/persistence/queries.py` | `list_children_of` uses `parent_node_id` instead of edge traversal | 3 |
| `ergon_builtins/ergon_builtins/tools/graph_toolkit.py` | `list_child_resources`/`list_descendant_resources` use `parent_node_id` query | 4 |
| `ergon_builtins/ergon_builtins/workers/research_rubrics/manager_worker.py` | Switch to `SubtaskLifecycleToolkit`, update system prompt | 4 |
| `ergon_builtins/ergon_builtins/workers/baselines/manager_researcher_worker.py` | Use `build_subtask_lifecycle_tools` | 4 |
| `ergon_builtins/ergon_builtins/benchmarks/delegation_smoke/benchmark.py` | Drive new toolkit, cover cancel-cascade in smoke | 4 |
| `ergon_core/ergon_core/core/runtime/services/orchestration_dto.py` | `PropagateTaskCompletionCommand` grows `terminal_status` + return grows `invalidated_targets` | 3 |
| `ergon_core/ergon_core/core/dashboard/emitter.py` | Handle `TaskCancelledEvent` — emit `node.cancelled` dashboard mutation | 5 |

### Deleted files

| Path | Reason | Phase |
|------|--------|-------|
| `ergon_builtins/ergon_builtins/tools/task_management_toolkit.py` | Replaced by `subtask_lifecycle_toolkit.py`. No backwards compat. | 4 |

---

## Phase 0: Schema + Status Vocabulary

### Task 0.1: Add containment columns to RunGraphNode model

**Files:**
- Modify: `ergon_core/ergon_core/core/persistence/graph/models.py`
- Test: `pnpm run check:be:lint`

- [ ] **Step 1: Read the current RunGraphNode model**

```bash
cat -n ergon_core/ergon_core/core/persistence/graph/models.py
```

- [ ] **Step 2: Add parent_node_id and level fields**

Add after the `assigned_worker_key` field (before `created_at`):

```python
    # Containment: self-referential FK to the spawning node.
    # NULL for definition-seeded roots; set for every dynamic subtask.
    # Stored (not derived) so a single SELECT on run_graph_nodes gives
    # a fully legible hierarchy without joins or edge traversal.
    parent_node_id: UUID | None = Field(
        default=None,
        foreign_key="run_graph_nodes.id",
        index=True,
    )

    # Depth in the containment tree. 0 for roots, parent.level + 1
    # for dynamic subtasks. Stored for debuggability and to avoid
    # N+1 level computation at query/rendering time.
    level: int = Field(default=0)
```

- [ ] **Step 3: Run lint**

```bash
pnpm run check:be:lint
```

Expected: All checks passed

- [ ] **Step 4: Run tests**

```bash
pnpm run test:be:fast
```

Expected: All tests pass (new fields have defaults, no schema enforcement in SQLite tests)

- [ ] **Step 5: Commit**

```bash
git add ergon_core/ergon_core/core/persistence/graph/models.py
git commit -m "feat(schema): add parent_node_id and level to RunGraphNode

Containment columns for the subtask hierarchy. parent_node_id is a
self-referential FK (NULL for roots). level is the depth in the tree
(0 for roots). Both are stored, not derived, for debuggability and
to avoid N+1 queries on the FE rendering path."
```

### Task 0.2: Replace ABANDONED with CANCELLED in status vocabulary

**Files:**
- Modify: `ergon_core/ergon_core/core/persistence/graph/status_conventions.py`
- Modify: `ergon_core/ergon_core/core/persistence/shared/enums.py`
- Verify: all callers of `ABANDONED` constant

- [ ] **Step 1: Update status_conventions.py**

Replace the full file content:

```python
"""Conventional status values for RunGraphNode and RunGraphEdge.

The graph layer accepts any string at the DB level -- these are not
enforced by the schema. They are the values used by the core runtime,
propagation, and dynamic delegation logic. Experiment layers may add
domain-specific statuses without changing core code.

The Literal type aliases below are for use in service signatures, DTOs,
and function annotations. They catch typos at type-check time without
constraining the DB column.
"""

from typing import Literal

# ── Node status ───────────────────────────────────────────────────
PENDING = "pending"
READY = "ready"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"

TERMINAL_STATUSES = frozenset({COMPLETED, FAILED, CANCELLED})

NodeStatus = Literal["pending", "ready", "running", "completed", "failed", "cancelled"]

# ── Edge status ───────────────────────────────────────────────────
# Edges are pure dependency relations (containment lives on the node).
# "active" is removed — delegation edges no longer exist.
EDGE_PENDING = "pending"
EDGE_SATISFIED = "satisfied"
EDGE_INVALIDATED = "invalidated"

EdgeStatus = Literal["pending", "satisfied", "invalidated"]
```

- [ ] **Step 2: Add CANCELLED to TaskExecutionStatus enum**

In `ergon_core/ergon_core/core/persistence/shared/enums.py`, add to the `TaskExecutionStatus` StrEnum:

```python
    CANCELLED = "cancelled"
```

- [ ] **Step 3: Find and fix all references to ABANDONED**

```bash
rg -n "ABANDONED\b|\"abandoned\"|'abandoned'" ergon_core/ ergon_builtins/ tests/
```

For each hit:
- Replace `ABANDONED` symbol with `CANCELLED`
- Replace `"abandoned"` string literal with `"cancelled"`
- Replace `EDGE_ACTIVE` with `EDGE_SATISFIED` where it's used for dependency edges, or remove if it was delegation-only
- Replace `EDGE_ABANDONED` with `EDGE_INVALIDATED`

Key files to check:
- `ergon_core/ergon_core/core/runtime/execution/propagation.py`
- `ergon_core/ergon_core/core/runtime/services/task_management_service.py`
- `ergon_core/ergon_core/core/runtime/services/task_management_dto.py` (AbandonTaskCommand, AbandonTaskResult — leave renaming to Phase 2)
- `tests/state/*.py`

**Important:** In this phase, only rename the status values. Do NOT rename methods/DTOs yet (that's Phase 2). For `abandon_task` and `AbandonTaskCommand`, change internal status writes from `ABANDONED` to `CANCELLED` but keep the method/class names.

- [ ] **Step 4: Run tests**

```bash
pnpm run test:be:fast
```

Expected: All pass. If any test asserts `"abandoned"`, update assertion to `"cancelled"`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(status): replace ABANDONED with CANCELLED across codebase

Single non-success terminal status. ABANDONED is gone from all code
and test fixtures. Edge vocabulary narrowed: EDGE_ACTIVE removed
(delegation edges eliminated), EDGE_INVALIDATED added for dep-failure
path. TaskExecutionStatus gains CANCELLED value."
```

### Task 0.3: Add TaskCancelledEvent

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/events/task_events.py`
- Test: lint + type check

- [ ] **Step 1: Read current task_events.py**

```bash
cat -n ergon_core/ergon_core/core/runtime/events/task_events.py
```

- [ ] **Step 2: Add CancelCause literal and TaskCancelledEvent class**

Append to the file (after existing event classes):

```python
# ── Cancel cause ──────────────────────────────────────────────────

CancelCause = Literal[
    "manager_decision",
    "parent_terminal",
    "dep_invalidated",
    "run_cancelled",
]


class TaskCancelledEvent(BaseModel):
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

    model_config = {"frozen": True}
```

Add `Literal` to the typing import if not already present. Add `ClassVar` import if not already present. Check existing events for the import pattern and match it.

- [ ] **Step 3: Run lint + tests**

```bash
pnpm run check:be:lint && pnpm run test:be:fast
```

Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add ergon_core/ergon_core/core/runtime/events/task_events.py
git commit -m "feat(events): add TaskCancelledEvent and CancelCause

New event emitted whenever a node transitions to CANCELLED. Carries
cause (manager_decision, parent_terminal, dep_invalidated, run_cancelled)
for audit logging and trajectory analysis."
```

### Task 0.4: Create Alembic migration

**Files:**
- Create: `ergon_core/migrations/versions/<auto>_add_containment_and_cancelled.py`

- [ ] **Step 1: Generate migration skeleton**

```bash
cd ergon_core && uv run alembic revision --autogenerate -m "add_containment_and_cancelled"
```

- [ ] **Step 2: Edit the migration**

Replace the upgrade function body with the migration from RFC §5.1.2:

```python
def upgrade() -> None:
    # 1. Add parent_node_id column + FK + index.
    op.add_column(
        "run_graph_nodes",
        sa.Column("parent_node_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_run_graph_nodes_parent",
        "run_graph_nodes", "run_graph_nodes",
        ["parent_node_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_run_graph_nodes_parent_node_id",
        "run_graph_nodes", ["parent_node_id"],
    )

    # 2. Add level column (default 0 = root).
    op.add_column(
        "run_graph_nodes",
        sa.Column("level", sa.Integer(), server_default="0", nullable=False),
    )

    # 3. Backfill: old delegation edges (status='active') become parent_node_id
    #    on their target node.
    op.execute("""
        UPDATE run_graph_nodes tgt
           SET parent_node_id = e.source_node_id
          FROM run_graph_edges e
         WHERE e.target_node_id = tgt.id
           AND e.status = 'active'
    """)

    # 4. Recursive level backfill.
    op.execute("""
        WITH RECURSIVE tree AS (
            SELECT id, 0 AS depth
              FROM run_graph_nodes
             WHERE parent_node_id IS NULL
            UNION ALL
            SELECT n.id, t.depth + 1
              FROM run_graph_nodes n
              JOIN tree t ON n.parent_node_id = t.id
        )
        UPDATE run_graph_nodes
           SET level = tree.depth
          FROM tree
         WHERE run_graph_nodes.id = tree.id
    """)

    # 5. Delete delegation edges — containment now lives on the node.
    op.execute("DELETE FROM run_graph_edges WHERE status = 'active'")

    # 6. Status vocabulary: ABANDONED -> CANCELLED.
    op.execute("UPDATE run_graph_nodes SET status = 'cancelled' WHERE status = 'abandoned'")
    op.execute("UPDATE run_graph_edges SET status = 'invalidated' WHERE status = 'abandoned'")


def downgrade() -> None:
    # Downgrade is lossy: delegation edges cannot be reconstructed.
    op.execute("UPDATE run_graph_nodes SET status = 'abandoned' WHERE status = 'cancelled'")
    op.execute("UPDATE run_graph_edges SET status = 'abandoned' WHERE status = 'invalidated'")
    op.drop_index("ix_run_graph_nodes_parent_node_id")
    op.drop_constraint("fk_run_graph_nodes_parent", "run_graph_nodes")
    op.drop_column("run_graph_nodes", "level")
    op.drop_column("run_graph_nodes", "parent_node_id")
```

- [ ] **Step 3: Commit**

```bash
git add ergon_core/migrations/
git commit -m "feat(migration): add containment columns and migrate ABANDONED→CANCELLED

Adds parent_node_id (self-FK, indexed) and level (int) to
run_graph_nodes. Backfills from delegation edges via recursive CTE.
Deletes delegation edges. Renames abandoned→cancelled in both
nodes and edges."
```

---

## Phase 1: Conditional Status Writes

### Task 1.1: Add only_if_not_terminal guard to update_node_status

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/services/graph_repository.py`
- Test: `tests/state/test_conditional_status_writes.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/state/test_conditional_status_writes.py`:

```python
"""Tests for the only_if_not_terminal conditional guard on update_node_status.

The conditional write is the single invariant that closes all race conditions
in the cascade cancellation system (RFC §4.4). Every concurrent path —
cancel vs complete, cascade vs cascade, manager cancel vs engine cascade —
resolves to "first writer wins" via this guard.
"""

from uuid import uuid4

import pytest
from sqlmodel import Session

from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    COMPLETED,
    FAILED,
    PENDING,
    RUNNING,
    TERMINAL_STATUSES,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository

META = MutationMeta(actor="test", reason="test")


class TestConditionalStatusWrites:
    def test_guard_blocks_write_on_completed_node(self, db_session: Session) -> None:
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = repo.add_node(
            db_session, run_id,
            task_key="t1", instance_key="i0", description="test",
            status=COMPLETED, meta=META,
        )
        result = repo.update_node_status(
            db_session,
            run_id=run_id, node_id=node.id, new_status=CANCELLED,
            meta=META, only_if_not_terminal=True,
        )
        assert result is False

    def test_guard_blocks_write_on_failed_node(self, db_session: Session) -> None:
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = repo.add_node(
            db_session, run_id,
            task_key="t1", instance_key="i0", description="test",
            status=FAILED, meta=META,
        )
        result = repo.update_node_status(
            db_session,
            run_id=run_id, node_id=node.id, new_status=CANCELLED,
            meta=META, only_if_not_terminal=True,
        )
        assert result is False

    def test_guard_blocks_write_on_cancelled_node(self, db_session: Session) -> None:
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = repo.add_node(
            db_session, run_id,
            task_key="t1", instance_key="i0", description="test",
            status=CANCELLED, meta=META,
        )
        result = repo.update_node_status(
            db_session,
            run_id=run_id, node_id=node.id, new_status=COMPLETED,
            meta=META, only_if_not_terminal=True,
        )
        assert result is False

    def test_guard_allows_write_on_running_node(self, db_session: Session) -> None:
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = repo.add_node(
            db_session, run_id,
            task_key="t1", instance_key="i0", description="test",
            status=RUNNING, meta=META,
        )
        result = repo.update_node_status(
            db_session,
            run_id=run_id, node_id=node.id, new_status=CANCELLED,
            meta=META, only_if_not_terminal=True,
        )
        assert result is True
        refreshed = repo.get_node(db_session, run_id=run_id, node_id=node.id)
        assert refreshed.status == CANCELLED

    def test_unconditional_write_still_works(self, db_session: Session) -> None:
        """Without the guard, writes proceed even on terminal nodes."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = repo.add_node(
            db_session, run_id,
            task_key="t1", instance_key="i0", description="test",
            status=COMPLETED, meta=META,
        )
        # Default only_if_not_terminal=False: unconditional
        result = repo.update_node_status(
            db_session,
            run_id=run_id, node_id=node.id, new_status=FAILED,
            meta=META,
        )
        assert result is True

    def test_guard_does_not_emit_mutation_on_blocked_write(self, db_session: Session) -> None:
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = repo.add_node(
            db_session, run_id,
            task_key="t1", instance_key="i0", description="test",
            status=COMPLETED, meta=META,
        )
        mutations_before = repo.get_mutations(db_session, run_id)
        count_before = len(mutations_before.mutations)

        repo.update_node_status(
            db_session,
            run_id=run_id, node_id=node.id, new_status=CANCELLED,
            meta=META, only_if_not_terminal=True,
        )
        mutations_after = repo.get_mutations(db_session, run_id)
        assert len(mutations_after.mutations) == count_before
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/state/test_conditional_status_writes.py -v
```

Expected: FAIL — `update_node_status` doesn't accept `only_if_not_terminal` yet, and returns `GraphNodeDto` not `bool`.

- [ ] **Step 3: Implement conditional guard**

In `ergon_core/ergon_core/core/runtime/services/graph_repository.py`, modify `update_node_status`:

```python
    def update_node_status(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
        new_status: str,
        meta: MutationMeta,
        only_if_not_terminal: bool = False,
    ) -> bool:
        """Transition a node's status. Returns True if the write applied.

        When ``only_if_not_terminal`` is True, the write is skipped if the
        node is already in a terminal status (COMPLETED, FAILED, CANCELLED).
        This is the single invariant that closes all race conditions in the
        cascade cancellation system — concurrent paths that both attempt to
        write a terminal status resolve to "first writer wins" without
        requiring distributed locks.
        """
        node = self._get_node_row(session, run_id, node_id)

        if only_if_not_terminal and node.status in TERMINAL_STATUSES:
            return False

        old_status = node.status
        node.status = new_status
        node.updated_at = utcnow()
        session.add(node)
        session.flush()

        self._log_mutation(
            session,
            run_id,
            mutation_type="node.status_changed",
            target_type="node",
            target_id=node_id,
            meta=meta,
            old_value=NodeStatusChangedMutation(status=old_status),
            new_value=NodeStatusChangedMutation(status=new_status),
        )
        return True
```

Add `TERMINAL_STATUSES` to the imports from `status_conventions`.

**Important:** This changes the return type from `GraphNodeDto` to `bool`. All existing callers must be updated.

- [ ] **Step 4: Update all callers of update_node_status**

Search for all callers:

```bash
rg "update_node_status\(" ergon_core/ tests/ --files-with-matches
```

For each caller that was using the returned `GraphNodeDto`, update to handle `bool`. Most callers ignore the return value, so the change is usually just removing the assignment. Key files:
- `propagation.py` — `_update_task_status` and `mark_task_*` helpers
- `task_management_service.py` — `abandon_task` (still named that in this phase)
- `task_execution_service.py`
- Tests

- [ ] **Step 5: Run tests**

```bash
pnpm run test:be:fast
```

Expected: All pass including new `test_conditional_status_writes.py`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(graph_repo): add only_if_not_terminal guard to update_node_status

Returns bool (True = applied, False = blocked). This is the single
invariant closing all race conditions in cascade cancellation — 
concurrent terminal writes resolve to first-writer-wins without
distributed locks."
```

### Task 1.2: Extend add_node with parent_node_id and level

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/services/graph_repository.py`

- [ ] **Step 1: Read current add_node signature**

The current signature is:
```python
def add_node(self, session, run_id, *, task_key, instance_key, description, status, assigned_worker_key=None, meta)
```

- [ ] **Step 2: Add parent_node_id and level kwargs**

```python
    def add_node(
        self,
        session: Session,
        run_id: UUID,
        *,
        task_key: str,
        instance_key: str,
        description: str,
        status: str,
        assigned_worker_key: str | None = None,
        parent_node_id: UUID | None = None,
        level: int = 0,
        meta: MutationMeta,
    ) -> GraphNodeDto:
        """Create a graph node. Writes the containment columns directly.

        parent_node_id and level are set at creation time and never change.
        The caller (TaskManagementService) computes level = parent.level + 1.
        """
```

In the body where `RunGraphNode(...)` is constructed, add:
```python
        parent_node_id=parent_node_id,
        level=level,
```

- [ ] **Step 3: Run tests**

```bash
pnpm run test:be:fast
```

Expected: All pass (new params have defaults matching old behavior)

- [ ] **Step 4: Commit**

```bash
git add ergon_core/ergon_core/core/runtime/services/graph_repository.py
git commit -m "feat(graph_repo): add parent_node_id and level to add_node

Containment columns are set at creation time and never change.
Defaults (None, 0) match pre-existing root-node behavior."
```

### Task 1.3: Add TASK_CANCEL to inngest_client

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/inngest_client.py`

- [ ] **Step 1: Add TASK_CANCEL export**

```python
# Per-node cancel matcher. Fires on task/cancelled for this exact node_id.
# Used by execute_task_fn to drop queued or terminate in-flight invocations
# when a parent terminates or the manager explicitly cancels.
TASK_CANCEL = [
    inngest.Cancel(
        event="task/cancelled",
        if_exp="event.data.node_id == async.data.node_id",
    ),
]
```

- [ ] **Step 2: Run lint**

```bash
pnpm run check:be:lint
```

- [ ] **Step 3: Commit**

```bash
git add ergon_core/ergon_core/core/runtime/inngest_client.py
git commit -m "feat(inngest): add TASK_CANCEL per-node cancel matcher

Matches task/cancelled events by node_id. Used by execute_task_fn
to drop queued invocations or terminate in-flight workers when
their parent terminates."
```

---

## Phase 2: Services

### Task 2.1: New error classes for plan validation

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/errors/delegation_errors.py`

- [ ] **Step 1: Add new error classes**

```python
class CycleDetectedError(DelegationError):
    """Raised when plan_subtasks dependency graph contains a cycle."""

    def __init__(self, remaining_keys: list[str]) -> None:
        super().__init__(f"Cycle detected among keys: {remaining_keys}")
        self.remaining_keys = remaining_keys


class DuplicateLocalKeyError(DelegationError):
    """Raised when plan_subtasks has duplicate local_key values."""

    def __init__(self, key: str) -> None:
        super().__init__(f"Duplicate local_key: {key!r}")
        self.key = key


class UnknownLocalKeyError(DelegationError):
    """Raised when depends_on references a local_key not in the plan."""

    def __init__(self, unknown: list[str]) -> None:
        super().__init__(f"Unknown depends_on keys: {unknown}")
        self.unknown = unknown
```

- [ ] **Step 2: Run lint + tests**

```bash
pnpm run check:be:lint && pnpm run test:be:fast
```

- [ ] **Step 3: Commit**

```bash
git add ergon_core/ergon_core/core/runtime/errors/delegation_errors.py
git commit -m "feat(errors): add CycleDetectedError, DuplicateLocalKeyError, UnknownLocalKeyError

Validation errors for plan_subtasks — cycle detection via Kahn's
algorithm, duplicate local_key guard, and unknown depends_on
reference guard."
```

### Task 2.2: New DTOs for subtask lifecycle

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/services/task_management_dto.py`
- Create: `ergon_core/ergon_core/core/runtime/services/task_inspection_dto.py`
- Create: `ergon_core/ergon_core/core/runtime/services/subtask_cancellation_dto.py`
- Create: `ergon_core/ergon_core/core/runtime/services/task_cleanup_dto.py`

- [ ] **Step 1: Replace task_management_dto.py**

Replace the entire file with the RFC §6.1 DTOs. Copy verbatim from the RFC (the `AddSubtaskCommand`, `AddSubtaskResult`, `PlanSubtasksCommand`, `PlanSubtasksResult`, `SubtaskSpec`, `CancelTaskCommand`, `CancelTaskResult`, `RefineTaskCommand`, `RefineTaskResult`).

- [ ] **Step 2: Create task_inspection_dto.py**

Copy RFC §6.2 verbatim — `SubtaskInfo` and `SubtaskStatus`.

- [ ] **Step 3: Create subtask_cancellation_dto.py**

Copy RFC §6.3 first half — `CancelOrphansResult`.

- [ ] **Step 4: Create task_cleanup_dto.py**

Copy RFC §6.3 second half — `CleanupResult`.

- [ ] **Step 5: Run lint**

```bash
pnpm run check:be:lint
```

Fix any import issues (old DTOs were imported elsewhere — tests will break, that's expected at this stage).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(dto): replace task management DTOs with subtask lifecycle DTOs

AddTaskCommand→AddSubtaskCommand, AbandonTaskCommand→CancelTaskCommand.
New: PlanSubtasksCommand/Result, SubtaskSpec, SubtaskInfo, CancelOrphansResult,
CleanupResult. All frozen Pydantic v2 models with typed UUID aliases."
```

### Task 2.3: Rewrite TaskManagementService

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/services/task_management_service.py`
- Test: `tests/state/test_task_management_service.py` (update)
- Test: `tests/state/test_plan_subtasks.py` (new)

- [ ] **Step 1: Write plan_subtasks validation tests**

Create `tests/state/test_plan_subtasks.py`:

```python
"""Tests for plan_subtasks — atomic sub-DAG creation with validation.

plan_subtasks is the primary way managers express structured delegation.
It creates all nodes and edges in a single transaction, rejects cycles
via Kahn's algorithm, and only dispatches roots (nodes with no deps).
"""

from uuid import uuid4

import pytest
from sqlmodel import Session

from ergon_core.core.persistence.graph.status_conventions import PENDING
from ergon_core.core.runtime.errors.delegation_errors import (
    CycleDetectedError,
    DuplicateLocalKeyError,
    UnknownLocalKeyError,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.task_management_dto import (
    PlanSubtasksCommand,
    SubtaskSpec,
)
from ergon_core.core.runtime.services.task_management_service import TaskManagementService

META = MutationMeta(actor="test", reason="test")


def _make_parent(repo: WorkflowGraphRepository, session: Session, run_id):
    """Create a root node to serve as parent for plan_subtasks."""
    return repo.add_node(
        session, run_id,
        task_key="root", instance_key="i0", description="root",
        status="running", meta=META,
    )


class TestPlanSubtasksValidation:
    def test_rejects_duplicate_local_keys(self, db_session: Session) -> None:
        svc = TaskManagementService()
        repo = WorkflowGraphRepository()
        run_id = uuid4()
        parent = _make_parent(repo, db_session, run_id)

        with pytest.raises(DuplicateLocalKeyError):
            svc.plan_subtasks(
                db_session,
                PlanSubtasksCommand(
                    run_id=run_id,
                    parent_node_id=parent.id,
                    subtasks=[
                        SubtaskSpec(local_key="a", description="A"),
                        SubtaskSpec(local_key="a", description="A2"),
                    ],
                ),
            )

    def test_rejects_unknown_depends_on(self, db_session: Session) -> None:
        svc = TaskManagementService()
        repo = WorkflowGraphRepository()
        run_id = uuid4()
        parent = _make_parent(repo, db_session, run_id)

        with pytest.raises(UnknownLocalKeyError):
            svc.plan_subtasks(
                db_session,
                PlanSubtasksCommand(
                    run_id=run_id,
                    parent_node_id=parent.id,
                    subtasks=[
                        SubtaskSpec(local_key="a", description="A", depends_on=["nonexistent"]),
                    ],
                ),
            )

    def test_rejects_cycle(self, db_session: Session) -> None:
        svc = TaskManagementService()
        repo = WorkflowGraphRepository()
        run_id = uuid4()
        parent = _make_parent(repo, db_session, run_id)

        with pytest.raises(CycleDetectedError):
            svc.plan_subtasks(
                db_session,
                PlanSubtasksCommand(
                    run_id=run_id,
                    parent_node_id=parent.id,
                    subtasks=[
                        SubtaskSpec(local_key="a", description="A", depends_on=["b"]),
                        SubtaskSpec(local_key="b", description="B", depends_on=["a"]),
                    ],
                ),
            )

    def test_creates_nodes_and_edges_atomically(self, db_session: Session) -> None:
        svc = TaskManagementService()
        repo = WorkflowGraphRepository()
        run_id = uuid4()
        parent = _make_parent(repo, db_session, run_id)

        result = svc.plan_subtasks(
            db_session,
            PlanSubtasksCommand(
                run_id=run_id,
                parent_node_id=parent.id,
                subtasks=[
                    SubtaskSpec(local_key="t1", description="Task 1"),
                    SubtaskSpec(local_key="t2", description="Task 2", depends_on=["t1"]),
                ],
            ),
        )

        assert "t1" in result.nodes
        assert "t2" in result.nodes
        assert result.roots == ["t1"]

        # Verify nodes exist and have correct containment
        t1 = repo.get_node(db_session, run_id=run_id, node_id=result.nodes["t1"])
        assert t1.status == PENDING
        # parent_node_id check requires reading the raw model — use get_graph
        graph = repo.get_graph(db_session, run_id)
        t1_raw = next(n for n in graph.nodes if n.id == result.nodes["t1"])
        t2_raw = next(n for n in graph.nodes if n.id == result.nodes["t2"])

        # Verify edge exists from t1 → t2
        edges = repo.get_outgoing_edges(db_session, run_id=run_id, node_id=result.nodes["t1"])
        assert len(edges) == 1
        assert edges[0].target_node_id == result.nodes["t2"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/state/test_plan_subtasks.py -v
```

Expected: FAIL — `plan_subtasks` doesn't exist yet, DTOs don't match.

- [ ] **Step 3: Rewrite task_management_service.py**

Replace the service with the RFC §7.1 implementation. Key changes:
- `add_task` → `add_subtask` (with `depends_on` parameter, writes `parent_node_id` + `level`)
- `abandon_task` → `cancel_task` (emits `TaskCancelledEvent`, uses `only_if_not_terminal`)
- Add `plan_subtasks` (Kahn's algorithm for cycle detection, atomic node+edge creation)
- Add `_resolve_definition_id` (replaces external `_lookup_definition_id`)
- Add `_dispatch_task_ready` helper
- Add `_validate_plan` static method
- Add `_count_non_terminal_descendants` module-level helper
- Add `_latest_execution_id` module-level helper

Copy the implementation from RFC §7.1 verbatim (the docstrings are already reviewed).

**Note:** `_count_non_terminal_descendants` uses a recursive CTE over `parent_node_id`. `_latest_execution_id` queries the task_executions table. Both need to work with the current DB schema. Check how the existing code queries executions and adapt.

- [ ] **Step 4: Update test_task_management_service.py**

Update all imports and assertions:
- `AddTaskCommand` → `AddSubtaskCommand`
- `AbandonTaskCommand` → `CancelTaskCommand`
- `AddTaskResult` → `AddSubtaskResult`
- `AbandonTaskResult` → `CancelTaskResult`
- `add_task` → `add_subtask`
- `abandon_task` → `cancel_task`
- `"abandoned"` → `"cancelled"` in all assertions
- Update result field accesses (e.g. `edge_id` no longer on result)

- [ ] **Step 5: Run all tests**

```bash
pnpm run test:be:fast
```

Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(service): rewrite TaskManagementService with subtask lifecycle

add_task→add_subtask (with depends_on, parent_node_id+level),
abandon_task→cancel_task (emits TaskCancelledEvent, conditional write),
new plan_subtasks (atomic sub-DAG creation with Kahn's cycle detection).
definition_id resolved from run_id at dispatch time — not on command DTOs."
```

### Task 2.4: SubtaskCancellationService

**Files:**
- Create: `ergon_core/ergon_core/core/runtime/services/subtask_cancellation_service.py`
- Test: `tests/state/test_subtask_cancellation_service.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/state/test_subtask_cancellation_service.py`:

```python
"""Tests for SubtaskCancellationService — single-level cascade cancel.

This service marks non-terminal children of a parent as CANCELLED and
returns events for the caller to emit. It does NOT recurse — cascade
to grandchildren is driven by Inngest re-delivering task/cancelled.
Separated from TaskCleanupService (different concerns: state vs resources)
and from TaskManagementService (different callers: engine vs agent).
"""

from uuid import uuid4

import pytest
from sqlmodel import Session

from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    COMPLETED,
    PENDING,
    RUNNING,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.subtask_cancellation_service import (
    SubtaskCancellationService,
)

META = MutationMeta(actor="test", reason="test")


class TestCancelOrphans:
    def test_cancels_non_terminal_children(self, db_session: Session) -> None:
        repo = WorkflowGraphRepository()
        svc = SubtaskCancellationService(graph_repo=repo)
        run_id = uuid4()

        parent = repo.add_node(
            db_session, run_id, task_key="root", instance_key="i0",
            description="parent", status=COMPLETED, meta=META,
        )
        child_running = repo.add_node(
            db_session, run_id, task_key="c1", instance_key="i0",
            description="running child", status=RUNNING,
            parent_node_id=parent.id, level=1, meta=META,
        )
        child_pending = repo.add_node(
            db_session, run_id, task_key="c2", instance_key="i0",
            description="pending child", status=PENDING,
            parent_node_id=parent.id, level=1, meta=META,
        )
        child_completed = repo.add_node(
            db_session, run_id, task_key="c3", instance_key="i0",
            description="completed child", status=COMPLETED,
            parent_node_id=parent.id, level=1, meta=META,
        )

        result = svc.cancel_orphans(
            db_session,
            run_id=run_id,
            definition_id=uuid4(),
            parent_node_id=parent.id,
            cause="parent_terminal",
        )

        assert len(result.cancelled_node_ids) == 2
        assert child_running.id in result.cancelled_node_ids
        assert child_pending.id in result.cancelled_node_ids
        assert child_completed.id not in result.cancelled_node_ids
        assert len(result.events_to_emit) == 2

    def test_empty_children_is_noop(self, db_session: Session) -> None:
        repo = WorkflowGraphRepository()
        svc = SubtaskCancellationService(graph_repo=repo)
        run_id = uuid4()

        parent = repo.add_node(
            db_session, run_id, task_key="root", instance_key="i0",
            description="leaf", status=COMPLETED, meta=META,
        )

        result = svc.cancel_orphans(
            db_session,
            run_id=run_id,
            definition_id=uuid4(),
            parent_node_id=parent.id,
            cause="parent_terminal",
        )

        assert result.cancelled_node_ids == []
        assert result.events_to_emit == []

    def test_only_cancels_direct_children_not_grandchildren(self, db_session: Session) -> None:
        """Grandchildren are cancelled by Inngest re-delivering task/cancelled."""
        repo = WorkflowGraphRepository()
        svc = SubtaskCancellationService(graph_repo=repo)
        run_id = uuid4()

        root = repo.add_node(
            db_session, run_id, task_key="root", instance_key="i0",
            description="root", status=COMPLETED, meta=META,
        )
        child = repo.add_node(
            db_session, run_id, task_key="c1", instance_key="i0",
            description="child", status=RUNNING,
            parent_node_id=root.id, level=1, meta=META,
        )
        grandchild = repo.add_node(
            db_session, run_id, task_key="gc1", instance_key="i0",
            description="grandchild", status=RUNNING,
            parent_node_id=child.id, level=2, meta=META,
        )

        result = svc.cancel_orphans(
            db_session,
            run_id=run_id,
            definition_id=uuid4(),
            parent_node_id=root.id,
            cause="parent_terminal",
        )

        # Only direct child cancelled, not grandchild
        assert result.cancelled_node_ids == [child.id]
        # Grandchild still running (will be handled by next cascade)
        gc = repo.get_node(db_session, run_id=run_id, node_id=grandchild.id)
        assert gc.status == RUNNING
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/state/test_subtask_cancellation_service.py -v
```

- [ ] **Step 3: Implement SubtaskCancellationService**

Create `ergon_core/ergon_core/core/runtime/services/subtask_cancellation_service.py`. Copy implementation from RFC §7.2 verbatim (includes the approved docstrings).

**Adaptation needed:** The RFC uses `only_if_not_terminal=True` on `update_node_status`. Make sure the call uses keyword args matching our updated signature from Task 1.1.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/state/test_subtask_cancellation_service.py -v
```

Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(service): add SubtaskCancellationService

Single-level cascade: marks non-terminal children of a parent as
CANCELLED, returns events for caller to emit. Does NOT recurse —
cascade to grandchildren is driven by Inngest re-delivering
task/cancelled events."
```

### Task 2.5: TaskInspectionService

**Files:**
- Create: `ergon_core/ergon_core/core/runtime/services/task_inspection_service.py`
- Test: `tests/state/test_task_inspection_service.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/state/test_task_inspection_service.py`:

```python
"""Tests for TaskInspectionService — read-only subtask queries.

Separated from TaskManagementService because inspection has no side
effects. The toolkit injects this independently of the write services.
"""

from uuid import uuid4

from sqlmodel import Session

from ergon_core.core.persistence.graph.status_conventions import (
    COMPLETED,
    FAILED,
    PENDING,
    RUNNING,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.task_inspection_service import TaskInspectionService

META = MutationMeta(actor="test", reason="test")


class TestListSubtasks:
    def test_returns_direct_children_only(self, db_session: Session) -> None:
        repo = WorkflowGraphRepository()
        svc = TaskInspectionService()
        run_id = uuid4()

        parent = repo.add_node(
            db_session, run_id, task_key="root", instance_key="i0",
            description="parent", status=RUNNING, meta=META,
        )
        child = repo.add_node(
            db_session, run_id, task_key="c1", instance_key="i0",
            description="child", status=PENDING,
            parent_node_id=parent.id, level=1, meta=META,
        )
        grandchild = repo.add_node(
            db_session, run_id, task_key="gc1", instance_key="i0",
            description="grandchild", status=PENDING,
            parent_node_id=child.id, level=2, meta=META,
        )

        results = svc.list_subtasks(db_session, run_id=run_id, parent_node_id=parent.id)

        assert len(results) == 1
        assert results[0].node_id == child.id

    def test_returns_deterministic_order(self, db_session: Session) -> None:
        repo = WorkflowGraphRepository()
        svc = TaskInspectionService()
        run_id = uuid4()

        parent = repo.add_node(
            db_session, run_id, task_key="root", instance_key="i0",
            description="parent", status=RUNNING, meta=META,
        )
        for key in ["c3", "c1", "c2"]:
            repo.add_node(
                db_session, run_id, task_key=key, instance_key="i0",
                description=key, status=PENDING,
                parent_node_id=parent.id, level=1, meta=META,
            )

        results = svc.list_subtasks(db_session, run_id=run_id, parent_node_id=parent.id)

        task_keys = [r.task_key for r in results]
        assert task_keys == sorted(task_keys)

    def test_empty_children(self, db_session: Session) -> None:
        repo = WorkflowGraphRepository()
        svc = TaskInspectionService()
        run_id = uuid4()

        parent = repo.add_node(
            db_session, run_id, task_key="root", instance_key="i0",
            description="leaf", status=RUNNING, meta=META,
        )

        results = svc.list_subtasks(db_session, run_id=run_id, parent_node_id=parent.id)
        assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/state/test_task_inspection_service.py -v
```

- [ ] **Step 3: Implement TaskInspectionService**

Create `ergon_core/ergon_core/core/runtime/services/task_inspection_service.py`.

Copy from RFC §7.4, **with these adaptations** since the codebase doesn't have `TaskExecutionRepository.get_latest_for_node` or `ContextEventRepository.mark_stream_closed`:

1. For `_latest_output` and `_latest_error`: query the task_executions table directly via SQLModel. Check how existing code (e.g. `task_execution_service.py`) queries execution records and follow that pattern.
2. For the `output` field: if the execution repo pattern doesn't support fetching output text, return `None` for now and add a `# TODO: wire output extraction` comment. The core listing/ordering functionality is what matters for this phase.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/state/test_task_inspection_service.py -v
```

Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(service): add TaskInspectionService for read-only subtask queries

list_subtasks returns direct children ordered by task_key.
get_subtask returns a single SubtaskInfo with dep edges and status.
Separated from TaskManagementService — no side effects, no write deps."
```

### Task 2.6: TaskCleanupService (stub)

**Files:**
- Create: `ergon_core/ergon_core/core/runtime/services/task_cleanup_service.py`

- [ ] **Step 1: Create TaskCleanupService**

The RFC's TaskCleanupService references `release_sandbox_for_execution` (doesn't exist) and `ContextEventRepository.mark_stream_closed` (doesn't exist). Create a working service with the parts that CAN work, and stub the rest:

```python
"""TaskCleanupService — releases infrastructure for a CANCELLED task execution.

Responsibilities: mark the execution row as CANCELLED, close the
context event stream so trajectory serializers stop tailing it,
and release the E2B sandbox (the main cost driver).

Separated from SubtaskCancellationService because that service
operates on graph nodes (state transitions, fan-out) while this
one operates on execution resources (sandbox, telemetry rows,
context streams). They also have different failure characteristics:
a failed sandbox teardown should be retried for *this* node
without re-cancelling siblings.

Idempotent: every mutating call checks current state before
writing, so Inngest retries=3 is safe.
"""

import logging
from uuid import UUID

from sqlmodel import Session, select

from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import TaskExecution
from ergon_core.core.runtime.services.task_cleanup_dto import CleanupResult

logger = logging.getLogger(__name__)


class TaskCleanupService:
    """Releases infrastructure for a single CANCELLED task execution.

    See module docstring for design rationale.
    """

    async def cleanup(
        self,
        *,
        run_id: UUID,
        node_id: UUID,
        execution_id: UUID | None,
    ) -> CleanupResult:
        if execution_id is None:
            return CleanupResult(
                run_id=run_id, node_id=node_id, execution_id=None,
                sandbox_released=False, execution_row_updated=False,
            )

        with get_session() as session:
            execution_updated = self._mark_execution_cancelled(session, execution_id)
            session.commit()

        # TODO: sandbox teardown — ergon_core/core/runtime/sandbox/teardown.py
        # does not exist yet. Wire release_sandbox_for_execution when sandbox
        # management is implemented.
        sandbox_released = False

        logger.info(
            "task-cleanup node_id=%s execution_id=%s sandbox=%s",
            node_id, execution_id, sandbox_released,
        )
        return CleanupResult(
            run_id=run_id,
            node_id=node_id,
            execution_id=execution_id,
            sandbox_released=sandbox_released,
            execution_row_updated=execution_updated,
        )

    def _mark_execution_cancelled(self, session: Session, execution_id: UUID) -> bool:
        exe = session.exec(
            select(TaskExecution).where(TaskExecution.id == execution_id)
        ).first()
        if exe is None or exe.status in {
            TaskExecutionStatus.COMPLETED,
            TaskExecutionStatus.FAILED,
            TaskExecutionStatus.CANCELLED,
        }:
            return False
        exe.status = TaskExecutionStatus.CANCELLED
        session.add(exe)
        return True
```

Check the actual `TaskExecution` model location and import path. The model might be at a different path — search for `class TaskExecution` in the codebase.

- [ ] **Step 2: Run lint**

```bash
pnpm run check:be:lint
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat(service): add TaskCleanupService for cancelled task resource cleanup

Marks execution row as CANCELLED. Sandbox teardown stubbed — will
be wired when sandbox management module exists. Idempotent under
retry."
```

---

## Phase 3: Inngest Functions + Propagation

### Task 3.1: Wire TASK_CANCEL into execute_task_fn

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/inngest/execute_task.py`

- [ ] **Step 1: Read the current decorator**

```bash
head -50 ergon_core/ergon_core/core/runtime/inngest/execute_task.py
```

- [ ] **Step 2: Add TASK_CANCEL to the cancel list**

Import `TASK_CANCEL` from `inngest_client`:

```python
from ergon_core.core.runtime.inngest_client import RUN_CANCEL, TASK_CANCEL, inngest_client
```

Update the decorator:

```python
@inngest_client.create_function(
    fn_id="task-execute",
    trigger=inngest.TriggerEvent(event="task/ready"),
    cancel=[*RUN_CANCEL, *TASK_CANCEL],   # ← added TASK_CANCEL
    retries=0,
    ...
)
```

- [ ] **Step 3: Run lint + tests**

```bash
pnpm run check:be:lint && pnpm run test:be:fast
```

- [ ] **Step 4: Commit**

```bash
git add ergon_core/ergon_core/core/runtime/inngest/execute_task.py
git commit -m "feat(inngest): wire TASK_CANCEL matcher into execute_task_fn

task/cancelled events matching this node_id now drop queued or
terminate in-flight invocations. Zero-compute path for the common
race where parent finishes immediately after spawning."
```

### Task 3.2: Create cancel_orphan_subtasks Inngest functions

**Files:**
- Create: `ergon_core/ergon_core/core/runtime/inngest/cancel_orphan_subtasks.py`

- [ ] **Step 1: Create the file**

Copy the implementation from RFC §9.1 verbatim (includes the two-step durable execution with `step.run` and approved docstrings).

- [ ] **Step 2: Register in inngest __init__**

Check how other Inngest functions are registered. If there's an `__init__.py` or a registration list, add the three new functions.

```bash
cat ergon_core/ergon_core/core/runtime/inngest/__init__.py
```

Add imports for the three new functions.

- [ ] **Step 3: Run lint**

```bash
pnpm run check:be:lint
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(inngest): add cancel_orphan_subtasks functions

Three Inngest functions — one per trigger event (task/completed,
task/failed, task/cancelled). Each scans children of the triggering
node and cancels non-terminal ones. Uses step.run for durable
two-phase execution: scan-and-cancel then emit-events."
```

### Task 3.3: Create cleanup_cancelled_task Inngest function

**Files:**
- Create: `ergon_core/ergon_core/core/runtime/inngest/cleanup_cancelled_task.py`

- [ ] **Step 1: Create the file**

Copy from RFC §9.2 (the step.run version with `_update_db_rows` and `_release_sandbox` steps).

**Adaptation:** Since `release_sandbox_for_execution` doesn't exist, stub the sandbox step:

```python
    async def _release_sandbox() -> bool:
        # TODO: wire when sandbox management module exists
        return False

    sandbox_released = await ctx.step.run("release-sandbox", _release_sandbox)
```

- [ ] **Step 2: Register in inngest __init__**

Add the import.

- [ ] **Step 3: Run lint**

```bash
pnpm run check:be:lint
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(inngest): add cleanup_cancelled_task_fn

Two durable steps: update-db-rows (mark execution CANCELLED) and
release-sandbox (stubbed — pending sandbox management module).
Each step independently retryable via Inngest retries=3."
```

### Task 3.4: Update propagation for dep-failure cascade and relaxed workflow terminal

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/execution/propagation.py`
- Modify: `ergon_core/ergon_core/core/runtime/inngest/propagate_execution.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/task_propagation_service.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/orchestration_dto.py` — `PropagateTaskCompletionCommand` grows `terminal_status`; return type grows `invalidated_targets`

- [ ] **Step 1: Read current propagation.py structure**

```bash
rg "^def |^class |^async def " ergon_core/ergon_core/core/runtime/execution/propagation.py
```

Understand which flavour is active (definition-based vs graph-native). The graph-native path (`on_task_completed_by_node`, `mark_task_*_by_node`) is what we modify.

- [ ] **Step 2: Update is_workflow_complete**

The function should check that all nodes are terminal AND none are FAILED:

```python
def is_workflow_complete(session: Session, run_id: UUID) -> bool:
    """Every node terminal; zero FAILED. CANCELLED nodes are neutral —
    a run with {COMPLETED, CANCELLED} is considered successful."""
    from ergon_core.core.persistence.graph.status_conventions import (
        FAILED, TERMINAL_STATUSES,
    )
    statuses = list(
        session.exec(select(RunGraphNode.status).where(RunGraphNode.run_id == run_id)).all()
    )
    if not statuses:
        return True
    return (
        all(s in TERMINAL_STATUSES for s in statuses)
        and not any(s == FAILED for s in statuses)
    )
```

- [ ] **Step 3: Update propagation to return invalidated targets**

The graph-native `on_task_completed_by_node` (or equivalent) should return `(newly_ready, invalidated_targets)` when a dep source fails. For COMPLETED sources, outgoing edges become SATISFIED. For FAILED/CANCELLED sources, outgoing edges become INVALIDATED and targets are reported.

Follow the RFC §9.4 pattern.

- [ ] **Step 4: Update propagate_execution.py to emit task/cancelled for invalidated targets**

In the Inngest wrapper, after calling the propagation service, emit `task/cancelled(cause="dep_invalidated")` events for each invalidated target.

- [ ] **Step 5: Ensure all mark_task_* helpers use only_if_not_terminal for terminal writes**

Any call to `update_node_status` that writes a terminal status should pass `only_if_not_terminal=True`.

- [ ] **Step 6: Run tests**

```bash
pnpm run test:be:fast
```

Fix any test failures from the return type change or new propagation behavior.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(propagation): dep-failure cascade and relaxed workflow terminal

FAILED/CANCELLED source invalidates outgoing edges. Invalidated
targets get task/cancelled(cause=dep_invalidated). Workflow terminal
detection tolerates CANCELLED nodes — only FAILED blocks success.
All terminal status writes use only_if_not_terminal=True."
```

### Task 3.5: Rewrite _build_task_map for stored containment

**Files:**
- Modify: `ergon_core/ergon_core/core/api/runs.py`

- [ ] **Step 1: Read current _build_task_map**

```bash
rg -n "_build_task_map" ergon_core/ergon_core/core/api/runs.py
```

- [ ] **Step 2: Replace with three-pass implementation**

Copy the RFC §9.5 implementation:
- Pass 1: build DTOs reading `parent_node_id` and `level` from node columns
- Pass 2: derive `child_ids` and `is_leaf` via reverse lookup
- Pass 3: dependency edges → `depends_on_ids`

- [ ] **Step 3: Update list_children_of in queries.py**

Read the `list_children_of` function:
```bash
rg -n "list_children_of" ergon_core/ergon_core/core/persistence/queries.py -A 20
```

Replace the edge-traversal implementation with a `parent_node_id` query:
```python
def list_children_of(self, session, run_id, parent_node_id):
    """Direct children via containment column — no edge traversal."""
    # Resolves TODO(graph-edges) at the old implementation
    ...
```

- [ ] **Step 4: Update run summary endpoint for cancelled counts (AC8)**

Search for where the run summary/detail response is built:
```bash
rg "completed.*failed\|status.*count\|RunDetailResponse\|RunSummary" ergon_core/ergon_core/core/api/runs.py -n
```

Ensure the response includes `cancelled` count alongside `completed` and `failed`. The `_build_task_map` return tuple already counts by status — add `cancelled` to the counts.

- [ ] **Step 5: Run tests**

```bash
pnpm run test:be:fast
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(api): rewrite _build_task_map for stored containment

Three clean passes: node columns (parent_id, level), reverse lookup
(child_ids, is_leaf), dependency edges (depends_on_ids). Removes the
'first edge = parent' heuristic. Also rewrites list_children_of to
use parent_node_id query (resolves TODO(graph-edges)). Run summary
now reports cancelled count separately (AC8)."
```

---

## Phase 4: Tools + Worker Integration

### Task 4.1: Create bash_sandbox_tool

**Files:**
- Create: `ergon_builtins/ergon_builtins/tools/bash_sandbox_tool.py`

- [ ] **Step 1: Create the file**

```python
"""Sandboxed bash tool for manager agents.

Provides a bash callable that runs commands inside the manager's E2B
sandbox. Primary use case: `sleep N` between subtask-status polls.
Also supports light inspection (cat, echo, grep).

This is a separate module (not inline in the toolkit) because it has
no dependency on the subtask lifecycle services — it only needs the
sandbox_id. Other toolkits can reuse it independently.
"""

from collections.abc import Callable
from typing import Any

from ergon_core.core.runtime.sandbox.exec import sandbox_exec


def make_sandbox_bash_tool(*, sandbox_id: str) -> Callable[..., Any]:
    """Produce a single bash callable bound to the given sandbox."""

    async def bash(command: str, timeout_s: int = 30) -> dict[str, object]:
        """Run a shell command inside the manager's sandbox. Useful for:
           - `sleep 10` between subtask-status polls;
           - `cat` / `echo` for light inspection;
           - simple pipes (grep / awk).
        No host-filesystem access; network policy is inherited from the sandbox."""
        try:
            result = await sandbox_exec(
                sandbox_id=sandbox_id, command=command, timeout_s=timeout_s,
            )
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
            }
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    return bash
```

**Note:** Check if `sandbox_exec` exists. If not, search for the actual sandbox execution helper:
```bash
rg "sandbox_exec\|run_command\|execute_command" ergon_core/ --files-with-matches
```

Adapt the import to match the actual helper. If no sandbox exec helper exists at all, stub it:

```python
async def _stub_sandbox_exec(*, sandbox_id: str, command: str, timeout_s: int):
    """Stub until sandbox management module exists."""
    raise NotImplementedError("Sandbox exec not yet wired")
```

- [ ] **Step 2: Run lint**

```bash
pnpm run check:be:lint
```

- [ ] **Step 3: Commit**

```bash
git add ergon_builtins/ergon_builtins/tools/bash_sandbox_tool.py
git commit -m "feat(tools): add bash_sandbox_tool for manager agents

Sandboxed bash callable for sleep-between-polls and light inspection.
Separate module with no subtask lifecycle dependencies — reusable
by other toolkits."
```

### Task 4.2: Create SubtaskLifecycleToolkit

**Files:**
- Create: `ergon_builtins/ergon_builtins/tools/subtask_lifecycle_toolkit.py`

- [ ] **Step 1: Create the file**

Copy from RFC §8 verbatim (includes the approved docstrings). The toolkit produces seven tools:
1. `add_subtask`
2. `plan_subtasks`
3. `cancel_task`
4. `refine_task`
5. `list_subtasks`
6. `get_subtask`
7. `bash` (via `make_sandbox_bash_tool`)

Plus the factory function:
```python
def build_subtask_lifecycle_tools(
    *,
    run_id: RunId,
    parent_node_id: NodeId,
    sandbox_id: str,
) -> list[Callable[..., Any]]:
    return SubtaskLifecycleToolkit(
        run_id=run_id,
        parent_node_id=parent_node_id, sandbox_id=sandbox_id,
    ).get_tools()
```

- [ ] **Step 2: Run lint**

```bash
pnpm run check:be:lint
```

- [ ] **Step 3: Commit**

```bash
git add ergon_builtins/ergon_builtins/tools/subtask_lifecycle_toolkit.py
git commit -m "feat(tools): add SubtaskLifecycleToolkit

Closure factory producing seven manager-facing tool callables.
Captures run_id and parent_node_id from WorkerContext — agents
never see raw UUIDs. definition_id resolved by service at dispatch.
Replaces TaskManagementToolkit."
```

### Task 4.3: Delete TaskManagementToolkit and update workers

**Files:**
- Delete: `ergon_builtins/ergon_builtins/tools/task_management_toolkit.py`
- Modify: `ergon_builtins/ergon_builtins/workers/research_rubrics/manager_worker.py`
- Modify: any other file importing `TaskManagementToolkit`

- [ ] **Step 1: Find all imports of the old toolkit**

```bash
rg "TaskManagementToolkit\|task_management_toolkit" ergon_builtins/ ergon_core/ tests/
```

- [ ] **Step 2: Delete task_management_toolkit.py**

```bash
rm ergon_builtins/ergon_builtins/tools/task_management_toolkit.py
```

- [ ] **Step 3: Update manager_worker.py**

Replace `TaskManagementToolkit` usage with `build_subtask_lifecycle_tools`. Update the system prompt to reference the new tool names: `add_subtask`, `plan_subtasks`, `cancel_task`, `refine_task`, `list_subtasks`, `get_subtask`, `bash`.

Read the current manager_worker.py to understand the exact integration point (how tools are injected, how the system prompt references them).

- [ ] **Step 4: Update other workers and benchmarks**

Update these files to use `build_subtask_lifecycle_tools`:
- `ergon_builtins/ergon_builtins/workers/baselines/manager_researcher_worker.py`
- `ergon_builtins/ergon_builtins/benchmarks/delegation_smoke/benchmark.py` — drive new toolkit, add cancel-cascade path to smoke test

Verify no `"abandoned"` references in:
- `ergon_builtins/ergon_builtins/workers/research_rubrics/researcher_worker.py`
- `ergon_builtins/ergon_builtins/workers/research_rubrics/stub_worker.py`

- [ ] **Step 5: Update graph_toolkit.py**

Update `list_child_resources` and `list_descendant_resources` to use `parent_node_id` query instead of edge traversal.

```bash
rg "list_children_of\|list_child_resources\|list_descendant" ergon_builtins/ -n
```

- [ ] **Step 6: Update/delete old toolkit tests and worker tests**

```bash
rg "task_management_toolkit\|TaskManagementToolkit" tests/ --files-with-matches
```

Delete or rename test files for the old toolkit. Key files:
- `tests/state/test_task_management_toolkit.py` → rename to `test_subtask_lifecycle_toolkit.py`, update for new tools
- `tests/state/test_graph_toolkit.py` — update assertions for `parent_node_id` query
- `tests/state/test_research_rubrics_workers.py` — update for new toolkit and tool names

- [ ] **Step 7: Run all tests**

```bash
pnpm run test:be:fast
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(tools): replace TaskManagementToolkit with SubtaskLifecycleToolkit

Deleted task_management_toolkit.py. Updated manager_worker.py to use
build_subtask_lifecycle_tools. Updated graph_toolkit to use
parent_node_id queries. Updated system prompts for new tool names."
```

### Task 4.4: Update remaining test fixtures

**Files:**
- Modify: `tests/state/test_delegation_scenario.py`
- Modify: `tests/state/test_propagation_graph_native.py`
- Modify: any test still referencing old patterns

- [ ] **Step 1: Find all remaining references to old patterns**

```bash
rg "\"abandoned\"|ABANDONED|add_task|abandon_task|AbandonTask|AddTask[^S]|delegation.*edge\|edge.*delegation" tests/
```

- [ ] **Step 2: Fix each reference**

- `"abandoned"` → `"cancelled"`
- `ABANDONED` → `CANCELLED`
- `add_task` → `add_subtask` (in service calls)
- `abandon_task` → `cancel_task` (in service calls)
- `AbandonTaskCommand` → `CancelTaskCommand`
- `AddTaskCommand` → `AddSubtaskCommand`
- Remove test fixtures that create delegation edges (edges with `status='active'` as containment)

- [ ] **Step 3: Run full test suite**

```bash
pnpm run test:be:fast
```

- [ ] **Step 4: Run full lint + format**

```bash
pnpm run check:be
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore(tests): update all fixtures for subtask lifecycle

Replace abandoned→cancelled, add_task→add_subtask, abandon_task→cancel_task.
Remove delegation edge fixtures. All tests green."
```

---

## Phase 5: FE Alignment

### Task 5.1: Update FE status vocabulary and edge types

**Files:**
- Modify: `ergon-dashboard/src/lib/types.ts`
- Modify: `ergon-dashboard/src/generated/rest/contracts.ts`
- Modify: `ergon-dashboard/src/components/common/StatusBadge.tsx`
- Modify: `ergon-dashboard/src/components/dag/DAGCanvas.tsx`
- Modify: `ergon-dashboard/src/features/graph/state/graphMutationReducer.ts`
- Modify: `ergon-dashboard/src/components/dag/TaskGraphStatusIcon.tsx`
- Remove/modify: `ergon-dashboard/src/features/graph/components/GraphDelegationEdge.tsx`
- Modify: `ergon_core/ergon_core/core/dashboard/emitter.py` — handle `TaskCancelledEvent`, emit `node.cancelled` dashboard mutation

- [ ] **Step 1: Update dashboard emitter for TaskCancelledEvent**

Read the current emitter and add handling for `TaskCancelledEvent`:
```bash
rg "graph_mutation\|TaskCompleted\|TaskFailed" ergon_core/ergon_core/core/dashboard/emitter.py -n
```

Add a handler that emits a `node.cancelled` mutation when `TaskCancelledEvent` is received. Follow the same pattern as the existing `TaskCompletedEvent`/`TaskFailedEvent` handlers.

- [ ] **Step 2: Find all FE references to "abandoned" and "graphDelegation"**

```bash
rg "abandoned|graphDelegation|delegation" ergon-dashboard/src/ --type ts --type tsx
```

- [ ] **Step 3: Replace "abandoned" with "cancelled" in types**

In `types.ts`:
- `TaskStatus` zod enum: replace `"abandoned"` with `"cancelled"`
- `TaskState.status`: same

In `contracts.ts`:
- If auto-generated, re-run codegen. If hand-maintained, replace `"abandoned"` → `"cancelled"`.

- [ ] **Step 4: Update StatusBadge and TaskGraphStatusIcon**

Replace styling/icon for `"abandoned"` → `"cancelled"`.

- [ ] **Step 5: Remove GraphDelegationEdge**

Delete the file or remove the component. Remove from `edgeTypes` in `DAGCanvas.tsx`.

- [ ] **Step 6: Handle node.cancelled in graphMutationReducer**

Add handling for `"cancelled"` status in the reducer (same treatment as `"failed"` — mark terminal).

- [ ] **Step 7: Run FE checks**

```bash
pnpm run check:fe
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(dashboard): align FE with CANCELLED status and removed delegation edges

abandoned→cancelled in all types, badges, icons. Removed
GraphDelegationEdge (delegation edges no longer exist in DB).
graphMutationReducer handles node.cancelled."
```

---

## Phase 6: Final Verification

### Task 6.1: Full check suite

- [ ] **Step 1: Run full backend checks**

```bash
pnpm run check:be
```

Expected: All pass (lint, format, type, slopcop)

- [ ] **Step 2: Run full backend tests**

```bash
pnpm run test:be:fast
```

Expected: All pass

- [ ] **Step 3: Run FE checks**

```bash
pnpm run check:fe
```

Expected: All pass

- [ ] **Step 4: Verify no stale references**

```bash
rg "ABANDONED\b|\"abandoned\"|'abandoned'|EDGE_ACTIVE|\"active\"" ergon_core/ ergon_builtins/ tests/ ergon-dashboard/src/
```

Expected: Zero hits (or only in migration/changelog files)

```bash
rg "TaskManagementToolkit|task_management_toolkit" ergon_core/ ergon_builtins/ tests/
```

Expected: Zero hits

- [ ] **Step 5: Git log review**

```bash
git log --oneline main..HEAD
```

Verify commit chain is clean and each commit message accurately describes its change.

---

## Summary of phases and subagent dispatch

| Phase | Tasks | Can run as one subagent | Dependencies |
|-------|-------|------------------------|-------------|
| 0 — Schema | 0.1, 0.2, 0.3, 0.4 | Yes | None |
| 1 — Conditional writes | 1.1, 1.2, 1.3 | Yes | Phase 0 |
| 2 — Services | 2.1, 2.2, 2.3, 2.4, 2.5, 2.6 | Yes | Phase 1 |
| 3 — Inngest + Propagation | 3.1, 3.2, 3.3, 3.4, 3.5 | Yes | Phase 2 |
| 4 — Tools + Workers | 4.1, 4.2, 4.3, 4.4 | Yes | Phase 3 |
| 5 — FE Alignment | 5.1 | Yes | Phase 3 (BE must be done) |
| 6 — Verification | 6.1 | Yes | All previous |

Each phase should be dispatched as a single subagent. Review between phases.
