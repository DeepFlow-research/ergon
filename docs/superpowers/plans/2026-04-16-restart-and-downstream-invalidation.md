# Restart Task & Downstream Invalidation

> **Depends on:** `2026-04-16-subtask-lifecycle.md` (containment model, cancel cascade, dep edges).
> **Branch:** `feature/type-tightening-prep`

## Problem

A manager agent cannot re-run a completed or failed subtask. Today the only recovery path is "cancel the old node, create a new one" — but that orphans existing dependency edges. The manager has to rebuild the entire subgraph.

More critically: if D is COMPLETED and its downstream E is in-progress, and the manager decides D's output is wrong and needs re-running, there is no way to:
1. Reset D back to PENDING
2. Cancel E (it's running against stale input)
3. Reset E to PENDING so it re-runs after D completes again

This is the "downstream invalidation on re-run" pattern (see Fractal OS task propagation).

## Test Scenario (E2E integration test)

This is the acceptance test — the north star that task propagation logic doesn't get broken. It runs in CI as a state test (SQLite, no Docker, no sleeps).

### Graph topology

```
Manager (L1, RUNNING)
├── Graph 1 — Diamond with fan-in:
│   A ──→ B ──→ F
│   A ──→ C ──→ F        (F has TWO incoming edges: from B and from C)
│
├── Graph 2 — Chain (3-deep, for recursive invalidation):
│   D ──→ E ──→ G
│
└── H (independent leaf, no deps — sanity baseline)
```

8 child nodes. Created via three `plan_subtasks` calls (Graph 1, Graph 2, H standalone via `add_subtask`).

### Step-by-step (15 steps)

| Step | Action | Assert | Tests |
|------|--------|--------|-------|
| 1 | Manager spawns Graph 1 (A→B, A→C, B→F, C→F), Graph 2 (D→E→G), and H | 8 child nodes. A, D, H are roots (PENDING, no deps). B, C, E, F, G blocked. | Creation, edge wiring |
| 2 | A completes | B and C become READY. F stays PENDING (not all deps met). | **Fan-out**: completion unblocks multiple targets |
| 3 | B completes | F stays PENDING (C not done yet). | **Fan-in**: partial dep satisfaction does NOT unblock |
| 4 | C completes | F becomes READY (all deps met). | **Fan-in**: full dep satisfaction unblocks |
| 5 | F completes | Graph 1 fully done. | Normal completion |
| 6 | D completes → E becomes READY | E is READY. G stays PENDING. | Chain propagation |
| 7 | E starts running | E is RUNNING. | Status transition |
| 8 | Manager cancels E (while RUNNING) | E is CANCELLED. G stays PENDING (managed subtask, not auto-cancelled). Edge E→G INVALIDATED. | **Cancel running node**, managed subtask no-cascade |
| 9 | Manager restarts E (from CANCELLED) | E is PENDING. Edge E→G reset to EDGE_PENDING. task/ready emitted for E. | **Restart from CANCELLED**, edge reset |
| 10 | E completes → G becomes READY | G is READY. | Re-propagation after restart |
| 11 | G completes | Graph 2 fully done. | Normal completion |
| 12 | Manager restarts B (B was COMPLETED, F was COMPLETED) | B is PENDING. **F is invalidated** (stale input): F goes CANCELLED, edges B→F and C→F reset to EDGE_PENDING. G unaffected (different graph). | **Restart with completed downstream**, deep invalidation, cross-graph isolation |
| 13 | B completes again | **F re-activates**: C is still COMPLETED, B now COMPLETED → all deps satisfied → F becomes READY. | **Fan-in re-activation**: CANCELLED target re-activates when all deps re-satisfied |
| 14 | F completes again | Graph 1 re-done. | Re-propagation after invalidation |
| 15 | H completes, manager completes | All 8 children + manager terminal. Zero FAILED. Workflow COMPLETED. | **Workflow terminal detection** |

### What this covers

| Pattern | Steps | Why it matters |
|---------|-------|----------------|
| Fan-out (one source → multiple targets) | 2 | Most basic propagation |
| Fan-in (multiple sources → one target) | 3, 4 | #1 source of propagation bugs — must wait for ALL deps |
| Diamond (fan-out + fan-in) | 2–5 | Where edge-counting bugs hide |
| Chain propagation (A→B→C) | 6, 10 | Multi-hop dependency |
| Cancel while RUNNING | 8 | Real-world manager behavior (not just cancelling PENDING) |
| Managed subtask no-cascade | 8 | Downstream stays PENDING, not auto-cancelled |
| Restart from CANCELLED | 9 | Terminal → PENDING, edge reset |
| Restart with completed downstream (deep invalidation) | 12 | The hard case: stale output must cascade |
| Fan-in re-activation | 13 | CANCELLED target re-activates when all deps re-satisfied |
| Cross-graph isolation | 12 | Restart in Graph 1 doesn't touch Graph 2 |
| Independent leaf | 15 | Node with no deps, no downstream — sanity |
| Workflow terminal | 15 | All terminal + zero FAILED = COMPLETED |

## Current State — What Works

| Operation | Works? | Code path |
|-----------|--------|-----------|
| `plan_subtasks` with dep edges | Yes | `TaskManagementService.plan_subtasks` |
| Cancel D, E stays PENDING | Yes | `on_task_completed_or_failed` skips managed subtasks |
| D completes → E becomes READY | Yes | `on_task_completed_or_failed(COMPLETED)` satisfies edges |
| Recursive cancel cascade | Yes | `SubtaskCancellationService.cancel_orphans` BFS |
| First-writer-wins guard | Yes | `update_node_status(only_if_not_terminal=True)` |
| Fan-in propagation | Yes | `on_task_completed_or_failed` checks ALL incoming source nodes |

## Gaps

### Gap 1: `restart_task` service method + tool

**No way to reset a terminal node back to PENDING.** The manager can cancel, refine, and add — but cannot restart.

Needed:
- `RestartTaskCommand(run_id, node_id)` DTO
- `RestartTaskResult(node_id, old_status)` DTO
- `TaskManagementService.restart_task()`:
  - Validate node is in TERMINAL_STATUSES (raise `TaskNotTerminalError` if not)
  - Call `_invalidate_downstream()` first (see Gap 2)
  - Reset node status to PENDING (unguarded `update_node_status`, `only_if_not_terminal=False`)
  - Reset all outgoing edges from this node to EDGE_PENDING
  - Emit `task/ready` event so the scheduler picks it up
  - Return result
- `SubtaskLifecycleToolkit._make_restart_task()` closure → 8th tool
- Tool signature: `restart_task(node_id: str) -> dict`

### Gap 2: Downstream invalidation on restart

**When a node is restarted, its downstream targets are running against stale input.** They must be cancelled and re-queued.

Needed — `_invalidate_downstream()` called by `restart_task` before resetting the node's own edges:

```
_invalidate_downstream(session, run_id, node_id, graph_repo):
    for each outgoing edge from node_id:
        reset edge to EDGE_PENDING
        target = edge.target_node
        if target is non-terminal (PENDING, READY, RUNNING):
            cancel target (it may be running against stale input)
            emit task/cancelled for cleanup
        if target is COMPLETED:
            # target's output is stale — cancel it too, then
            # reset its outgoing edges and recurse
            cancel target
            emit task/cancelled for cleanup
            recurse into target's outgoing edges
```

The recursion terminates because:
- The graph is a DAG (no cycles, enforced by Kahn's algorithm in `plan_subtasks`)
- We only recurse into COMPLETED targets (CANCELLED/FAILED have no stale output)

**Key semantic:** Restarting B resets B→F edge to PENDING, cancels F, and resets F's outgoing edges too. When B completes again, normal propagation re-satisfies the B→F edge. If C is still COMPLETED (the other fan-in source), F becomes READY.

### Gap 3: Re-activating a CANCELLED node via propagation

Currently `on_task_completed_or_failed(COMPLETED)` only unblocks PENDING targets:

```python
if candidate_node.status != TaskExecutionStatus.PENDING:
    continue
```

After step 12, F is CANCELLED (invalidated by B's restart). When B completes again in step 13, propagation needs to re-activate F. The check must also allow CANCELLED targets to become READY when ALL incoming edges are satisfied.

Change: when a source completes and the target is CANCELLED with all deps now satisfied, reset the target to PENDING and add it to `newly_ready`.

**Re-activation policy (decided):** Any CANCELLED managed subtask (parent_node_id set) re-activates when all deps are satisfied. If the manager explicitly cancelled a node and doesn't want it re-activated, it can re-cancel. This avoids needing a `cancel_cause` column on the node and keeps the propagation logic simple.

Static workflow nodes (parent_node_id=None) do NOT re-activate — they have no supervisor to adapt.

### Gap 4: Widen `refine_task` to work on terminal nodes

Currently `refine_task` rejects any non-PENDING node:

```python
if node.status != PENDING:
    raise TaskNotPendingError(command.node_id, node.status)
```

The manager should be able to edit a task's description or properties before restarting it. The composition is: `refine_task(D, new_description)` → `restart_task(D)`.

Change: allow `refine_task` on any status **except RUNNING** (the worker is actively using the description). PENDING, COMPLETED, FAILED, CANCELLED are all refinable.

This is a one-line change: `if node.status == RUNNING: raise TaskRunningError(...)`.

## File Map

### New files

| Path | Purpose |
|------|---------|
| `tests/state/test_restart_and_invalidation.py` | Unit tests for restart_task + downstream invalidation |
| `tests/state/test_propagation_reactivation.py` | Unit tests for CANCELLED → PENDING re-activation on dep satisfaction |
| `tests/state/test_manager_dag_scenario.py` | Full 15-step E2E scenario |

### Modified files

| Path | Change |
|------|--------|
| `ergon_core/.../services/task_management_dto.py` | Add `RestartTaskCommand`, `RestartTaskResult` |
| `ergon_core/.../services/task_management_service.py` | Add `restart_task()`, `_invalidate_downstream()`. Widen `refine_task` status check. |
| `ergon_core/.../execution/propagation.py` | `on_task_completed_or_failed`: allow CANCELLED managed subtasks to re-activate when all deps satisfied |
| `ergon_core/.../runtime/errors/delegation_errors.py` | Add `TaskNotTerminalError`, `TaskRunningError` |
| `ergon_builtins/.../tools/subtask_lifecycle_toolkit.py` | Add `_make_restart_task()`, update `get_tools()` to return 8 tools |

## Implementation Order

### Phase 1: Widen `refine_task` + restart_task (no downstream invalidation yet)

- [ ] Widen `refine_task`: change guard from `status != PENDING` to `status == RUNNING`
- [ ] Add `TaskNotTerminalError`, `TaskRunningError` to delegation_errors
- [ ] Add `RestartTaskCommand` / `RestartTaskResult` DTOs
- [ ] Implement `TaskManagementService.restart_task()`: validate terminal, reset node to PENDING, reset outgoing edges to EDGE_PENDING, emit task/ready
- [ ] Add `_make_restart_task()` to toolkit (8th tool)
- [ ] Unit test: restart from COMPLETED, FAILED, CANCELLED; reject restart of PENDING/RUNNING
- [ ] Unit test: outgoing edges reset to EDGE_PENDING
- [ ] Unit test: `refine_task` now works on COMPLETED/FAILED/CANCELLED, still rejects RUNNING

### Phase 2: Downstream invalidation

- [ ] Implement `_invalidate_downstream()` in task_management_service: walks outgoing edges, cancels non-terminal targets, recurses into completed targets
- [ ] Wire into `restart_task()` (called before edge reset)
- [ ] Unit test: restart D while E is RUNNING → E cancelled, edge D→E reset
- [ ] Unit test: restart D while E is COMPLETED → E cancelled, E's outgoing edges reset
- [ ] Unit test: deep chain D→E→G, restart D → E and G both invalidated
- [ ] Unit test: fan-in — restart B, F invalidated, but C→F edge also reset

### Phase 3: Re-activation of CANCELLED targets on dep satisfaction

- [ ] Modify `on_task_completed_or_failed(COMPLETED)`: for managed subtasks (parent_node_id set), check CANCELLED targets alongside PENDING
- [ ] When all incoming source nodes are COMPLETED for a CANCELLED managed subtask, reset to PENDING + add to newly_ready
- [ ] Unit test: D restarts, completes again → E (CANCELLED) re-activates
- [ ] Unit test: fan-in re-activation — B restarts, completes → F re-activates (C still COMPLETED)
- [ ] Unit test: static workflow CANCELLED node does NOT re-activate (no parent_node_id)
- [ ] Unit test: user-cancelled node with all deps satisfied — re-activates (manager can re-cancel)

### Phase 4: E2E integration test

- [ ] Write `test_manager_dag_scenario.py` with the full 15-step scenario
- [ ] Uses `TaskManagementService` + `WorkflowGraphRepository` directly (no Inngest, no stubs sleeping)
- [ ] Simulates worker completion via `graph_repo.update_node_status()` + `on_task_completed_or_failed()`
- [ ] All assertions from the 15-step scenario table
- [ ] Runs in `tests/state/` (SQLite, per-test transaction rollback)
- [ ] Wire into CI via existing `pnpm run test:be:state`

## Open Questions

1. **Concurrent restart + completion race:** If the manager calls `restart_task(D)` at the same moment D's worker reports completion, who wins? The restart should win (manager's intent is explicit), but we need to think about the edge reset happening after propagation already satisfied the edges. Likely solved by: `restart_task` runs in the manager's session, propagation runs in the Inngest step's session. The DB transaction that commits first wins. If propagation committed first (edges satisfied), restart will re-reset them. If restart committed first, propagation sees the node as PENDING and skips.

2. **Event semantics for restart:** Should `restart_task` emit a new event type (`task/restarted`) or reuse `task/ready`? A new event type gives better observability in Inngest dashboard but adds another function to register. Recommendation: reuse `task/ready` — the scheduler doesn't need to distinguish "first run" from "re-run".

3. **Sandbox lifecycle on restart:** When a node is restarted, its downstream targets get `task/cancelled` events which trigger `cleanup_cancelled_task_fn` (sandbox teardown). The restarted node itself goes PENDING→RUNNING and gets a fresh sandbox via normal `execute_task_fn` dispatch. The old execution's sandbox for the restarted node is NOT explicitly cleaned up — it will be orphaned. We may want to emit `task/cancelled` for the restarted node too, just for sandbox cleanup, even though it's not really "cancelled". Or add a `task/restarted` event that triggers cleanup.

4. **`refine_task` on RUNNING — edge case:** A manager might want to refine a running task's description for the _next_ run (if it plans to restart it). Current plan blocks RUNNING. Alternative: allow refine on RUNNING but document that the current execution won't see the change. Keeping it blocked is safer for now.
