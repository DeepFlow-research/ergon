# Six-Step Task Propagation — Implementation Plan

> **Precondition:** `0-task-status-design.md` is agreed. All code changes here implement its FSM and schema requirements. Integration tests are the acceptance criterion; core logic changes must make the tests pass, not the other way around.

---

## Execution order

```
Step 1: Schema migrations         — Postgres DDL + Alembic + Python models
Step 2: Constants & enums         — status_conventions.py, enums.py
Step 3: Write integration tests   — all marked xfail; watch them fail
Step 4: Fix failure propagation   — CANCELLED → BLOCKED, horizontal + vertical
Step 5: Fix terminal detection    — RunRecord never auto-FAILED from propagation
Step 6: Fix restart + management  — restart unblocks, new operator_unblock endpoint
→ Re-run integration tests        — watch them pass
→ E2E reconciliation              — align E2E tests to new semantics
```

Steps 1–2 have no logic changes — they are prerequisites. Write the tests in Step 3 *before* fixing the code in Steps 4–6. The red/green cycle is the signal.

---

## Step 1: Schema migrations

Four Alembic migrations, in dependency order. Each follows the pattern in `ergon_core/migrations/versions/84519b3f8431_add_cancelled_to_taskexecutionstatus_enum.py`.

### Migration A — Add `BLOCKED` to `taskexecutionstatus` enum

```bash
cd ergon_core
uv run alembic revision --autogenerate -m "add_blocked_to_taskexecutionstatus_enum"
# Then hand-edit the generated file to contain:
```

```python
# ergon_core/migrations/versions/<hash>_add_blocked_to_taskexecutionstatus_enum.py

def upgrade() -> None:
    if op.get_context().dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        op.execute(
            sa.text("ALTER TYPE taskexecutionstatus ADD VALUE IF NOT EXISTS 'blocked'")
        )

def downgrade() -> None:
    pass  # Postgres cannot remove enum values without rewriting the type
```

### Migration B — `triggered_by_mutation_id` on `RunGraphMutation`

```python
# ergon_core/migrations/versions/<hash>_add_triggered_by_mutation_id.py

def upgrade() -> None:
    op.add_column(
        "run_graph_mutations",
        sa.Column("triggered_by_mutation_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_run_graph_mutations_triggered_by",
        "run_graph_mutations", "run_graph_mutations",
        ["triggered_by_mutation_id"], ["id"],
        ondelete="SET NULL",
    )

def downgrade() -> None:
    op.drop_constraint("fk_run_graph_mutations_triggered_by", "run_graph_mutations")
    op.drop_column("run_graph_mutations", "triggered_by_mutation_id")
```

### Migration C — `batch_operation_id` on `RunGraphMutation`

```python
# ergon_core/migrations/versions/<hash>_add_batch_operation_id.py

def upgrade() -> None:
    op.add_column(
        "run_graph_mutations",
        sa.Column("batch_operation_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_run_graph_mutations_batch_operation_id",
        "run_graph_mutations",
        ["batch_operation_id"],
        postgresql_where=sa.text("batch_operation_id IS NOT NULL"),
    )

def downgrade() -> None:
    op.drop_index("ix_run_graph_mutations_batch_operation_id")
    op.drop_column("run_graph_mutations", "batch_operation_id")
```

### Migration D — `sandbox_id` on `RunTaskExecution`

```python
# ergon_core/migrations/versions/<hash>_add_sandbox_id_to_run_task_execution.py

def upgrade() -> None:
    op.add_column(
        "run_task_executions",
        sa.Column("sandbox_id", sa.String(), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("run_task_executions", "sandbox_id")
```

Run all four in sequence:
```bash
cd ergon_core && uv run alembic upgrade head
```

---

## Step 2: Constants, enums, and models

Three files. Pure additions — no existing values change.

### `ergon_core/ergon_core/core/persistence/graph/status_conventions.py`

```python
# Add after CANCELLED:
BLOCKED = "blocked"

# Update:
TERMINAL_STATUSES = frozenset({COMPLETED, FAILED, CANCELLED})
# BLOCKED is intentionally absent — it is non-terminal

# Update:
NodeStatus = Literal["pending", "ready", "running", "completed", "failed", "cancelled", "blocked"]
```

### `ergon_core/ergon_core/core/persistence/shared/enums.py`

```python
class TaskExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"   # ← add
```

### `ergon_core/ergon_core/core/persistence/graph/models.py`

Add two fields to `RunGraphMutation` (line ~185):

```python
class RunGraphMutation(SQLModel, table=True):
    # ... existing fields ...
    triggered_by_mutation_id: UUID | None = Field(
        default=None,
        foreign_key="run_graph_mutations.id",
        sa_column_kwargs={"ondelete": "SET NULL"},
    )
    batch_operation_id: UUID | None = Field(default=None, index=False)
```

---

## Step 3: Write the integration tests (all xfail)

Create one file per logical group. All tests start as `xfail(strict=True)` — the code changes in Steps 4–6 should make them pass one by one. Remove `xfail` as each test goes green.

```
tests/integration/
    propagation/
        __init__.py
        test_propagation_happy.py       # Tests 1, 2, 4, 5, 9
        test_propagation_blocked.py     # Tests 3, 7, 10, 11, 12, 13
        test_propagation_restart.py     # Test 8
        test_propagation_cancel.py      # Test 6
        test_propagation_edge_cases.py  # EC-1 through EC-7
        test_propagation_bulk.py        # B-1 through B-5
        test_propagation_races.py       # R-1 through R-4
        _helpers.py                     # Shared polling, assertion helpers
```

### `_helpers.py` scaffold

```python
import time
from uuid import UUID
from sqlmodel import Session, select
from ergon_core.core.persistence.graph.models import RunGraphNode, RunGraphMutation
from ergon_core.core.persistence.graph.status_conventions import TERMINAL_STATUSES

def poll_until(condition, *, timeout=30, interval=0.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(interval)
    raise TimeoutError("poll_until timed out")

def get_node_status(session: Session, run_id: UUID, node_id: UUID) -> str:
    return session.exec(
        select(RunGraphNode.status).where(
            RunGraphNode.id == node_id,
            RunGraphNode.run_id == run_id,
        )
    ).one()

def assert_wal_entry(session: Session, node_id: UUID, expected_status: str, cause: str | None = None):
    """Assert at least one mutation row for node with new_value containing expected_status."""
    mutations = session.exec(
        select(RunGraphMutation).where(RunGraphMutation.target_id == node_id)
    ).all()
    matching = [m for m in mutations if m.new_value.get("status") == expected_status]
    assert matching, f"No WAL entry with status={expected_status!r} for node {node_id}"
    if cause is not None:
        assert any(m.reason and cause in m.reason for m in matching), \
            f"No WAL entry with cause={cause!r} for node {node_id}"

def assert_cross_cutting_invariants(session: Session, run_id: UUID):
    """Call from every test after the run reaches terminal or stuck state."""
    nodes = session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all()
    # WAL completeness
    for node in nodes:
        mutations = session.exec(
            select(RunGraphMutation).where(RunGraphMutation.target_id == node.id)
        ).all()
        assert mutations, f"Node {node.id} has no WAL entries"
    # FAILED nodes must have RunTaskExecution with error_json
    # (check via RunTaskExecution join — omitted here for brevity, add in implementation)
    # No BLOCKED RunRecord status (RunRecord.status is never "blocked")
    # ... etc
```

### First tests to write (highest signal, lowest complexity)

Write these first — they exercise the core new semantics and will fail most obviously:

```python
# test_propagation_blocked.py

import pytest

@pytest.mark.xfail(strict=True, reason="BLOCKED not implemented; successors become CANCELLED")
async def test_3_failure_cascade_successor_blocked(run_factory, db_session):
    """A→B→C. B fails. C must be BLOCKED, not CANCELLED. RunRecord stays RUNNING."""
    run = await run_factory.linear_chain(steps=3)  # A→B→C, B configured to fail
    poll_until(lambda: get_node_status(db_session, run.id, run.nodes["B"]) == "failed")
    poll_until(lambda: get_node_status(db_session, run.id, run.nodes["C"]) == "blocked",
               timeout=5)  # short timeout — should arrive quickly after B fails

    assert get_node_status(db_session, run.id, run.nodes["A"]) == "completed"
    assert get_node_status(db_session, run.id, run.nodes["B"]) == "failed"
    assert get_node_status(db_session, run.id, run.nodes["C"]) == "blocked"
    assert run.record.status == "executing"  # RunRecord stays RUNNING

    assert_wal_entry(db_session, run.nodes["C"], "blocked", cause="dep_failed")
    assert_cross_cutting_invariants(db_session, run.id)


@pytest.mark.xfail(strict=True, reason="parent failure cascades CANCELLED not BLOCKED to children")
async def test_7_parent_failure_children_blocked(run_factory, db_session):
    """Parent FAILED → PENDING/READY children BLOCKED. RUNNING children untouched."""
    run = await run_factory.parent_with_subtree(...)  # parent fails; child-A PENDING, child-B RUNNING
    poll_until(lambda: get_node_status(db_session, run.id, run.nodes["parent"]) == "failed")
    poll_until(lambda: get_node_status(db_session, run.id, run.nodes["child_a"]) in ("blocked", "failed", "cancelled"))

    assert get_node_status(db_session, run.id, run.nodes["child_a"]) == "blocked"
    assert get_node_status(db_session, run.id, run.nodes["child_b"]) in ("running", "completed", "failed")  # not interrupted
    assert run.record.status == "executing"  # NOT failed

    assert_wal_entry(db_session, run.nodes["child_a"], "blocked", cause="parent_failed")
```

Write all 13 primary tests + 7 ECs + 5 Bs + 4 Rs before touching any production code. The full set of failures is the spec compliance baseline.

---

## Step 4: Fix failure propagation — CANCELLED → BLOCKED

Two files. This is the core change.

### `ergon_core/ergon_core/core/runtime/execution/propagation.py`

**Change 1 — `on_task_completed_or_failed`: horizontal BLOCKED**

In the failure path (around line where `new_status=CANCELLED` appears):

```python
# BEFORE:
if not is_success:
    if candidate_node.parent_node_id is not None:
        continue  # Dynamic subtasks — leave for manager
    await graph_repo.update_node_status(
        session, run_id=run_id, node_id=candidate_id,
        new_status=CANCELLED,
        meta=MutationMeta(actor="system:propagation", reason=f"dependency {node_id} failed"),
        only_if_not_terminal=True,
    )
    invalidated.append(candidate_id)
    continue

# AFTER:
if not is_success:
    # All successors (static and dynamic) become BLOCKED.
    # BLOCKED means "predecessor failed; operator action required."
    # Do NOT emit task/cancelled — BLOCKED is a DB write only.
    await graph_repo.update_node_status(
        session, run_id=run_id, node_id=candidate_id,
        new_status=BLOCKED,
        meta=MutationMeta(
            actor="system:propagation",
            reason=f"dependency {node_id} failed",
        ),
        only_if_not_terminal=True,
    )
    # Do not append to invalidated — no events to emit for BLOCKED transitions
    continue
```

**Change 2 — `is_workflow_failed_v2`: only terminal when ALL nodes done**

```python
# BEFORE:
def is_workflow_failed_v2(session: Session, run_id: UUID) -> bool:
    statuses = list(session.exec(select(RunGraphNode.status).where(...)).all())
    return any(s == TaskExecutionStatus.FAILED for s in statuses)

# AFTER:
def is_workflow_failed_v2(session: Session, run_id: UUID) -> bool:
    """All nodes terminal AND at least one FAILED.

    A run with BLOCKED tasks is stuck (RUNNING), not failed. Only when every
    node is terminal (including any BLOCKED ones being resolved to CANCELLED
    by the operator) and at least one is FAILED does the run finalise as FAILED.
    """
    statuses = list(session.exec(select(RunGraphNode.status).where(...)).all())
    if not statuses:
        return False
    all_terminal = all(s in TERMINAL_STATUSES for s in statuses)
    return all_terminal and any(s == FAILED for s in statuses)
```

Note: `BLOCKED ∉ TERMINAL_STATUSES`, so `all_terminal` is False whenever any node is BLOCKED. A stuck run with BLOCKED tasks will never trigger this function. Only when the operator has resolved all BLOCKED nodes (by restarting, cancelling, or unblocking them) and a FAILED node remains will this return True.

### `ergon_core/ergon_core/core/runtime/inngest/cancel_orphan_subtasks.py`

**Change — `cancel-orphans-on-failed`: cascade BLOCKED to descendants, not CANCELLED**

The `cancel_orphans_on_failed_fn` function currently cascades CANCELLED to all non-terminal children of a FAILED parent. Under the new design, children of a FAILED parent must become BLOCKED (not CANCELLED — that's reserved for intentional stops).

```python
# BEFORE: cancel-orphans-on-failed calls _cancel_orphans_for with cause="parent_terminal"
# which sets status=CANCELLED

# AFTER: replace with block-descendants-on-failed:
@inngest_client.create_function(
    fn_id="block-descendants-on-failed",
    trigger=inngest.TriggerEvent(event="task/failed"),
    cancel=RUN_CANCEL,
    retries=1,
)
async def block_descendants_on_failed_fn(ctx: inngest.Context) -> int:
    """When a parent fails, PENDING/READY containment descendants become BLOCKED.

    RUNNING descendants are not interrupted — they continue to their own terminal.
    This function only walks the vertical (containment) axis via parent_node_id.
    Horizontal (dependency) BLOCKED propagation is handled in propagation.py.
    """
    payload = TaskFailedEvent.model_validate(ctx.event.data)

    async def _block_descendants() -> list[str]:
        svc = SubtaskBlockingService()  # new service — see below
        with get_session() as session:
            blocked_ids = await svc.block_pending_descendants(
                session,
                run_id=payload.run_id,
                parent_node_id=payload.node_id,
                cause="parent_failed",
            )
        return [str(nid) for nid in blocked_ids]

    blocked = await ctx.step.run("block-pending-descendants", _block_descendants)
    return len(blocked)
```

**New service: `SubtaskBlockingService`** in `ergon_core/ergon_core/core/runtime/services/subtask_blocking_service.py`:

```python
"""Block PENDING/READY containment descendants when a parent fails."""

from uuid import UUID
from sqlmodel import Session, select
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import BLOCKED, TERMINAL_STATUSES, RUNNING
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository


class SubtaskBlockingService:
    async def block_pending_descendants(
        self,
        session: Session,
        *,
        run_id: UUID,
        parent_node_id: UUID,
        cause: str,
    ) -> list[UUID]:
        """Recursively BLOCK all PENDING/READY descendants of parent_node_id.

        RUNNING descendants are skipped — live executions continue to their
        own terminal state. Already-terminal descendants are skipped via
        only_if_not_terminal=True.

        Returns IDs of nodes that were transitioned to BLOCKED.
        """
        graph_repo = WorkflowGraphRepository()
        blocked: list[UUID] = []
        queue = [parent_node_id]

        while queue:
            current_parent = queue.pop()
            children = session.exec(
                select(RunGraphNode).where(
                    RunGraphNode.run_id == run_id,
                    RunGraphNode.parent_node_id == current_parent,
                )
            ).all()

            for child in children:
                queue.append(child.id)  # recurse into grandchildren

                if child.status == RUNNING or child.status in TERMINAL_STATUSES:
                    continue  # RUNNING: not interrupted; terminal: guard handles it

                await graph_repo.update_node_status(
                    session,
                    run_id=run_id,
                    node_id=child.id,
                    new_status=BLOCKED,
                    meta=MutationMeta(actor="system:propagation", reason=cause),
                    only_if_not_terminal=True,
                )
                blocked.append(child.id)

        session.commit()
        return blocked
```

### `ergon_core/ergon_core/core/runtime/inngest/propagate_execution.py`

**Change — `propagate_task_failure_fn`: stop emitting `task/cancelled` events**

```python
# BEFORE:
failure_events: list[inngest.Event] = [
    inngest.Event(
        name=TaskCancelledEvent.name,
        data=TaskCancelledEvent(
            ..., cause="dep_invalidated",
        ).model_dump(mode="json"),
    )
    for inv_node_id in propagation.invalidated_targets
]

# AFTER:
# BLOCKED successors are a DB write only — no task/cancelled events.
# invalidated_targets is now empty (on_task_completed_or_failed no longer
# appends to it on the failure path).
failure_events: list[inngest.Event] = []
```

Also remove the `WorkflowFailedEvent` emission from `propagate_task_failure_fn`. The workflow only fails when ALL nodes are terminal and any is FAILED — `is_workflow_failed_v2` now handles this correctly:

```python
# BEFORE:
if propagation.workflow_terminal_state == WorkflowTerminalState.FAILED:
    failure_events.append(inngest.Event(name=WorkflowFailedEvent.name, ...))

# AFTER: keep — but now is_workflow_failed_v2 only returns True when ALL
# nodes are terminal. A stuck run never reaches this branch.
# No change to the conditional itself; the fix is in is_workflow_failed_v2.
```

---

## Step 5: Fix workflow terminal detection

### `ergon_core/ergon_core/core/runtime/services/task_propagation_service.py`

The `propagate()` (success) path currently checks `is_workflow_failed_v2` and can set `WorkflowTerminalState.FAILED` when a task completes but there are pre-existing FAILED nodes. Under the new design, that is wrong — completing task A does not make the workflow enter a FAILED terminal state.

```python
# BEFORE (in propagate()):
terminal = WorkflowTerminalState.NONE
if is_workflow_complete_v2(session, command.run_id):
    terminal = WorkflowTerminalState.COMPLETED
elif is_workflow_failed_v2(session, command.run_id):
    terminal = WorkflowTerminalState.FAILED

# AFTER: unchanged — is_workflow_failed_v2 now returns False unless all
# nodes are terminal AND any is FAILED. A run with BLOCKED tasks will
# fall through to NONE correctly.
# If all nodes are terminal (operator resolved all BLOCKED to CANCELLED)
# and one is FAILED, WorkflowTerminalState.FAILED fires correctly here too.
```

The fix in `is_workflow_failed_v2` (Step 4) makes `propagate()` behave correctly without changing `task_propagation_service.py`. Verify with Test 3: after B fails and C is BLOCKED, `propagate()` completing A should see WorkflowTerminalState.NONE.

---

## Step 6: Fix restart and add operator_unblock

### `ergon_core/ergon_core/core/runtime/services/task_management_service.py`

**Change — `restart_task._invalidate_downstream`**

Currently traverses `RunGraphEdge` and emits `task/cancelled` for all downstream nodes. Under the new design:
- BLOCKED successors → PENDING (not CANCELLED — predecessor is being retried)
- COMPLETED successors → CANCELLED with cause `dep_invalidated`
- PENDING/READY successors — do NOT exist when restarting a FAILED node (they'd be BLOCKED already)

```python
async def _invalidate_downstream(self, session, *, run_id, node_id, graph_repo):
    """Reset outgoing edges; unblock BLOCKED successors; invalidate COMPLETED ones."""
    outgoing_edges = session.exec(
        select(RunGraphEdge).where(
            RunGraphEdge.run_id == run_id,
            RunGraphEdge.source_node_id == node_id,
        )
    ).all()

    for edge in outgoing_edges:
        await graph_repo.update_edge_status(
            session, run_id=run_id, edge_id=edge.id,
            new_status=EDGE_PENDING,
            meta=MutationMeta(actor="system:restart"),
        )

        successor = session.get(RunGraphNode, edge.target_node_id)
        if successor is None:
            continue

        if successor.status == BLOCKED:
            # Predecessor is being retried — successor re-evaluates when it completes.
            await graph_repo.update_node_status(
                session, run_id=run_id, node_id=successor.id,
                new_status=PENDING,
                meta=MutationMeta(actor="system:restart", reason="predecessor_restarted"),
                only_if_not_terminal=False,  # BLOCKED is non-terminal; guard would pass anyway
            )
        elif successor.status == COMPLETED:
            # Prior outputs are stale — invalidate.
            await graph_repo.update_node_status(
                session, run_id=run_id, node_id=successor.id,
                new_status=CANCELLED,
                meta=MutationMeta(actor="system:restart", reason="dep_invalidated"),
                only_if_not_terminal=True,
            )
        # RUNNING successors: not interrupted. PENDING/READY: shouldn't exist
        # (they'd be BLOCKED if this node was FAILED), but if somehow present, leave them.
```

**Change — containment descendants on restart**

Currently `restart_task` does not cancel containment descendants (the existing `_invalidate_downstream` only walks `RunGraphEdge`). The design requires: all containment descendants → CANCELLED before the new execution starts.

Add a call to `SubtaskCancellationService.cancel_orphans(parent_node_id=node_id)` (the existing service) before resetting the node itself:

```python
async def restart_task(self, run_id, node_id, ...):
    # 1. Cancel all containment descendants first (new execution creates fresh ones)
    svc = SubtaskCancellationService()
    await svc.cancel_orphans(session, run_id=run_id, parent_node_id=node_id, cause="operator_restart")

    # 2. Reset own outgoing edges + unblock/invalidate successors
    await self._invalidate_downstream(session, run_id=run_id, node_id=node_id, ...)

    # 3. Reset own status to PENDING
    await graph_repo.update_node_status(session, run_id=run_id, node_id=node_id, new_status=PENDING, ...)

    # 4. Emit task/ready
    await inngest_client.send(inngest.Event(name="task/ready", data=...))
```

**New method — `operator_unblock`**

```python
async def operator_unblock(self, session, *, run_id: UUID, node_id: UUID) -> None:
    """Transition a BLOCKED node to PENDING without restarting its predecessor.

    The operator is asserting "proceed despite the failed predecessor."
    The predecessor stays FAILED. The node re-evaluates when predecessors
    complete; it will stay PENDING until all predecessors complete or
    the operator takes further action.

    This transition MUST NOT fire from propagation logic — operator-only.
    """
    node = session.get(RunGraphNode, node_id)
    if node is None or node.run_id != run_id:
        raise NotFoundError(f"node {node_id} not found in run {run_id}")
    if node.status != BLOCKED:
        raise InvalidTransitionError(
            f"operator_unblock requires BLOCKED; got {node.status!r}"
        )

    # Reset all incoming edges to EDGE_PENDING so the node re-evaluates
    incoming_edges = session.exec(
        select(RunGraphEdge).where(
            RunGraphEdge.run_id == run_id,
            RunGraphEdge.target_node_id == node_id,
        )
    ).all()
    for edge in incoming_edges:
        await graph_repo.update_edge_status(
            session, run_id=run_id, edge_id=edge.id,
            new_status=EDGE_PENDING,
            meta=MutationMeta(actor="operator", reason="operator_unblock"),
        )

    await graph_repo.update_node_status(
        session, run_id=run_id, node_id=node_id,
        new_status=PENDING,
        meta=MutationMeta(actor="operator", reason="operator_unblock"),
        only_if_not_terminal=False,
    )
    session.commit()
```

Expose via a new API endpoint: `POST /runs/{run_id}/tasks/{node_id}/unblock`.

---

## Run the integration tests

```bash
uv run pytest tests/integration/propagation/ -v --tb=short
```

Expected sequence as steps land:
- After Step 4: Tests 3, 7, 10, 12 go green
- After Step 5: Test 3's RunRecord assertion goes green; `is_workflow_failed_v2` fix validated
- After Step 6 (restart): Tests 8, 11 go green
- After Step 6 (operator_unblock): Test 13 goes green
- EC-1 (fan-in under failure → BLOCKED): goes green after Step 4
- EC-6 (multi-predecessor BLOCKED): goes green after Step 6
- B and R tests: require bulk endpoint and locking model — implement after the above core tests pass

Tests 1, 2, 4, 5, 6, 9 should be green before any changes (they test paths the existing code handles correctly). If they red, that's a regression — fix before proceeding.

---

## E2E reconciliation

After the integration tests pass, run the E2E suite:

```bash
uv run pytest tests/e2e/ -v --tb=short
```

E2E tests currently assert `RunRecord.status == "failed"` when any task fails. Under the new design, `RunRecord` stays `"executing"` when tasks are BLOCKED. Two likely failure modes:

**Failure mode 1 — E2E poll times out waiting for RunRecord.FAILED**

The E2E assertion helper (`tests/e2e/_asserts.py`) polls for a terminal RunRecord status. If the run is stuck (BLOCKED tasks), it will poll until timeout. Fix: update the helper to also accept `"executing"` as a valid "settled" state for failure scenarios, or add a `poll_until_stuck` helper that checks for BLOCKED tasks.

**Failure mode 2 — E2E expected final score is wrong**

If a run that previously ended with `RunRecord.FAILED` (auto-propagated) now ends with `RunRecord.EXECUTING` (stuck), score aggregation never runs. The E2E test asserting a score of 0 (or any score) will fail because `summary_json` is never written.

For each failing E2E test, determine which scenario it exercises:
1. Task genuinely fails and the run should be stuck → update assertion to check BLOCKED node exists, RunRecord is EXECUTING
2. Task fails and all others cancel → now all others become BLOCKED → run stays EXECUTING → test needs rethinking
3. E2E has an explicit cancellation step → behavior unchanged

Specific files to check:
- `tests/e2e/_asserts.py` — update `assert_run_completed` / `assert_run_failed` helpers
- `tests/e2e/test_smoke_harness.py` (integration) — check what terminal state it polls for
- `tests/e2e/test_minif2f_smoke.py`, `test_swebench_smoke.py`, `test_researchrubrics_smoke.py` — these use real LLM; only run if a failure scenario is deliberately triggered

Do not change E2E test behavior speculatively. Run them, read the failures, update the specific assertions that conflict with the new semantics. The goal is that the E2E tests still accurately describe what the system does — not that they all pass by lowering the bar.

---

## What is NOT changing in this plan

- `cancel-orphans-on-completed` — still cascades CANCELLED to orphaned subtasks when parent COMPLETES (correct behavior unchanged)
- `cancel-orphans-on-cancelled` — still cascades CANCELLED when parent is CANCELLED (correct behavior unchanged)
- `StubSandboxManager` / `is_stub_sandbox_id` removal — separate cleanup (violated assumption B), not part of this plan
- Bulk operation locking model (Section 9 of status design doc) — `SELECT FOR UPDATE` implementation is a separate pass after core tests pass
- `triggered_by_mutation_id` population — schema is added in Step 1; populating it in every mutation call is a follow-up once the core paths are stable

---

## Checklist

```
[ ] Step 1: 4 Alembic migrations written and applied (uv run alembic upgrade head)
[ ] Step 2: BLOCKED in status_conventions.py, enums.py, RunGraphMutation model
[ ] Step 3: All integration tests written and failing (xfail strict)
[ ] Step 4a: on_task_completed_or_failed failure path → BLOCKED (not CANCELLED)
[ ] Step 4b: is_workflow_failed_v2 → only True when ALL nodes terminal
[ ] Step 4c: SubtaskBlockingService + block-descendants-on-failed Inngest fn
[ ] Step 4d: propagate_task_failure_fn stops emitting task/cancelled
[ ] Step 5: Verify propagate() (success path) WorkflowTerminalState.NONE when BLOCKED present
[ ] Step 6a: restart_task cancels containment descendants before resetting
[ ] Step 6b: restart_task unblocks BLOCKED successors → PENDING (not cancel them)
[ ] Step 6c: operator_unblock method + API endpoint
[ ] Integration tests: remove xfail from passing tests
[ ] E2E: run, read failures, update assertions that conflict with new semantics
[ ] pnpm run check:fast passes
[ ] Architecture docs updated (docs/architecture/) per CLAUDE.md requirement
```
