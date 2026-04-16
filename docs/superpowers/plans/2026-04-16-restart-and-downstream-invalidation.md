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

This is the acceptance test. A deterministic stub manager spawns two subgraphs and exercises every propagation path:

```
Manager (L1, RUNNING)
├── Graph 1: A → B, A → C     (plan_subtasks, A is root)
└── Graph 2: D → E             (plan_subtasks, D is root)
```

### Step-by-step

| Step | Action | Assert |
|------|--------|--------|
| 1 | Manager spawns Graph 1 (A→B, A→C) and Graph 2 (D→E) via two `plan_subtasks` calls | 5 child nodes created, all PENDING. A and D are roots (no deps). B, C, E blocked. |
| 2 | Stub workers complete A | A is COMPLETED. Edges A→B and A→C become SATISFIED. B and C become READY. |
| 3 | Stub workers complete B and C | B, C are COMPLETED. Graph 1 is fully done. |
| 4 | Manager cancels D | D is CANCELLED. E stays PENDING (managed subtask, not auto-cancelled). Edge D→E is INVALIDATED. |
| 5 | Manager restarts D | D is PENDING again. Edge D→E is reset to EDGE_PENDING. task/ready emitted for D. |
| 6 | Stub worker completes D | D is COMPLETED. Edge D→E becomes SATISFIED. E becomes READY. |
| 7 | Stub worker starts E | E is RUNNING. |
| 8 | Manager restarts D (while E is in-progress) | D is PENDING. E is CANCELLED (running against stale input). Edge D→E reset to EDGE_PENDING. |
| 9 | Stub worker completes D (again) | D is COMPLETED. Edge D→E becomes SATISFIED. E becomes READY (was CANCELLED, now PENDING). |
| 10 | Stub worker completes E | E is COMPLETED. All 5 children + manager are terminal. |
| 11 | Manager completes | Workflow is COMPLETED. |

### What this covers

- **Cancel without cascade** (step 4): managed subtask downstream stays PENDING
- **Restart from cancelled** (step 5): terminal → PENDING, edge reset
- **Normal dep propagation** (steps 2, 3, 6): completion satisfies edges, unblocks targets
- **Restart with downstream invalidation** (step 8): the hard case — D re-runs, E (in-progress) must be cancelled and re-queued
- **Re-propagation after restart** (step 9): D completes again, E unblocks again
- **Workflow terminal** (step 11): all nodes terminal, zero FAILED → COMPLETED

## Current State — What Works

| Operation | Works? | Code path |
|-----------|--------|-----------|
| `plan_subtasks` with dep edges | Yes | `TaskManagementService.plan_subtasks` |
| Cancel D, E stays PENDING | Yes | `on_task_completed_or_failed` skips managed subtasks |
| D completes → E becomes READY | Yes | `on_task_completed_or_failed(COMPLETED)` satisfies edges |
| Recursive cancel cascade | Yes | `SubtaskCancellationService.cancel_orphans` BFS |
| First-writer-wins guard | Yes | `update_node_status(only_if_not_terminal=True)` |

## Gaps

### Gap 1: `restart_task` service method + tool

**No way to reset a terminal node back to PENDING.** The manager can cancel, refine (pending only), and add — but cannot restart.

Needed:
- `RestartTaskCommand(run_id, node_id)` DTO
- `RestartTaskResult(node_id, old_status)` DTO
- `TaskManagementService.restart_task()`:
  - Validate node is in TERMINAL_STATUSES (raise if not)
  - Reset node status to PENDING (using unguarded `update_node_status`, i.e. `only_if_not_terminal=False`)
  - Reset all outgoing edges from this node to EDGE_PENDING
  - Emit `task/ready` event so the scheduler picks it up
  - Return result
- `SubtaskLifecycleToolkit._make_restart_task()` closure → 8th tool
- Tool signature: `restart_task(node_id: str) -> dict`

### Gap 2: Downstream invalidation on restart

**When a node is restarted, its downstream targets are running against stale input.** They must be cancelled and re-queued.

Needed — a `_invalidate_downstream` function called by `restart_task` after resetting the node:

```
_invalidate_downstream(session, run_id, node_id, graph_repo):
    for each outgoing edge from node_id:
        reset edge to EDGE_PENDING
        target = edge.target_node
        if target is non-terminal (PENDING, READY, RUNNING):
            cancel target (it may be running against stale input)
            # target stays cancelled until the restarted node completes
            # and propagation re-satisfies the edge
        if target is COMPLETED:
            # target's output is also stale — restart it recursively
            restart target → PENDING
            reset target's outgoing edges
            recurse into target's downstream
```

The recursion terminates because:
- CANCELLED/FAILED targets are already terminal and have no stale output to invalidate
- The graph is a DAG (no cycles, enforced by Kahn's algorithm in `plan_subtasks`)

**Key semantic:** Restarting D doesn't just cancel E — it also resets the D→E edge to PENDING so that when D completes again, normal propagation re-satisfies the edge and E becomes READY.

### Gap 3: Re-activating a CANCELLED node via propagation

Currently `on_task_completed_or_failed(COMPLETED)` only unblocks PENDING targets:

```python
if candidate_node.status != TaskExecutionStatus.PENDING:
    continue
```

After step 8, E is CANCELLED (invalidated by D's restart). When D completes again in step 9, propagation needs to re-activate E. This means the check needs to also allow CANCELLED targets to become READY — but only when ALL incoming edges are satisfied.

Change: when a source completes and the target is CANCELLED with all deps now satisfied, reset the target to PENDING and add it to `newly_ready`.

This is safe because:
- The target was cancelled by _us_ (downstream invalidation), not by the user
- All its deps are now satisfied, so it's valid to re-run
- The `only_if_not_terminal` guard is NOT used here — we deliberately write over CANCELLED

**Open question:** Should this re-activation only apply to nodes cancelled by downstream invalidation (`cause=dep_invalidated`)? Or should it apply to any CANCELLED node whose deps are all satisfied? The conservative approach is to add a `cancel_cause` field to `RunGraphNode` and only re-activate nodes cancelled by invalidation, not user-cancelled nodes. The simpler approach is to re-activate any CANCELLED node — the manager can always re-cancel if that's not what it wanted.

## File Map

### New files

| Path | Purpose |
|------|---------|
| `ergon_core/.../services/task_management_dto.py` | Add `RestartTaskCommand`, `RestartTaskResult` |
| `tests/state/test_restart_and_invalidation.py` | Unit tests for restart_task + downstream invalidation |
| `tests/state/test_propagation_reactivation.py` | Unit tests for CANCELLED → PENDING re-activation on dep satisfaction |
| `tests/state/test_manager_dag_scenario.py` | Full E2E scenario from the table above (11 steps) |

### Modified files

| Path | Change |
|------|--------|
| `ergon_core/.../services/task_management_service.py` | Add `restart_task()` method, `_invalidate_downstream()` helper |
| `ergon_core/.../execution/propagation.py` | `on_task_completed_or_failed`: allow CANCELLED targets to re-activate when all deps satisfied |
| `ergon_core/.../persistence/graph/status_conventions.py` | Possibly add `INVALIDATED_CANCEL_CAUSE` constant |
| `ergon_builtins/.../tools/subtask_lifecycle_toolkit.py` | Add `_make_restart_task()`, update `get_tools()` to return 8 tools |
| `ergon_core/.../services/task_management_dto.py` | Add DTOs |
| `ergon_core/.../runtime/errors/delegation_errors.py` | Add `TaskNotTerminalError` |

## Implementation Order

### Phase 1: restart_task (no downstream invalidation yet)

- [ ] Add `RestartTaskCommand` / `RestartTaskResult` DTOs
- [ ] Add `TaskNotTerminalError`
- [ ] Implement `TaskManagementService.restart_task()`: reset node to PENDING, reset outgoing edges to EDGE_PENDING, emit task/ready
- [ ] Add `_make_restart_task()` to toolkit (8th tool)
- [ ] Unit test: restart from COMPLETED, FAILED, CANCELLED; reject restart of PENDING/RUNNING node
- [ ] Unit test: outgoing edges reset to EDGE_PENDING

### Phase 2: Downstream invalidation

- [ ] Implement `_invalidate_downstream()` in task_management_service: recursive BFS that cancels non-terminal targets and restarts completed targets
- [ ] Wire `_invalidate_downstream()` into `restart_task()` (called after node reset, before edge reset)
- [ ] Unit test: restart D while E is RUNNING → E cancelled, edge reset
- [ ] Unit test: restart D while E is COMPLETED → E restarted recursively, E's outgoing edges reset
- [ ] Unit test: deep chain D→E→F, restart D → E and F both invalidated

### Phase 3: Re-activation of CANCELLED targets on dep satisfaction

- [ ] Modify `on_task_completed_or_failed(COMPLETED)` to check CANCELLED targets alongside PENDING
- [ ] When all incoming edges satisfied for a CANCELLED target, reset to PENDING + add to newly_ready
- [ ] Unit test: D restarts, completes again → E (CANCELLED) becomes READY
- [ ] Unit test: user-cancelled node with all deps satisfied — decide on re-activation policy

### Phase 4: E2E integration test

- [ ] Write `test_manager_dag_scenario.py` with the full 11-step scenario
- [ ] Stub workers that complete after a configurable delay
- [ ] All assertions from the scenario table
- [ ] Wire into CI (`pnpm run test:be:state`)

## Open Questions

1. **Re-activation policy:** Should CANCELLED nodes re-activate when all deps are satisfied, regardless of how they were cancelled? Or only when cancelled by downstream invalidation? Adding a `cancel_cause` column to `RunGraphNode` is cleaner but more invasive. The alternative is: any CANCELLED managed subtask re-activates when all deps are satisfied. The manager can always re-cancel.

2. **Concurrent restart + completion race:** If the manager calls `restart_task(D)` at the same moment D's worker reports completion, who wins? The restart should probably win (the manager's intent is explicit), but we need to think about the edge reset happening after propagation already satisfied the edges.

3. **Event semantics for restart:** Should `restart_task` emit a new event type (`task/restarted`) or reuse `task/ready`? A new event type gives better observability in Inngest dashboard but adds another function to register.

4. **Sandbox lifecycle on restart:** When a node is restarted, should its old sandbox be cleaned up? The current `cleanup_cancelled_task_fn` handles sandbox teardown for cancelled nodes, but a restarted node goes PENDING→RUNNING again and needs a fresh sandbox.
