---
status: active
opened: 2026-04-17
author: deepflow-research
architecture_refs: [docs/architecture/02_runtime_lifecycle.md#invariants, docs/architecture/cross_cutting/error_propagation.md]
supersedes: []
superseded_by: null
---

# RFC: Align static-sibling failure propagation with fractal-OS semantics (stay PENDING)

## Problem

`on_task_completed_or_failed` in
`ergon_core/ergon_core/core/runtime/execution/propagation.py:438-586`
treats static workflow siblings and managed subtasks differently on upstream
failure:

- **Managed subtasks** (`parent_node_id is not None`, lines 505-513): the edge
  is INVALIDATED but the target node is left PENDING. The manager observes the
  failure and decides whether to retry, cancel, or re-plan. Matches fractal-OS
  semantics.
- **Static workflow siblings** (`parent_node_id is None`, lines 515-527): the
  target is written CANCELLED via `graph_repo.update_node_status` with
  `only_if_not_terminal=True`, then appended to the `invalidated` return list.
  Diverges from fractal-OS semantics.

The diverging gate is at lines 505-513:

```python
if not is_success:
    if candidate_node.parent_node_id is not None:
        continue                           # manager-owned: stay PENDING

    graph_repo.update_node_status(         # static: auto-cancel
        session, run_id=run_id, node_id=candidate_id,
        new_status=CANCELLED,
        meta=MutationMeta(actor="system:propagation",
                          reason=f"dependency {node_id} {terminal_status}"),
        only_if_not_terminal=True,
    )
    invalidated.append(candidate_id)
    continue
```

The `propagate_task_failure_fn` Inngest function in
`ergon_core/ergon_core/core/runtime/inngest/propagate_execution.py:137-200`
calls `TaskPropagationService.propagate_failure`, which calls
`on_task_completed_or_failed` with `terminal_status=FAILED` and then emits a
`TaskCancelledEvent` (cause `"dep_invalidated"`) for every node in the
`invalidated_targets` list. This causes `cancel_orphan_subtasks_fn` to fire,
which calls `SubtaskCancellationService.cancel_orphans` on the now-CANCELLED
static node — cancelling any dynamic children that static node happened to
have. The chain is load-bearing for the current semantics.

Secondary consequence: `is_workflow_complete_v2` at lines 594-601:

```python
def is_workflow_complete_v2(session: Session, run_id: UUID) -> bool:
    statuses = list(
        session.exec(select(RunGraphNode.status).where(RunGraphNode.run_id == run_id)).all()
    )
    if not statuses:
        return True
    return all(s in TERMINAL_STATUSES for s in statuses) and not any(s == FAILED for s in statuses)
```

This returns `True` only when **every node** is in `{COMPLETED, FAILED,
CANCELLED}` and no node is FAILED. Under the new semantics, a failed node
leaves its static downstream siblings PENDING. `is_workflow_complete_v2` then
never returns `True` for those runs. The workflow hangs: `task-propagate` will
not emit `workflow/completed` or `workflow/failed` because neither
`is_workflow_complete_v2` nor `is_workflow_failed_v2` (line 604) becomes True
while unblocked-PENDING nodes exist.

`is_workflow_failed_v2` (lines 604-609) is fine as-is — it returns `True`
whenever any node is FAILED. After the semantic flip, a FAILED node still
triggers `is_workflow_failed_v2=True`, so `propagate_task_failure_fn` will
detect `WorkflowTerminalState.FAILED` correctly once `is_workflow_complete_v2`
no longer fires first on PENDING-blocked runs.

Existing test `tests/state/test_dep_failure_cascade.py:43-86`
(`TestStaticNodeAutoCancel`) encodes the current auto-cancel semantic and will
fail after the change. `tests/state/test_dep_failure_cascade.py:219-280`
(`TestDynamicSubtaskNoAutoCancel::test_mixed_static_and_dynamic_targets`)
also asserts `c_row.status == "cancelled"` for the static node; this must be
inverted.

System owner steer (2026-04-17): the intended model is uniform — "if B depends
on A and A fails, B stays PENDING forever unless an adaptive planner unblocks
it." Auto-cancelling static siblings removes optionality and bakes in an
assumption that no planner will ever exist above the static DAG.

---

## Proposal

Four coordinated changes, across two PRs:

1. **Rewrite `is_workflow_complete_v2`** with a blocked-chain rule: the
   workflow is complete when every non-terminal node is blocked by at least one
   INVALIDATED incoming edge and none of its incoming edges are in a
   satisfiable (PENDING) state. A node that is PENDING with all PENDING
   incoming edges is not blocked; it is waiting. The new rule must not confuse
   the two.

2. **Remove the static auto-cancel branch** in `on_task_completed_or_failed`:
   delete the `graph_repo.update_node_status(CANCELLED)` write and the
   `invalidated.append` for static nodes. Both static and managed nodes stay
   PENDING; both edges become INVALIDATED uniformly. The `invalidated` return
   list becomes empty on the failure path for all node types.

3. **Stop emitting `TaskCancelledEvent` for invalidated static targets** in
   `propagate_task_failure_fn`: after step 2, `propagation.invalidated_targets`
   will be empty for static nodes, so the event fan-out loop already does the
   right thing. No code change needed in `propagate_execution.py` beyond
   removing an assertion or comment.

4. **Rewrite the affected tests** in `tests/state/test_dep_failure_cascade.py`
   and `tests/state/test_propagation_graph_native.py` against the new semantic;
   add new tests for the `is_workflow_complete_v2` blocked-chain rule.

PR order:

- **PR 1** — Rewrite `is_workflow_complete_v2`, add tests for the new rule
  (run them against the old propagation semantic where static nodes are still
  auto-cancelled — the new completion check should still work because
  CANCELLED ∈ TERMINAL_STATUSES and blocked-PENDING does not yet exist).
- **PR 2** — Remove the auto-cancel branch from `on_task_completed_or_failed`;
  rewrite `test_dep_failure_cascade.py`; rewrite any other tests that assert
  the old auto-cancel outcome.

No data migration. This is a forward-only behavior change. In-flight runs at
deploy time continue under whichever state their nodes have already reached.
Existing CANCELLED nodes are not touched.

---

## Architecture overview

### Before (current)

```
task/failed fires propagate_task_failure_fn
    │
    ├── TaskPropagationService.propagate_failure
    │     ├── update_node_status(FAILED)                  ← terminal node
    │     └── on_task_completed_or_failed(FAILED)
    │           ├── edges → INVALIDATED
    │           ├── managed targets   → stay PENDING      (manager adapts)
    │           └── static targets    → CANCELLED         ← divergence
    │
    ├── emit TaskCancelledEvent(cause="dep_invalidated")
    │     for each invalidated_target (static nodes only)
    │         └── cancel_orphan_subtasks_fn
    │               └── SubtaskCancellationService.cancel_orphans
    │                     (BFS children of the now-CANCELLED static node)
    │
    └── is_workflow_failed_v2 → True
        emit workflow/failed
```

### After (proposed)

```
task/failed fires propagate_task_failure_fn
    │
    ├── TaskPropagationService.propagate_failure
    │     ├── update_node_status(FAILED)                  ← terminal node
    │     └── on_task_completed_or_failed(FAILED)
    │           ├── edges → INVALIDATED
    │           ├── managed targets   → stay PENDING      (manager adapts)
    │           └── static targets    → stay PENDING      ← uniform
    │
    ├── invalidated_targets == []
    │   no TaskCancelledEvent emitted for dep-blocked siblings
    │
    └── is_workflow_failed_v2 → True   (FAILED node present)
        is_workflow_complete_v2 (new rule):
          any non-terminal node blocked by ≥1 INVALIDATED edge
          and zero PENDING incoming edges → counts as blocked
          when ALL non-terminal nodes are blocked → True
        emit workflow/failed
```

### `is_workflow_complete_v2` rule change

| Condition | Old result | New result |
|---|---|---|
| All nodes COMPLETED | True | True |
| All nodes terminal (COMPLETED + CANCELLED), no FAILED | True | True |
| Any node FAILED | False (is_workflow_failed_v2 handles) | False (unchanged) |
| FAILED node + static PENDING siblings (new case) | hang (never True) | True — siblings are blocked-by-failed |
| PENDING node with PENDING incoming edges | False | False (not blocked, still waiting) |

---

## Type / interface definitions

No new public types. Two functions change signatures (same signature, different
body):

```python
# ergon_core/ergon_core/core/runtime/execution/propagation.py

def is_workflow_complete_v2(session: Session, run_id: UUID) -> bool:
    """Workflow is complete when no non-terminal node can make progress.

    A node can make progress only if at least one of its incoming edges is
    PENDING (i.e. the upstream might yet succeed).  A node that has only
    INVALIDATED incoming edges is blocked and will never advance on its own.

    Rules:
      - Zero nodes → True (empty run completes immediately).
      - Any FAILED node → False (is_workflow_failed_v2 handles termination).
      - Any non-terminal node with ≥1 PENDING incoming edge → False.
      - Any non-terminal node with 0 PENDING incoming edges but ≥1 INVALIDATED
        incoming edge is "blocked-by-failed" and does NOT block completion.
      - All nodes terminal or blocked-by-failed → True.
    """
```

```python
def on_task_completed_or_failed(
    session: Session,
    run_id: UUID,
    node_id: UUID,
    terminal_status: str,
    *,
    graph_repo: WorkflowGraphRepository,
) -> tuple[list[UUID], list[UUID]]:
    """Handle a node reaching COMPLETED, FAILED, or CANCELLED.

    Returns (newly_ready_node_ids, invalidated_target_node_ids).

    - COMPLETED: outgoing edges → SATISFIED; targets with all deps satisfied
      → PENDING (ready).
    - FAILED / CANCELLED: outgoing edges → INVALIDATED. Targets stay PENDING
      regardless of parent_node_id. invalidated_target_node_ids is always []
      on the failure path (edges are invalidated; nodes are not touched).

    The asymmetry between COMPLETED re-activation (managed subtasks only) and
    failure propagation (uniform PENDING) is intentional and documented in
    docs/architecture/cross_cutting/error_propagation.md.
    """
```

---

## Full implementations

### Change 1 — `is_workflow_complete_v2` (new body)

```python
# ergon_core/ergon_core/core/runtime/execution/propagation.py

def is_workflow_complete_v2(session: Session, run_id: UUID) -> bool:
    """Workflow is complete when no non-terminal node can make progress.

    See RFC docs/rfcs/active/2026-04-17-static-sibling-failure-semantics.md
    for the full rule description and rationale.
    """
    nodes = list(
        session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all()
    )
    if not nodes:
        return True

    node_by_id = {n.id: n for n in nodes}

    # Any FAILED node means this is a failed workflow, not a completed one.
    if any(n.status == FAILED for n in nodes):
        return False

    non_terminal = [n for n in nodes if n.status not in TERMINAL_STATUSES]
    if not non_terminal:
        # All nodes are terminal and none FAILED → completed.
        return True

    # For each non-terminal node, check whether it has a PENDING incoming edge.
    # If it does, it can still make progress → workflow is not complete.
    # If all its incoming edges are INVALIDATED → it is blocked-by-failed and
    # does not prevent completion.
    all_edges = list(
        session.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)).all()
    )
    incoming_by_node: dict[UUID, list[RunGraphEdge]] = {}
    for edge in all_edges:
        incoming_by_node.setdefault(edge.target_node_id, []).append(edge)

    for node in non_terminal:
        incoming = incoming_by_node.get(node.id, [])
        if not incoming:
            # Root node that is non-terminal and has no edges:
            # it is legitimately waiting (e.g. initial PENDING before first
            # task/ready is dispatched) or running.  Not blocked.
            return False
        has_pending_edge = any(e.status == EDGE_PENDING for e in incoming)
        if has_pending_edge:
            # At least one upstream is still reachable → not blocked.
            return False
        # All incoming edges are INVALIDATED (or SATISFIED, which would
        # only occur if a source completed but the node hasn't been marked
        # ready yet — transient, not a hang). Treat as blocked.

    # Every non-terminal node is blocked by invalidated deps.
    return True
```

### Change 2 — `on_task_completed_or_failed` failure branch (removal)

Exact unified diff against `propagation.py:505-527`:

```diff
-        if not is_success:
-            # Dynamic subtasks (parent_node_id set) are manager-owned.
-            # The manager polls via list_subtasks and decides whether to
-            # retry, cancel, or re-plan — so we leave the target PENDING
-            # and only invalidate the edge.  Static workflow nodes
-            # (parent_node_id is None) have no adaptive supervisor, so
-            # auto-cancel is the correct behaviour.
-            if candidate_node.parent_node_id is not None:
-                continue
-
-            graph_repo.update_node_status(
-                session,
-                run_id=run_id,
-                node_id=candidate_id,
-                new_status=CANCELLED,
-                meta=MutationMeta(
-                    actor="system:propagation",
-                    reason=f"dependency {node_id} {terminal_status}",
-                ),
-                only_if_not_terminal=True,
-            )
-            invalidated.append(candidate_id)
-            continue
+        if not is_success:
+            # Both managed subtasks (parent_node_id set) and static workflow
+            # nodes (parent_node_id is None) stay PENDING.  Failure is a
+            # signal for an adaptive planner, not a reason to auto-cancel.
+            # The edge is already INVALIDATED above.  is_workflow_complete_v2
+            # uses the blocked-by-failed rule to detect when the run is done.
+            # See RFC docs/rfcs/active/2026-04-17-static-sibling-failure-semantics.md
+            continue
```

After this change the `invalidated` list is always `[]` on the failure path.
The `invalidated_targets` returned by `on_task_completed_or_failed` for a
FAILED source is an empty list. `propagate_task_failure_fn` already iterates
`propagation.invalidated_targets` to emit `TaskCancelledEvent`; an empty list
means no events are emitted, which is correct.

### Change 2 full replacement — `on_task_completed_or_failed` failure block

Full function body after edit (lines 438-586 become):

```python
def on_task_completed_or_failed(
    session: Session,
    run_id: UUID,
    node_id: UUID,
    terminal_status: str,
    *,
    graph_repo: WorkflowGraphRepository,
) -> tuple[list[UUID], list[UUID]]:
    """Handle a node reaching COMPLETED, FAILED, or CANCELLED.

    Returns (newly_ready_node_ids, invalidated_target_node_ids).

    - COMPLETED: outgoing edges → SATISFIED; targets with all deps satisfied
      → PENDING (ready).
    - FAILED / CANCELLED: outgoing edges → INVALIDATED. All downstream
      candidates stay PENDING regardless of parent_node_id.
      invalidated_target_node_ids is always [] on the failure path.

    Precondition: node_id is already in terminal_status before calling.
    The node's own status is NOT written here — only edge statuses and
    downstream candidate statuses are updated.
    """
    is_success = terminal_status == TaskExecutionStatus.COMPLETED

    outgoing = list(
        session.exec(
            select(RunGraphEdge).where(
                RunGraphEdge.run_id == run_id,
                RunGraphEdge.source_node_id == node_id,
            )
        ).all()
    )

    edge_status = EDGE_SATISFIED if is_success else EDGE_INVALIDATED
    for edge in outgoing:
        graph_repo.update_edge_status(
            session,
            run_id=run_id,
            edge_id=edge.id,
            new_status=edge_status,
            meta=_PROPAGATION_META,
        )

    candidate_node_ids = {e.target_node_id for e in outgoing}

    newly_ready: list[UUID] = []
    invalidated: list[UUID] = []

    for candidate_id in candidate_node_ids:
        candidate_node = session.get(RunGraphNode, candidate_id)
        if candidate_node is None:
            continue
        if candidate_node.status in TERMINAL_STATUSES and candidate_node.status != CANCELLED:
            continue
        if candidate_node.status == CANCELLED and not is_success:
            continue

        if not is_success:
            # Both managed subtasks and static workflow nodes stay PENDING.
            # Failure is a signal for an adaptive planner; is_workflow_complete_v2
            # uses the blocked-by-failed rule to detect run termination.
            continue

        # Source completed — check if this candidate can become READY.
        #
        # Eligibility:
        #   - PENDING (first activation): normal case.
        #   - CANCELLED managed subtask (parent_node_id is not None):
        #     re-activation after the manager or an upstream restart
        #     invalidated it.
        #   - CANCELLED static workflow node (parent_node_id is None):
        #     NOT re-activated — no supervisor to adapt.
        #
        # Everything else (COMPLETED, FAILED, RUNNING) is skipped.
        status = candidate_node.status
        is_managed_subtask = candidate_node.parent_node_id is not None
        is_pending = status == TaskExecutionStatus.PENDING
        is_reactivatable_cancelled = status == CANCELLED and is_managed_subtask

        if not (is_pending or is_reactivatable_cancelled):
            continue

        incoming = list(
            session.exec(
                select(RunGraphEdge).where(
                    RunGraphEdge.run_id == run_id,
                    RunGraphEdge.target_node_id == candidate_id,
                )
            ).all()
        )

        source_nodes = [session.get(RunGraphNode, e.source_node_id) for e in incoming]
        if all(n is not None and n.status == TaskExecutionStatus.COMPLETED for n in source_nodes):
            reason = (
                f"all dependencies satisfied after {node_id}"
                if is_pending
                else f"re-activating cancelled subtask after {node_id}"
            )
            graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=candidate_id,
                new_status=TaskExecutionStatus.PENDING,
                meta=MutationMeta(
                    actor="system:propagation",
                    reason=reason,
                ),
                only_if_not_terminal=False,
            )
            newly_ready.append(candidate_id)

    session.commit()
    return newly_ready, invalidated
```

---

## Exact diffs for modified files

### `ergon_core/ergon_core/core/runtime/execution/propagation.py`

**Hunk 1** — Replace `is_workflow_complete_v2` body (lines 594-601):

```diff
-def is_workflow_complete_v2(session: Session, run_id: UUID) -> bool:
-    """Every node terminal; zero FAILED. CANCELLED is neutral."""
-    statuses = list(
-        session.exec(select(RunGraphNode.status).where(RunGraphNode.run_id == run_id)).all()
-    )
-    if not statuses:
-        return True
-    return all(s in TERMINAL_STATUSES for s in statuses) and not any(s == FAILED for s in statuses)
+def is_workflow_complete_v2(session: Session, run_id: UUID) -> bool:
+    """Workflow is complete when no non-terminal node can make progress.
+
+    A node is blocked-by-failed when all its incoming edges are INVALIDATED.
+    Blocked-by-failed nodes do not prevent completion.
+    Any FAILED node → False (is_workflow_failed_v2 handles termination).
+    """
+    nodes = list(
+        session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all()
+    )
+    if not nodes:
+        return True
+    if any(n.status == FAILED for n in nodes):
+        return False
+    non_terminal = [n for n in nodes if n.status not in TERMINAL_STATUSES]
+    if not non_terminal:
+        return True
+    all_edges = list(
+        session.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)).all()
+    )
+    incoming_by_node: dict[UUID, list[RunGraphEdge]] = {}
+    for edge in all_edges:
+        incoming_by_node.setdefault(edge.target_node_id, []).append(edge)
+    for node in non_terminal:
+        incoming = incoming_by_node.get(node.id, [])
+        if not incoming:
+            return False
+        if any(e.status == EDGE_PENDING for e in incoming):
+            return False
+    return True
```

**Hunk 2** — Remove static auto-cancel branch (lines 505-527):

```diff
         if not is_success:
-            # Dynamic subtasks (parent_node_id set) are manager-owned.
-            # The manager polls via list_subtasks and decides whether to
-            # retry, cancel, or re-plan — so we leave the target PENDING
-            # and only invalidate the edge.  Static workflow nodes
-            # (parent_node_id is None) have no adaptive supervisor, so
-            # auto-cancel is the correct behaviour.
-            if candidate_node.parent_node_id is not None:
-                continue
-
-            graph_repo.update_node_status(
-                session,
-                run_id=run_id,
-                node_id=candidate_id,
-                new_status=CANCELLED,
-                meta=MutationMeta(
-                    actor="system:propagation",
-                    reason=f"dependency {node_id} {terminal_status}",
-                ),
-                only_if_not_terminal=True,
-            )
-            invalidated.append(candidate_id)
-            continue
+            # Both managed subtasks and static workflow nodes stay PENDING.
+            # is_workflow_complete_v2 uses the blocked-by-failed edge rule
+            # to detect run termination without requiring auto-cancel.
+            continue
```

No other files in the production path require changes for this RFC. The
`propagate_task_failure_fn` (`propagate_execution.py:137-200`) already iterates
`propagation.invalidated_targets`; an empty list means no `TaskCancelledEvent`
is emitted, which is the correct new behavior.

---

## Package structure

No new packages. Changes are confined to one source file and three test files.

---

## Implementation order

| Step | PR | What | Files touched |
|---|---|---|---|
| 1 | PR 1 | Add `is_blocked_by_failed` helper predicate (private, used by `is_workflow_complete_v2`) | `propagation.py` |
| 2 | PR 1 | Rewrite `is_workflow_complete_v2` with the blocked-chain rule | `propagation.py` |
| 3 | PR 1 | Add `TestBlockedChainCompletion` class to `test_propagation_graph_native.py` | `tests/state/test_propagation_graph_native.py` |
| 4 | PR 1 | Verify existing `TestIsWorkflowCompleteV2` tests still pass (CANCELLED-as-terminal and RUNNING cases unchanged) | no changes |
| 5 | PR 2 | Remove static auto-cancel branch from `on_task_completed_or_failed` | `propagation.py` |
| 6 | PR 2 | Rewrite `TestStaticNodeAutoCancel` → `TestStaticNodeStaysPending` in `test_dep_failure_cascade.py` | `tests/state/test_dep_failure_cascade.py` |
| 7 | PR 2 | Invert `test_mixed_static_and_dynamic_targets` assertion for static node (PENDING not CANCELLED) | `tests/state/test_dep_failure_cascade.py` |
| 8 | PR 2 | Add `TestWorkflowCompleteOnBlockedChain` integration test: FAILED node + PENDING-blocked siblings → workflow terminates via `propagate_failure` path | `tests/state/test_dep_failure_cascade.py` |
| 9 | PR 2 | Audit remaining tests for implicit dependency on auto-cancel (see Testing section) | `tests/state/` |

Steps 1–4 land as **PR 1** (safe: new completion logic is tested before the
semantic flip). Steps 5–9 land as **PR 2** (semantic flip, test rewrites).

---

## File map

### MODIFY

| File | Changes |
|---|---|
| `ergon_core/ergon_core/core/runtime/execution/propagation.py` | (1) Replace `is_workflow_complete_v2` body with blocked-chain rule. (2) Remove static auto-cancel branch from `on_task_completed_or_failed` (lines 505-527). |
| `tests/state/test_dep_failure_cascade.py` | Rewrite `TestStaticNodeAutoCancel` → `TestStaticNodeStaysPending`; invert `test_mixed_static_and_dynamic_targets` assertion for static node; add `TestWorkflowCompleteOnBlockedChain`. |
| `tests/state/test_propagation_graph_native.py` | Add `TestBlockedChainCompletion` class for new `is_workflow_complete_v2` rule. |

### ADD

None. All changes are in-place rewrites.

---

## Testing approach

### Unit — `TestBlockedChainCompletion` (PR 1, `test_propagation_graph_native.py`)

```python
class TestBlockedChainCompletion:
    """is_workflow_complete_v2 with the blocked-by-failed rule."""

    def test_pending_node_with_invalidated_edges_does_not_block(self, session: Session):
        """A fails. B is PENDING with only an INVALIDATED A->B edge.
        Workflow should be complete (blocked-by-failed)."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.FAILED)
        b = _add_node(repo, session, run_id, "B", status=TaskExecutionStatus.PENDING)
        repo.add_edge(
            session, run_id,
            source_node_id=a.id, target_node_id=b.id,
            status="invalidated", meta=META,
        )
        session.flush()

        assert is_workflow_complete_v2(session, run_id) is False
        # is_workflow_failed_v2 returns True; completion check must be False
        # so the caller emits workflow/failed rather than workflow/completed.

    def test_failed_node_alone_blocks_complete(self, session: Session):
        """A FAILED node alone → is_workflow_complete_v2 is False."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.FAILED)
        session.flush()

        assert is_workflow_complete_v2(session, run_id) is False

    def test_all_completed_no_failed_returns_true(self, session: Session):
        """Original happy path unchanged."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.COMPLETED)
        _add_node(repo, session, run_id, "B", status=TaskExecutionStatus.COMPLETED)
        session.flush()

        assert is_workflow_complete_v2(session, run_id) is True

    def test_pending_node_with_pending_edge_not_complete(self, session: Session):
        """B has a PENDING incoming edge (upstream still running) → not complete."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.RUNNING)
        b = _add_node(repo, session, run_id, "B", status=TaskExecutionStatus.PENDING)
        repo.add_edge(
            session, run_id,
            source_node_id=a.id, target_node_id=b.id,
            status="pending", meta=META,
        )
        session.flush()

        assert is_workflow_complete_v2(session, run_id) is False

    def test_chain_failure_all_blocked_pending(self, session: Session):
        """A fails. B PENDING (A->B invalidated). C PENDING (B->C pending).
        C still has a PENDING edge so run is not complete."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.FAILED)
        b = _add_node(repo, session, run_id, "B", status=TaskExecutionStatus.PENDING)
        c = _add_node(repo, session, run_id, "C", status=TaskExecutionStatus.PENDING)
        repo.add_edge(
            session, run_id,
            source_node_id=a.id, target_node_id=b.id,
            status="invalidated", meta=META,
        )
        repo.add_edge(
            session, run_id,
            source_node_id=b.id, target_node_id=c.id,
            status="pending", meta=META,
        )
        session.flush()

        # C has a PENDING edge from B → not fully blocked → not complete
        assert is_workflow_complete_v2(session, run_id) is False
```

**Note on the first test:** `is_workflow_complete_v2` returns `False` because
`FAILED ∈ nodes`. The caller (`TaskPropagationService.propagate_failure`) checks
`is_workflow_failed_v2` first (line 143); that returns `True`, and
`WorkflowTerminalState.FAILED` is set. `is_workflow_complete_v2` is not the
primary finalization path on failure. The test documents the invariant that the
two checks do not conflict.

### Unit — `TestStaticNodeStaysPending` (PR 2, rewrite of `TestStaticNodeAutoCancel`)

```python
class TestStaticNodeStaysPending:
    """Static workflow nodes stay PENDING when a dependency fails."""

    def test_failure_leaves_static_downstream_pending(self, session: Session):
        """A -> B, A -> C (all static). A fails. B and C stay PENDING."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.FAILED)
        b = _add_node(repo, session, run_id, "B")
        c = _add_node(repo, session, run_id, "C")

        repo.add_edge(session, run_id, source_node_id=a.id, target_node_id=b.id,
                      status="pending", meta=META)
        repo.add_edge(session, run_id, source_node_id=a.id, target_node_id=c.id,
                      status="pending", meta=META)
        session.flush()

        _ready, invalidated = on_task_completed_or_failed(
            session, run_id, a.id, TaskExecutionStatus.FAILED, graph_repo=repo,
        )

        assert invalidated == []  # no auto-cancel

        b_row = session.get(RunGraphNode, b.id)
        c_row = session.get(RunGraphNode, c.id)
        assert b_row is not None and b_row.status == TaskExecutionStatus.PENDING
        assert c_row is not None and c_row.status == TaskExecutionStatus.PENDING

    def test_edges_are_still_invalidated(self, session: Session):
        """Edge state is INVALIDATED even though the target node stays PENDING."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.FAILED)
        b = _add_node(repo, session, run_id, "B")
        edge = repo.add_edge(session, run_id, source_node_id=a.id, target_node_id=b.id,
                              status="pending", meta=META)
        session.flush()

        on_task_completed_or_failed(
            session, run_id, a.id, TaskExecutionStatus.FAILED, graph_repo=repo,
        )

        from ergon_core.core.persistence.graph.models import RunGraphEdge
        edge_row = session.get(RunGraphEdge, edge.id)
        assert edge_row is not None
        assert edge_row.status == "invalidated"

    def test_managed_subtask_regression(self, session: Session):
        """Managed subtask behavior is unchanged: stays PENDING, not in invalidated."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        manager = _add_node(repo, session, run_id, "manager",
                             status=TaskExecutionStatus.RUNNING)
        a = _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.FAILED,
                      parent_node_id=manager.id, level=1)
        b = _add_node(repo, session, run_id, "B", parent_node_id=manager.id, level=1)
        repo.add_edge(session, run_id, source_node_id=a.id, target_node_id=b.id,
                      status="pending", meta=META)
        session.flush()

        _ready, invalidated = on_task_completed_or_failed(
            session, run_id, a.id, TaskExecutionStatus.FAILED, graph_repo=repo,
        )

        assert b.id not in invalidated
        b_row = session.get(RunGraphNode, b.id)
        assert b_row is not None and b_row.status == TaskExecutionStatus.PENDING


class TestWorkflowCompleteOnBlockedChain:
    """After the semantic flip, propagate_failure terminates runs via
    is_workflow_failed_v2, not is_workflow_complete_v2."""

    def test_propagate_failure_detects_failed_state(self, session: Session):
        """TaskPropagationService.propagate_failure on A with static B downstream
        returns WorkflowTerminalState.FAILED (not NONE)."""
        from ergon_core.core.runtime.services.task_propagation_service import (
            TaskPropagationService,
        )
        from ergon_core.core.runtime.services.orchestration_dto import (
            PropagateTaskCompletionCommand,
            WorkflowTerminalState,
        )

        # Build graph via repo (no definition tables)
        repo = WorkflowGraphRepository()
        run_id = uuid4()
        def_id = uuid4()

        a_node = repo.add_node(session, run_id, task_key="A", instance_key="i0",
                                description="A", status=TaskExecutionStatus.RUNNING, meta=META)
        b_node = repo.add_node(session, run_id, task_key="B", instance_key="i0",
                                description="B", status=TaskExecutionStatus.PENDING, meta=META)
        repo.add_edge(session, run_id, source_node_id=a_node.id, target_node_id=b_node.id,
                      status="pending", meta=META)
        session.commit()

        svc = TaskPropagationService()
        result = svc.propagate_failure(
            PropagateTaskCompletionCommand(
                run_id=run_id,
                definition_id=def_id,
                task_id=a_node.definition_task_id or uuid4(),
                execution_id=uuid4(),
                node_id=a_node.id,
            )
        )

        assert result.workflow_terminal_state == WorkflowTerminalState.FAILED
        assert result.invalidated_targets == []
```

### Regression guard

All existing tests in `tests/state/test_propagation_reactivation.py` must pass
unchanged — they test the CANCELLED managed-subtask re-activation path, which
is untouched. `test_static_cancelled_does_not_reactivate` (line 176) remains
correct: a CANCELLED static node (reached by some prior path, not by this
RFC's change) stays CANCELLED on the success path.

---

## Trace / observability impact

### Spans

`task.propagate` span in `propagate_task_failure_fn` (emitted from
`propagate_execution.py:119-133`) already carries:

```python
"newly_ready_tasks": len(propagation.ready_tasks),    # always 0 on failure path
"workflow_terminal": str(propagation.workflow_terminal_state),
```

After the change, `workflow_terminal` will be `"failed"` where it previously
may have been `"failed"` (unchanged for runs where the failed node itself was
the last to trigger finalization). No attribute schema change.

### Logs

`propagate_task_failure_fn` logs:
```
task-failure-propagate run_id=... task_id=... error=...
```
No change.

`on_task_completed_or_failed` has no structured logging of its own; the
auto-cancel branch being removed produces no loss of log signal.

### Dashboard events

`propagate_task_failure_fn` currently emits `TaskCancelledEvent(cause="dep_invalidated")`
for each entry in `invalidated_targets`. Under the new semantics, that list is
empty for static nodes; no `TaskCancelledEvent` fires for dep-blocked siblings.
The dashboard will show those nodes as PENDING rather than CANCELLED.

The dashboard badge for "blocked by failed dep" versus "cancelled" is a
follow-up (noted in Open Questions). This RFC does not add a new node status —
PENDING remains the node status. The edge INVALIDATED state is readable via the
mutations log if dashboard wants to distinguish.

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `is_workflow_complete_v2` edge-query cost | PR 1 adds a full `RunGraphEdge` scan per finalization check. Propagation runs once per task terminal; edge count ≤ task count. Acceptable at experiment scale. | Monitor `task.propagate` span duration. If P99 degrades, add `GROUP BY target_node_id` aggregate query. |
| Root PENDING node (no incoming edges) with failing chain elsewhere in DAG | `is_workflow_complete_v2` returns `False` (root has no edges → treated as not blocked). Correct: root is still runnable. | Covered by `test_pending_node_with_pending_edge_not_complete`. |
| In-flight runs at deploy: nodes already CANCELLED by old path | CANCELLED is absorbing. Existing CANCELLED nodes stay CANCELLED. New runs get the new semantic. No hybrid run possible mid-task. | Acceptable; document in migration note. |
| Tests that assert `TaskCancelledEvent` is emitted for dep-blocked static nodes | `test_propagation_graph_native.py` and `test_dep_failure_cascade.py` have explicit assertions on `invalidated` list contents | PR 2 rewrites those assertions. Grep: `dep_invalidated` in `tests/` before merging PR 2. |
| `cancel_orphans_on_failed_fn` fires but `SubtaskCancellationService.cancel_orphans` finds nothing to cancel | No-op; `cancel_orphans` uses BFS on `parent_node_id` — static nodes with `parent_node_id=None` are never BFS roots. | Verified: `cancel_orphan_subtasks.py:98-107` passes `parent_node_id=payload.node_id` to the service; static siblings are not children of the failing node. No behavior change needed. |
| `propagate_task_failure_fn` still emits `TaskCancelledEvent` via the `for inv_node_id in propagation.invalidated_targets` loop | After Change 2, `invalidated_targets == []` so the loop body never executes. | Zero code change needed in `propagate_execution.py`. Confirmed by inspection of lines 164-176. |
| Interaction with `SubtaskCancellationService` assumption | Today `cancel_orphans_on_failed_fn` fires because `TaskFailedEvent` triggers it. It walks `parent_node_id` children of the FAILED node, not the PENDING siblings. The siblings' subtrees are unaffected. | Confirmed: `cancel_orphan_subtasks.py:98-107` passes the FAILED node's `node_id` as `parent_node_id`. Static siblings (`parent_node_id=None`) are not children of the failed node. No change to `cancel_orphans_on_*_fn` needed. |

---

## Invariants affected

### `docs/architecture/02_runtime_lifecycle.md#invariants`

**Section 4, Known limits, bullet 1 (line 116):** Remove the bullet entirely on
merge — it describes the divergence this RFC closes.

**Section 4, Invariants:** Add new invariant after existing invariant 2:

> **Failure propagation is uniform across static and managed nodes.** When a
> node reaches FAILED or CANCELLED, all outgoing edges become INVALIDATED and
> all downstream targets stay PENDING — regardless of `parent_node_id`. The
> only asymmetry is re-activation on the success path: managed subtasks
> (`parent_node_id is not None`) can re-activate to PENDING when all deps
> re-satisfy; static workflow nodes cannot. See
> `ergon_core/core/runtime/execution/propagation.py::on_task_completed_or_failed`
> for the enforcement point.

**Section 5, Extension points:** Add a bullet:

> **Blocking-chain completion seam.** `is_workflow_complete_v2` is the single
> check for "is the workflow done without a FAILED node". Future features
> (retry policies, planners) that want to unblock PENDING-blocked nodes do so
> by satisfying or replacing INVALIDATED edges — not by patching the completion
> check. The completion check must never be taught about domain-specific states;
> it must stay a pure graph query.

### `docs/architecture/cross_cutting/error_propagation.md`

**"Current behavior" section:** Move items 1-5 to "Before 2026-04-17". After
merge, "Current behavior" becomes:

1. Task COMPLETED → dependents with all deps satisfied → PENDING. Correct.
2. Task FAILED or CANCELLED, any downstream target (managed or static) → stays
   PENDING, edge → INVALIDATED. Uniform fractal-OS semantics.
3. Parent terminal → `cancel_orphans_on_*_fn` cancels the full subtask
   subtree. Correct.
4. CANCELLED managed subtask with re-satisfied deps → re-activates to PENDING.
   Static workflow CANCELLED nodes do NOT re-activate.

**"Intended behavior" section:** Delete (it is now current behavior).

**Control flow diagram:** Update the `static sibling target` line from
`AUTO-CANCELLED (CURRENT)` to `STAY PENDING (uniform)`.

**Invariants section:** Add:
> - Failure propagation is uniform: all downstream candidates stay PENDING
>   on a failed/cancelled source, regardless of `parent_node_id`.

**Anti-patterns section:** Update:
> - **Assuming "failed → children cancel" today.** No longer true for ANY
>   target — neither static nor managed. Check edge status (`INVALIDATED`) to
>   determine whether a node's dependency chain has failed.

---

## Alternatives considered

- **Keep static auto-cancel; add a config flag per-benchmark.** Rejected: two
  semantics in parallel makes every PR reviewer's life harder; the system owner
  wants uniform.
- **Auto-cancel static siblings but also emit a signal to a future planner.**
  Rejected: no planner exists today; speculative coupling. Adding a signal
  channel we do not consume ages into dead code.
- **Leave `is_workflow_complete_v2` as-is and rely on run-level timeouts.**
  Rejected: timeouts are a crutch; blocked-chain detection is a correctness
  invariant. Timeouts also make it impossible to distinguish "hung" from
  "legitimately slow."
- **Move the gate to a strategy object on the run.** Rejected: same problem as
  the config flag, with extra indirection.
- **Add a new node status `BLOCKED`.** Rejected: `TaskExecutionStatus` is
  frozen (architecture doc §3.2). Adding a status requires coordinated changes
  across propagation, evaluator gating, finalization, and dashboard. The blocked
  state is fully encodable as PENDING + all-INVALIDATED incoming edges; no new
  status needed.

---

## Open questions

- **Transitive closure definition.** "Blocked by a failed-dependency chain" is
  defined as: the node has ≥1 INVALIDATED incoming edge and 0 PENDING incoming
  edges. This is a single-hop check, not transitive. A deeper chain (A fails,
  B stays PENDING with INVALIDATED edge from A, C stays PENDING with PENDING
  edge from B) is NOT blocked because C still has a PENDING edge. This is
  correct: B may yet be unblocked by a planner, which would satisfy B's dep and
  allow C to activate. Transitive closure is not needed and would be wrong.

- **Dashboard badge for PENDING-blocked.** A node that is PENDING with only
  INVALIDATED incoming edges looks identical to a legitimately waiting PENDING
  node in the current dashboard. Operators need a way to distinguish. Specific
  event name and badge design TBD; recommended as a follow-up PR after this
  RFC lands. The INVALIDATED edge status is available via the mutations log
  today.

- **Dashboard event for "workflow finalized due to blocked chains".** The
  `WorkflowFailedEvent` covers this case (run ends in FAILED state). A separate
  event may be useful for UX. TBD.

- **Mixed static + managed siblings test.** Covered in
  `TestStaticNodeStaysPending::test_managed_subtask_regression` above and by
  the existing `TestDynamicSubtaskNoAutoCancel::test_mixed_static_and_dynamic_targets`
  after the assertion inversion in PR 2.

- **Interaction with `SubtaskCancellationService`.** Confirmed no handler
  assumes `cancel_orphans` fires for dep-failed static siblings (see Risks
  table). The three `cancel_orphans_on_*_fn` functions pass the terminal
  node's own `node_id` as `parent_node_id`; static siblings are not children.

---

## On acceptance

- Update `docs/architecture/02_runtime_lifecycle.md#invariants` — add the
  "failure propagation is UNIFORM" invariant; remove the Known Limits bullet
  for static auto-cancel.
- Update `docs/architecture/02_runtime_lifecycle.md#extension-points` — add
  blocking-chain completion seam bullet.
- Update `docs/architecture/cross_cutting/error_propagation.md` — merge
  intended-behavior into current-behavior; update control flow diagram; add
  invariant; update anti-pattern.
- Link the implementation plan at
  `docs/superpowers/plans/2026-04-17-static-sibling-pending.md`.
- Move this file to `docs/rfcs/accepted/`.
