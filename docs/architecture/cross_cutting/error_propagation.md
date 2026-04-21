# Cross-cutting — Error Propagation

## Purpose

Captures how failure and cancellation propagate through the DAG. This is a
cross-cutting concern spanning runtime, persistence, and worker layers; it
is also an area where current behavior diverges from the intended
fractal-OS semantics — documented here so every PR touching propagation
knows the target. The central claim: failure must be treated as a signal
for an adaptive planner, not as a reason to cascade-cancel the entire
workflow. Today we partially honor that for managed subtasks and violate
it for static workflow siblings.

## Core abstractions

| Type | Location | Freeze | Owner |
|------|----------|--------|-------|
| `TaskExecutionStatus` | `ergon_core/core/persistence/...` | Stable enum: PENDING / RUNNING / COMPLETED / FAILED / CANCELLED | Persistence layer |
| `on_task_completed_or_failed` | `ergon_core/core/runtime/execution/propagation.py:438-586` | Central propagation seam | Runtime layer |
| `CancelCause` | `runtime/events/task_events.py` | Literal type: `"parent_terminal" \| "run_cancel"` | Runtime layer |
| `cancel_orphans_on_*_fn` | `runtime/inngest/cancel_orphan_subtasks.py` | Three Inngest functions | Runtime layer |
| `RunGraphEdge` | persistence row | Stable; edge state: PENDING / SATISFIED / INVALIDATED | Persistence layer |
| `is_workflow_complete_v2` | runtime finalization check | Stable; depends on propagation semantics | Runtime layer |
| `TaskCancelledEvent` | `runtime/events/task_events.py` | The ONLY cancellation trigger for a live task | Runtime layer |

`on_task_completed_or_failed` is the central propagation function. It walks
`RunGraphEdge` outward from the terminal node, updates edge statuses, and
decides target node fates. All failure/cancellation outcomes for
non-terminal nodes are settled here; no other code writes edge statuses.

`CancelCause` records why a task was cancelled. Two values today:
`"parent_terminal"` (cascade from a terminal parent) and `"run_cancel"`
(explicit run-level cancel). The value drives which dashboard events fire
and how the UI renders the cause.

`cancel_orphans_on_*_fn` is a set of three Inngest functions that
cascade-cancel the entire subtask subtree when a parent reaches terminal.
They are the enforcement point for the "cancellation flows strictly
downward along parent->subtask links" invariant.

## Current behavior (as of 2026-04-17)

1. Task COMPLETED, dependents with all deps satisfied -> PENDING.
   Correct.
2. Task FAILED or CANCELLED, MANAGED subtask dependents
   (`parent_node_id` is not None) -> target stays PENDING, edge becomes
   INVALIDATED. Correct; matches fractal-OS semantics. The manager
   observes the failure and adapts.
3. Task FAILED or CANCELLED, STATIC workflow dependents
   (`parent_node_id is None`) -> target AUTO-CANCELLED. Diverges from
   intent — see below.
4. Parent reaches terminal -> `cancel_orphans_on_*_fn` cancels the entire
   subtask subtree. Correct.
5. CANCELLED managed subtask with re-satisfied deps -> CAN re-activate to
   PENDING. Guarded at `propagation.py:546-583`; static workflow
   CANCELLED nodes do NOT re-activate. Correct at the seam level; the
   asymmetry is intentional because static nodes have no adaptive planner
   above them.

## Intended behavior (system owner steer, 2026-04-17)

- Static workflow sibling dependents on upstream failure -> should stay
  PENDING, not auto-cancel. The model is: "B depends on A; A fails; B
  stays PENDING forever unless an adaptive planner unblocks it."
- This makes failure propagation UNIFORM across static and managed nodes.
  The only asymmetry becomes re-activation, which is still justified
  because static nodes lack a manager to re-plan around them.
- Consequence: `is_workflow_complete_v2` will hang on a
  failed-node-with-dependents. Finalization needs a new rule:
  "terminate when every non-terminal node is blocked by a failed-dependency
  chain." That rule is the companion change to the semantic flip.

## Control flow

```
task reaches terminal (COMPLETED | FAILED | CANCELLED)
    |
    +--> propagate_execution fires
    |      |
    |      +--> on_task_completed_or_failed
    |      |     walks outgoing edges
    |      |     |
    |      |     +--> COMPLETED: edge -> SATISFIED;
    |      |     |              if target has all deps satisfied -> PENDING
    |      |     |
    |      |     +--> FAILED/CANCELLED:
    |      |           edge -> INVALIDATED
    |      |           |
    |      |           +--> managed subtask target: stay PENDING (manager adapts)
    |      |           +--> static sibling target:  AUTO-CANCELLED (CURRENT)
    |      |                                        STAY PENDING  (INTENDED; RFC in flight)
    |      |
    |      +--> cancel_orphans_on_* (if parent terminal)
    |            cascade-cancel the full subtask subtree
    |
    v
check_evaluators if COMPLETED; finalize_{success,failure} otherwise
```

Three movements to keep straight:

1. Edge state update — always happens, regardless of target fate.
2. Target node fate — conditional on `parent_node_id` and terminal
   status.
3. Subtree cascade — only fires for terminal parents, strictly downward.

## Invariants

- Cancellation cascades strictly downward along parent->subtask links.
  `cancel_orphans_on_*_fn` handles this. Enforced by: only these three
  Inngest functions may issue `TaskCancelledEvent` with cause
  `"parent_terminal"`.
- `TaskCancelledEvent` is the ONLY legitimate trigger for a running task's
  cleanup. Direct DB CANCELLED writes without the event break the
  cascade. Enforced by: runtime cleanup (sandbox teardown, worker
  shutdown) is wired to the event handler, not to the DB status.
- A CANCELLED managed subtask is re-activatable if dependencies
  re-satisfy; a CANCELLED static workflow node is NOT. Enforced by the
  guard at `propagation.py:546-583`.
- Failure propagation is manager-aware: dynamic subtasks stay PENDING so
  their manager can adapt; static nodes (no manager) — currently
  auto-cancel, intended PENDING.
- Edge state transitions are monotonic within a run:
  PENDING -> (SATISFIED | INVALIDATED), no reverse. Enforced at the seam
  in `on_task_completed_or_failed`.

## Extension points

- **Add a new `CancelCause`:** extend the literal type in
  `runtime/events/task_events.py`; ensure every emission site sets one.
  The dashboard will render the new cause once it is added to the
  renderer's switch. Do not reuse an existing cause for a new meaning.
- **Change propagation semantics:** single seam at
  `propagation.py::on_task_completed_or_failed`; coordinate with
  `is_workflow_complete_v2` and `test_propagation.py`. These three
  co-evolve; changing one without the others leaves the runtime in an
  inconsistent state.
- **Add a new terminal kind** (e.g. `TIMED_OUT` as distinct from FAILED):
  extend `TaskExecutionStatus`, teach the propagation function the new
  terminal's branch, and update finalization.
- **Hook a policy on failure** (retry, escalate, notify): plug into the
  propagation seam's FAILED branch before the target-fate decision.

## Anti-patterns

- **Silently marking a node FAILED via direct DB write.** Must emit
  `TaskFailedEvent` so the cascade fires. A direct write bypasses
  `on_task_completed_or_failed`, leaves edges in PENDING, and strands
  dependents.
- **Assuming "failed -> children cancel" today.** True for static
  siblings, NOT for managed subtasks. Check `parent_node_id` before
  reasoning about a failure's downstream effect.
- **Re-activating a CANCELLED static workflow node.** Explicitly forbidden
  at `propagation.py:546-583`. The guard exists because static nodes have
  no planner to own the re-activation decision.
- **Issuing `TaskCancelledEvent` without a `CancelCause`.** Breaks
  dashboard rendering and loses the reason for the cancel. Every
  emission site must set a cause.
- **Checking `is_workflow_complete_v2` without accounting for the intended
  semantics flip.** Code that assumes "all nodes reach a terminal state"
  will hang once static siblings stop auto-cancelling.
- **Coupling sandbox teardown to the DB status column instead of
  `TaskCancelledEvent`.** Makes teardown invisible to the cascade and
  easy to double-fire.

## Follow-ups

- `docs/rfcs/active/2026-04-17-static-sibling-failure-semantics.md` —
  align static-sibling behavior with fractal-OS semantics; also fixes the
  `is_workflow_complete_v2` hang. This is the single RFC that flips the
  current-vs-intended diff above.
- Terminology note: the `propagate_task_failure_fn` module may still
  encode the old auto-cancel path; audit and align when the RFC lands.
  Leaving two code paths that disagree on static-sibling fate is the
  single most likely source of future bugs.
- Finalization rewrite. Once static siblings can stay PENDING
  indefinitely, `is_workflow_complete_v2` needs the "blocked by a failed
  dependency chain" rule. Land it in the same PR as the semantics flip;
  the two are inseparable.
- Dashboard UX. Distinguish "blocked by failed dependency" from
  "cancelled". Today they render identically once we stop cancelling;
  the new state needs its own badge.
- Test coverage. `test_propagation.py` currently encodes the CURRENT
  behavior. When the RFC lands, flip those tests; audit for tests that
  implicitly depend on auto-cancel as a shortcut to reach workflow
  terminal.
