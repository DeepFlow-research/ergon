# Control Flow Test Specification

## What the System Actually Is (and What Integration Tests Should Assert)

The integration tier is testing the wrong things because it is not oriented around the actual system model. Understanding that model is a prerequisite for knowing what to test.

### The system model

Ergon is an Inngest-driven, append-only workflow engine. Every meaningful invariant lives in Postgres. The unit of truth is **the database state after events settle**, not HTTP response codes.

| Table | Purpose |
|-------|---------|
| `RunRecord` | One row per benchmark run; owns the run-level lifecycle status |
| `RunGraphNode` / `RunGraphEdge` / `RunGraphMutation` | DAG execution state; WAL is the ground truth |
| `RunTaskExecution` | One row per execution attempt; records start/end, output, error |
| `RunResource` / `ThreadMessage` | Task outputs and agent-to-agent communication |

### The state machine

| Status | Terminal? | Meaning |
|--------|-----------|---------|
| `PENDING` | No | Created; not all predecessors COMPLETED. Normal waiting. |
| `READY` | No | All predecessors COMPLETED. Eligible for `task/ready` dispatch. |
| `BLOCKED` | No | At least one predecessor FAILED. Operator action required. |
| `RUNNING` | No | Worker executing in sandbox. |
| `COMPLETED` | Yes | Worker returned success. Outputs in `RunResource`. |
| `FAILED` | Yes | Worker raised an error during execution. |
| `CANCELLED` | Yes | Explicitly stopped by operator, or orphaned by parent cancellation. |

**BLOCKED is not PENDING.** PENDING means "waiting for normal upstream progress." BLOCKED means "a predecessor FAILED and operator action is required." A stuck run with BLOCKED tasks must be distinguishable from an active run with PENDING tasks.

**FAILED is reserved for worker errors.** A task that never ran because its predecessor FAILED is BLOCKED, not FAILED. FAILED means "the execution attempt ran and something went wrong inside it."

**CANCELLED means intentionally stopped or orphaned.** A task whose parent was cancelled has no execution context — it is CANCELLED. A task that cannot proceed because a predecessor failed is BLOCKED, not CANCELLED.

**`only_if_not_terminal` guard:** Prevents writing to a node already in `{COMPLETED, FAILED, CANCELLED}`. BLOCKED, PENDING, READY, and RUNNING are non-terminal and can be overwritten by valid transitions.

**RunRecord statuses:** `CREATED → RUNNING → {COMPLETED | FAILED | CANCELLED}`

`RunRecord` has no BLOCKED state. A run with BLOCKED tasks shows `RUNNING` — it is stuck, not failed. `RunRecord.status == FAILED` requires an explicit operator action or run-level timeout, not automatic propagation. `RunRecord.status == COMPLETED` requires all nodes in `{COMPLETED, CANCELLED}`.

**Edge statuses:** `EDGE_PENDING → EDGE_SATISFIED`

An edge flips to `EDGE_SATISFIED` when its source node reaches `COMPLETED`. On restart, edges flip back to `EDGE_PENDING`.

### The Inngest event flow

```
benchmark/run-request
  → [benchmark_run_start_fn]
      persist ExperimentDefinition
      INSERT RunRecord (status=CREATED)
      emit workflow/started

workflow/started
  → [start_workflow_fn]
      create RunGraphNode for each definition task
      create RunGraphEdge for each dependency
      mark root nodes READY
      emit task/ready (fanout to all roots)

task/ready
  → [execute_task_fn]
      CAS: UPDATE run_graph_node SET status='RUNNING'
           WHERE id=? AND status='READY' RETURNING id;
      → 0 rows returned: exit immediately (duplicate delivery or concurrent pickup)
      INSERT RunTaskExecution (status=PENDING)
      [sandbox_setup_fn]
      [worker_execute_fn]
          optionally: plan_subtasks() → inserts child RunGraphNodes, emits task/ready for roots
          optionally: save_message()  → inserts Thread + ThreadMessage
      [persist_outputs_fn]           → INSERT RunResource rows
      UPDATE RunTaskExecution (status=COMPLETED)
      UPDATE RunGraphNode → COMPLETED
      INSERT RunGraphMutation
      emit task/completed

    [on any failure]
      UPDATE RunTaskExecution (status=FAILED, error_json=...)
      UPDATE RunGraphNode → FAILED
      INSERT RunGraphMutation
      emit task/failed

task/completed → [propagate_execution]
      flip source edge → EDGE_SATISFIED
      for each successor:
          all incoming edges EDGE_SATISFIED → mark READY, emit task/ready
          any predecessor FAILED            → stays BLOCKED
          otherwise                         → stays PENDING
      if all nodes terminal → emit workflow/completed

task/failed → [propagate_execution]
      SELECT FOR UPDATE all affected successor + descendant rows (id ASC)
      for each PENDING/READY successor (horizontal):  → BLOCKED
          INSERT RunGraphMutation (cause=dep_failed)
      for each PENDING/READY descendant (vertical):   → BLOCKED
          INSERT RunGraphMutation (cause=parent_failed)
      RUNNING successors/descendants: NOT interrupted (live executions continue)
      (no task/blocked event — BLOCKED is a synchronous DB write, not an event dispatch)
      RunRecord stays RUNNING — the run is stuck, not failed

task/cancelled → [cancel_orphans_fn]
      SELECT FOR UPDATE all descendant rows (id ASC)
      cascade CANCELLED to all non-terminal children (cause=parent_terminal)
      UPDATE RunTaskExecution → CANCELLED
      UPDATE RunGraphNode → CANCELLED
      INSERT RunGraphMutation

workflow/completed
  → [complete_workflow_fn]
      aggregate scores from RunTaskExecution outputs
      UPDATE RunRecord (status=COMPLETED, completed_at=now, summary_json={scores})
      emit run/cleanup

workflow/failed
  → [fail_workflow_fn]
      UPDATE RunRecord (status=FAILED, error_message=...)
      emit run/cleanup
```

**Key difference from prior spec:** `task/failed` no longer emits `task/cancelled` for downstream nodes. It writes BLOCKED directly to `RunGraphNode` rows. There is no `task/blocked` event — BLOCKED transitions are synchronous DB updates in the propagation pass.

### Subtask spawning (dynamic DAG mutation)

A worker can call `plan_subtasks()` during execution. This inserts child `RunGraphNode` rows under the currently-executing node and immediately emits `task/ready` for the new roots. The containment tree is recorded via `parent_node_id` (self-referential FK) and `level` (precomputed depth: `parent.level + 1`).

**Key invariants:**
- Every node with `parent_node_id != NULL` has `level == parent.level + 1`
- Cycle detection runs at `plan_subtasks` time; any cycle rejected before any DB write
- The parent task does not finalise until all its children are terminal
- Cross-containment `RunGraphEdge` rows are forbidden: both endpoints must share the same `parent_node_id`

### Cancellation causes

| Cause | Trigger |
|-------|---------|
| `manager_decision` | Operator explicitly called `cancel_task()` |
| `parent_terminal` | Parent node reached CANCELLED |
| `dep_invalidated` | Predecessor restarted; this successor's prior outputs are stale (restart only — not failure) |
| `run_cancelled` | Run-level cancellation broadcast |

**`dep_invalidated` does not apply to failure.** When a predecessor FAILS, successors become BLOCKED — no cancellation event is emitted. `dep_invalidated` fires only when a predecessor is *restarted* and a COMPLETED successor needs to be invalidated.

### The restart flow

`restart_task(node_id)` (valid on FAILED or COMPLETED nodes):

1. Acquire `SELECT FOR UPDATE` on all affected rows (id ASC — see Section 9.2 of status design doc)
2. Reset node: `FAILED/COMPLETED → PENDING`
3. Reset own outgoing edges: `EDGE_SATISFIED → EDGE_PENDING`
4. BLOCKED successors → `PENDING` (predecessor being retried; re-evaluate when it completes)
5. COMPLETED successors → `CANCELLED` with cause `dep_invalidated` (prior outputs are stale)
6. Containment descendants: ALL → `CANCELLED` regardless of prior status; new execution creates fresh children via `plan_subtasks()` (resetting to PENDING instead would create duplicate child generations)
7. Emit `task/ready` for the node

Nodes with `parent_node_id != NULL` cannot be restarted independently — only via their parent's restart.

---

## Integration Tests

Each test: stub workers (no E2B, no real LLM), submit real event to local Inngest dev server, poll until `RunRecord.status` is terminal **or** all expected BLOCKED/stuck nodes are confirmed, then assert exact Postgres state.

Polling timeout: 30 s for standard tests, 120 s for `pytest.mark.slow`.

---

### Test 1: Single-task happy path

One task, worker returns `WorkerOutput(success=True)`.

Assert:
- `RunRecord.status == COMPLETED`, `completed_at` set
- `RunGraphNode.status == COMPLETED`
- `RunTaskExecution.status == COMPLETED`, `started_at ≤ completed_at`
- At least one `RunResource` row with correct `run_id` and `task_execution_id`
- WAL contains entries for `PENDING → RUNNING → COMPLETED`

---

### Test 2: Linear chain — propagation

Three tasks A → B → C. All succeed.

Assert:
- Completed in topological order (`completed_at`: A before B before C)
- All `RunGraphEdge` rows `EDGE_SATISFIED`
- WAL: `READY` transition for B only after A's `COMPLETED` entry; ditto C after B
- `RunRecord.status == COMPLETED`

---

### Test 3: Failure cascade — successor becomes BLOCKED

Three tasks A → B → C. A succeeds. B fails. C never ran.

Assert:
- A: `COMPLETED`
- B: `FAILED`, `RunTaskExecution.error_json` non-null
- C: `BLOCKED` — **not** CANCELLED, **not** PENDING
- No `RunTaskExecution` row for C (it never started)
- WAL entry for C: cause `dep_failed`, timestamped after B's `FAILED` mutation
- `RunRecord.status == RUNNING` — the run is stuck, **not** FAILED
- No `RunResource` rows owned by C
- No `task/ready` emitted for C

**Critical:** `RunRecord.status` must be `RUNNING`. A run is only FAILED when an operator explicitly fails it or a timeout fires. Automatic failure propagation does not change `RunRecord`.

---

### Test 4: Diamond DAG — propagation convergence

Four tasks: `root → left`, `root → right`, `left → sink`, `right → sink`. All succeed.

Assert:
- `left` and `right` both reach `RUNNING` before `sink` becomes `READY`
- `sink` transitions to `READY` only after both `left` AND `right` are `COMPLETED` (both edges `EDGE_SATISFIED`)
- `sink` transitions to `READY` exactly once — the `only_if_not_terminal` / CAS guard is exercised: sink receives two "dep satisfied" signals but dispatches once
- All four `COMPLETED`, `RunRecord.status == COMPLETED`

---

### Test 5: Subtask spawning — dynamic DAG

Parent worker calls `plan_subtasks()` with:

```
root_child  (no deps within subtask group)
    ↓ dependency edge
leaf_child  (depends on root_child; same parent_node_id)
```

Both are direct children of parent — same `parent_node_id`, same `level`. The `→` is a sibling dependency edge, not a nesting level.

Assert:
- Two `RunGraphNode` rows with `parent_node_id == parent_node.id`
- Both have `level == parent.level + 1`
- `root_child` was the only node to transition to `READY` immediately after subtask insertion (`leaf_child` was `PENDING`)
- `leaf_child` transitions to `READY` only after `root_child` COMPLETED (WAL timestamps)
- Parent reaches `COMPLETED` only after both children are terminal
- No `RunGraphEdge` from parent to either child — containment is via `parent_node_id`, not edges

---

### Test 6: Cancellation — manager_decision

Two sibling tasks: `target` (with subtree) and `sibling` (independent).

```
target (cancelled while RUNNING)
├── target-child-A
│   ├── target-grandchild-A1
│   └── target-grandchild-A2
└── target-child-B

sibling (must NOT be affected)
└── sibling-child
```

Call `cancel_task(target.node_id)` while target is RUNNING and subtree is live.

Assert — cancellation target:
- `target.status == CANCELLED`, cause `manager_decision`
- `target.RunTaskExecution.status == CANCELLED`

Assert — full subtree cascade:
- `target-child-A`, `target-child-B`: `CANCELLED`, cause `parent_terminal`
- `target-grandchild-A1`, `target-grandchild-A2`: `CANCELLED`, cause `parent_terminal`
- WAL: grandchild entries timestamped after their parent's `CANCELLED` mutation (level-by-level, not all-at-once)
- No `RunTaskExecution` with `status IN (RUNNING, COMPLETED)` for any descendant

Assert — sibling isolation:
- `sibling.status` unchanged
- `sibling-child.status` unchanged
- WAL for sibling contains no `CANCELLED` entries

Assert — run-level status:
- `RunRecord.status == RUNNING` (cancelling one task does not fail the run while other tasks remain)

Assert — idempotency:
- Second `cancel_task(target.node_id)` returns an error
- WAL mutation count for `target` does not increase

---

### Test 7: Parent-failure cascade — descendants become BLOCKED

When a parent's worker fails (`RUNNING → FAILED`), non-terminal containment descendants become `BLOCKED`. BLOCKED means "this execution context collapsed; operator action required." FAILED is only for tasks whose own worker errored. CANCELLED is only for tasks explicitly stopped or orphaned.

```
parent (raises controlled exception)
├── child-A  (PENDING when parent fails)
│   ├── grandchild-A1  (PENDING)
│   └── grandchild-A2  (RUNNING)
└── child-B  (RUNNING when parent fails)
└── child-C  (COMPLETED before parent fails — must survive)
```

Assert:
- Parent: `FAILED`, `RunTaskExecution.error_json` non-null
- `child-A`: `BLOCKED`, cause `parent_failed` — **not** CANCELLED, **not** FAILED
- `grandchild-A1`: `BLOCKED`, cause `parent_failed`
- `child-B`: **not interrupted** — continues to its own terminal state (RUNNING execution is live)
- `grandchild-A2`: **not interrupted** — continues to its own terminal state
- `child-C`: remains `COMPLETED` — already terminal, not overwritten
- WAL: grandchild BLOCKED entries timestamped after their parent's BLOCKED mutation
- `RunRecord.status == RUNNING` — stuck, not FAILED

**What must NOT happen:**
- No CANCELLED mutations for any descendant (cancel = intentional stop)
- No FAILED mutations for child-A or grandchild-A1 (they did not run and error)
- RunRecord must not automatically become FAILED

**Depth parametrisation:** Run at N=1, N=3, N=10 sublayer depths. Every descendant at every level must be BLOCKED. Catches iterative vs recursive cascade bugs where only the first level is processed.

---

### Test 8: Restart — BLOCKED successors unblock; descendants cancel and regenerate

Prior state:

```
parent  (FAILED after first execution)
├── child-root       (COMPLETED in prior run)
│   └── child-leaf   (COMPLETED in prior run)
└── child-standalone (FAILED in prior run)

blocked-successor   (DAG successor of parent; currently BLOCKED)
completed-successor (DAG successor of parent; COMPLETED in prior run)
```

**Step 1 — refine:** `refine_task(parent.node_id, new_description)` updates description; status unchanged (FAILED).

**Step 2 — restart:** `restart_task(parent.node_id)`

Assert — parent reset:
- `parent.status == PENDING`, then `RUNNING` once `task/ready` fires
- WAL: `FAILED → PENDING` with cause `operator_restart`
- New `RunTaskExecution` with incremented `attempt_number`

Assert — containment descendants cancelled (not reset to PENDING):
- `child-root`, `child-leaf`, `child-standalone`: all `CANCELLED`
- Not reset to PENDING — new execution creates fresh children via `plan_subtasks()`
- Prior child rows preserved in DB (append-only); status is CANCELLED

Assert — BLOCKED successor unblocked:
- `blocked-successor`: `BLOCKED → PENDING`
- Incoming edge from parent resets to `EDGE_PENDING`
- WAL cause: `predecessor_restarted`

Assert — COMPLETED successor invalidated:
- `completed-successor`: `COMPLETED → CANCELLED`, cause `dep_invalidated`
- Incoming edge from parent resets to `EDGE_PENDING`

Assert — dispatch:
- `task/ready` fires for `parent` only — not for any containment descendants
- New execution creates fresh children; propagation drives non-root activations

Assert — independent guard:
- `restart_task(child-root.node_id)` raises an error — containment nodes cannot be restarted independently

**Step 3 — restarted execution completes:**
- New children reach `COMPLETED` via normal propagation
- `parent.status == COMPLETED`
- `blocked-successor` re-activates (edge → EDGE_SATISFIED → READY → COMPLETED)
- `RunRecord.status == COMPLETED`
- Exactly two `RunTaskExecution` rows for parent (attempt 1, attempt 2)

**Depth parametrisation:** Run at N=1, N=3, N=10. Every containment descendant at every level must be CANCELLED on restart. `task/ready` must fire only for the new subtask roots — not every node simultaneously.

---

### Test 9: Communication service — message routing

Stub worker calls `save_message(from_agent_id=leaf-X, to_agent_id=parent, thread_topic=smoke-completion)`.

Assert:
- `Thread` row exists scoped to `run_id` with correct `topic`
- `ThreadMessage` row with correct `from_agent_id`, `to_agent_id`, `run_id`, `task_execution_id`
- `sequence_num == 1` for first message
- Second message to same thread gets `sequence_num == 2`

---

### Test 10: BLOCKED propagates rightward transitively

Three tasks A → B → C. A fails. Neither B nor C has started.

Assert:
- A: `FAILED`
- B: `BLOCKED` (direct successor)
- C: `BLOCKED` (transitive successor — blocked because B is blocked, which is blocked because A failed)
- WAL: B's BLOCKED timestamped after A's FAILED; C's BLOCKED timestamped after B's BLOCKED
- `RunRecord.status == RUNNING`

**Distinct from Test 3:** Test 3 has B failing (B is the one whose worker errors). This test has A failing, cascading BLOCKED to both B and C via transitive propagation. The propagation must walk the full rightward chain, not just direct successors.

---

### Test 11: BLOCKED → PENDING when predecessor restarted

Precondition: state from Test 10 (A FAILED, B and C BLOCKED).

Call `restart_task(A.node_id)`.

Assert immediately after restart:
- A: `PENDING`
- B: `PENDING` (was BLOCKED because of A; unblocked by restart)
- C: `PENDING` (was BLOCKED because of B; cascade unblocked)
- All incoming edges reset to `EDGE_PENDING`
- WAL: PENDING transitions for B and C with cause `predecessor_restarted`
- `RunRecord.status == RUNNING`

Assert after A, B, C complete normally:
- A → B → C all `COMPLETED` in order
- `RunRecord.status == COMPLETED`

---

### Test 12: RUNNING successor not interrupted by predecessor failure

Two tasks A → B. B is actively RUNNING when A fails.

Assert immediately after A fails:
- A: `FAILED`
- B: **not** BLOCKED, **not** CANCELLED — remains `RUNNING`
- WAL: no BLOCKED mutation for B (RUNNING tasks are never interrupted by predecessor failure)
- `RunRecord.status == RUNNING`

Assert after B reaches its own terminal state:
- If B completes: `B.status == COMPLETED`; `RunRecord.status == RUNNING` (stuck — A is FAILED and the run cannot complete while A is non-COMPLETED-or-CANCELLED)
- If B fails: `B.status == FAILED`; `RunRecord.status == RUNNING`

---

### Test 13: Operator unblock — BLOCKED → PENDING without restarting the predecessor

A: `FAILED`. B: `BLOCKED` (successor of A). Operator calls `unblock_task(B.node_id)` (cause `operator_unblock`).

Assert:
- B: `PENDING` — not READY (A has not re-completed; B re-evaluates when predecessors complete)
- A: `FAILED` — unchanged
- B's incoming edge from A: `EDGE_PENDING`
- WAL entry for B: cause `operator_unblock`

Assert this never fires automatically:
- No propagation path produces `BLOCKED → PENDING` without an explicit operator call
- B remains PENDING indefinitely until A is restarted and completes, or B is separately managed

---

## Edge Cases and Boundary Conditions

### EC-1: Fan-in convergence race under failure

Diamond DAG: `root → left`, `root → right`, `left → sink`, `right → sink`. Left fails at the same moment right completes. Use a sleep barrier to make the race reproducible.

Two propagation events race to `sink`: BLOCKED propagation (from left's failure) and READY evaluation (from right's completion).

Assert:
- `sink.status == BLOCKED` — left is a failed predecessor; right completing alone is not sufficient
- `RunRecord.status == RUNNING`
- `sink` WAL has exactly one terminal mutation (BLOCKED); no READY or RUNNING entry
- If right's completion arrives first: right's edge satisfies, but sink re-evaluates, finds left FAILED → BLOCKED
- If left's failure arrives first: sink → BLOCKED; right's completion does not override it

Mark `pytest.mark.slow`, run with `--count=5`.

**Note:** Prior spec expected `sink == CANCELLED`. Under new semantics, a failed predecessor blocks successors; it does not cancel them.

---

### EC-2: Duplicate `task/ready` delivery — CAS guard at READY→RUNNING

The `task/ready` handler's first DB operation:

```sql
UPDATE run_graph_node SET status='RUNNING'
WHERE id = $node_id AND status = 'READY'
RETURNING id;
```

0 rows returned → exit immediately, no RunTaskExecution created.

Unit-tier test: seed `RunGraphNode` in `RUNNING` state, invoke `prepare-execution` logic directly.

Assert:
- No second `RunTaskExecution` created
- No sandbox provisioned
- No duplicate `RUNNING` WAL entry
- Handler exits cleanly

---

### EC-3: Cross-containment dependency edges are forbidden

A `RunGraphEdge` where `source.parent_node_id != target.parent_node_id` must be rejected at graph construction time.

Unit-tier test.

Assert:
- `add_edge(source, target)` raises an error when `source.parent_node_id != target.parent_node_id`
- `add_edge` raises an error when one node has `parent_node_id` and the other does not
- Error raised before any DB write — no partial edge rows created

---

### EC-4: Evaluation after restart — which attempt's score counts

1. Task completes (attempt 1) → `RunTaskEvaluation` created with score X
2. `restart_task` called → task re-runs (attempt 2) → second `RunTaskEvaluation` with score Y

Assert:
- Exactly two `RunTaskEvaluation` rows for same `definition_task_id` and `run_id`
- `RunRecord.summary_json` reflects score Y (most recent attempt), not X
- Attempt-1 `RunTaskEvaluation` preserved (append-only) but not used in summary
- Summary row identified by matching `execution_id` to the most recent `RunTaskExecution` for the node

If not yet implemented: `pytest.mark.xfail(strict=True, reason="evaluation after restart: score selection across attempts not yet defined")`.

---

### EC-5: Concurrency queue + node cancellation while queued

`execute_task_fn` has `concurrency limit=15`. Saturate all 15 slots, fire a 16th `task/ready`, then cancel the 16th node via `cancel_task` while it is queued (before Inngest dispatches it).

Assert:
- When Inngest dispatches the queued invocation, the READY→RUNNING CAS returns 0 rows (node is now CANCELLED) → handler exits
- No `RunTaskExecution` row created for the cancelled node
- No sandbox provisioned
- No `TaskCompletedEvent` or `TaskFailedEvent` emitted
- WAL: CANCELLED entry for node, no RUNNING entry

Mark `pytest.mark.slow`.

---

### EC-6: Multiple BLOCKED predecessors — task stays BLOCKED until all resolved

Fan-in: A and B both feed into C. A fails, then B fails independently.

Assert after both fail:
- C: `BLOCKED` (two failed predecessors)

Call `restart_task(A.node_id)`.

Assert:
- C: still `BLOCKED` — B is still FAILED; one predecessor restarting is insufficient
- A's outgoing edge resets to `EDGE_PENDING`; B's edge is still in blocked state

Call `restart_task(B.node_id)`.

Assert:
- C: `PENDING` — both predecessors now being retried; C re-evaluates
- Both incoming edges at `EDGE_PENDING`

After A and B both complete:
- C: `READY` → `RUNNING` → `COMPLETED`

---

### EC-7: RUNNING descendant survives parent FAILED

Parent spawns a subtask that is actively RUNNING when parent's worker raises.

Assert immediately after parent fails:
- Parent: `FAILED`
- Child: **not** interrupted — remains `RUNNING`
- WAL: no BLOCKED or CANCELLED mutation for child yet
- `RunRecord.status == RUNNING`

After child reaches its own terminal state:
- If child `COMPLETED`: parent stays `FAILED` (already terminal); `RunRecord.status == RUNNING` (stuck)
- If child `FAILED`: parent stays `FAILED`; `RunRecord.status == RUNNING`

The child's execution is independent of parent's failure — it runs to completion or failure on its own.

---

## Bulk Operation Tests

Full protocol: `0-task-status-design.md` § 8. These tests assert Postgres state after batch API requests. All mutations within a batch share the same `batch_operation_id`.

### B-1: Batch restart + operator unblock

Precondition: A→B→C linear chain; A failed; B and C BLOCKED.

Bulk request: restart A + operator-unblock B.

Assert:
- All mutations share one `batch_operation_id`
- A: `PENDING` (directly specified)
- B: `PENDING` (directly specified, cause `operator_unblock`)
- C: `PENDING` (cascade from B's unblocking)
- `triggered_by_mutation_id` on C's mutation points to B's mutation row
- All incoming edges `EDGE_PENDING`

After A completes: B → C complete in order; `RunRecord.status == COMPLETED`.

### B-2: Batch conflict — same task twice

Batch: restart A AND cancel A.

Assert:
- 422 response; zero mutations written; A status unchanged

### B-3: Batch FSM violation

Batch: `RUNNING → PENDING` for an actively running task (not in FSM).

Assert:
- 422 response; zero mutations written

### B-4: Batch FAILED → CANCELLED (give up without restarting)

Task A: `FAILED`. Descendants B and C (containment): `BLOCKED`.

Bulk request: cancel A (FAILED → CANCELLED).

Assert:
- A: `CANCELLED`
- B, C: `CANCELLED` (cascade from A's cancellation — they are descendants)
- DAG successors of A: remain `BLOCKED` — they still lack A's outputs
- `RunRecord.status == RUNNING` (successors are BLOCKED; run is stuck)

### B-5: Cascade supersession rejection

Batch: cancel parent P + restart child C (where C is a containment descendant of P).

Pre-flight must detect C is inside the cancel cascade of P.

Assert:
- 422 response; zero mutations written
- Error body identifies C as the superseded target

---

## Race and Concurrency Tests

Full locking model: `0-task-status-design.md` § 9. These tests verify correctness guarantees under concurrent load.

### R-1: Fan-in double dispatch — exactly-once task/ready

Two-predecessor fan-in task C. Hold both predecessors A and B at commit boundary via advisory lock, release simultaneously.

Assert:
- Exactly one `task/ready` event emitted for C
- Exactly one `RunTaskExecution` row for C
- C's WAL contains exactly one `READY` transition
- C eventually `COMPLETED`

Mark `pytest.mark.slow`, run with `--count=10`.

### R-2: Duplicate task/ready — CAS prevents double execution

Integration-tier version of EC-2. Submit same `task/ready` event twice via Inngest API for an already-RUNNING task.

Assert:
- Exactly one `RunTaskExecution` row
- Exactly one `RUNNING` WAL entry
- Second handler invocation exits without DB writes

### R-3: Cascade supersession — atomic rejection under concurrent load

Submit two concurrent API requests: bulk-cancel P + restart C (where C is a descendant of P).

Assert:
- Exactly one request succeeds; the other returns 422
- Final DB state is consistent (not partial — no C in PENDING while P is CANCELLED)

### R-4: Concurrent cancel vs propagation — cancel always wins

Task B is PENDING. A completes — propagation starts to move B to READY. Simultaneously cancel B via API.

Assert:
- B's final status is `CANCELLED` regardless of propagation timing
- No `task/ready` emitted for B after it is CANCELLED
- No `RunTaskExecution` created for B

Mark `pytest.mark.slow`.

---

## Cross-Cutting Invariants

Write these as shared assertion helpers, call from every test above.

| Invariant | Assertion |
|-----------|-----------|
| WAL completeness | Every `RunGraphNode` has at least one `RunGraphMutation` entry |
| Execution coverage | Every node that reached `COMPLETED` or `FAILED` has a `RunTaskExecution` with non-null `completed_at` |
| No executions for un-run BLOCKED nodes | No `RunTaskExecution` with status `RUNNING` or `COMPLETED` for a node that is currently BLOCKED with no prior attempt |
| No orphaned executions | Every `RunTaskExecution.node_id` references an existing `RunGraphNode` in the same run |
| RunRecord terminal consistency | `COMPLETED` → all nodes in `{COMPLETED, CANCELLED}`; `FAILED` → explicit operator/timeout only; `RUNNING` → any non-terminal nodes present (including BLOCKED) |
| BLOCKED is non-terminal | No `RunGraphNode` in `{COMPLETED, FAILED, CANCELLED}` was transitioned there directly from `BLOCKED` without an intervening operator action in the WAL |
| FAILED is worker-only | Every FAILED node has a `RunTaskExecution` with non-null `error_json` |
| CANCELLED is intentional | Every CANCELLED node has a WAL cause in `{manager_decision, parent_terminal, dep_invalidated, run_cancelled}` |
| No RunRecord FAILED without operator | `RunRecord.status == FAILED` implies a WAL entry with cause `operator_decision` or `run_timeout` — automatic propagation never sets it |
| Edge–node consistency | Every `EDGE_SATISFIED` edge has a source node with `status == COMPLETED` |
| Level consistency | Every node with `parent_node_id != NULL` has `level == parent.level + 1` |
| Append-only WAL | Mutation count for any given node only ever increases; no rows deleted or updated |
| Timeline consistency | `started_at ≤ completed_at` on every `RunTaskExecution` |
| Batch attribution | All mutations from a bulk request share `batch_operation_id`; cascade mutations carry `triggered_by_mutation_id` pointing to the direct batch item that caused them |
| No BLOCKED RunRecord | `RunRecord.status` is never `BLOCKED` — stuck runs show `RUNNING` |

---

## Summary

The current `tests/integration/` has one real integration test checking HTTP response codes on a narrow happy path. This spec covers:

- **13 primary control flow tests** (Tests 1–13): happy path, propagation, failure→BLOCKED, diamond convergence, subtask spawning, cancellation, parent-failure→BLOCKED, restart+unblocking, communication, transitive BLOCKED cascade, BLOCKED→PENDING on restart, RUNNING isolation, operator unblock
- **7 edge cases** (EC-1–7): fan-in race under failure, duplicate delivery CAS, cross-containment guard, evaluation across restarts, queued cancellation, multi-predecessor BLOCKED, RUNNING descendant survival
- **5 bulk operation tests** (B-1–5): batch atomicity, conflict rejection, FSM violation, give-up cancel, cascade supersession rejection
- **4 concurrency tests** (R-1–4): double dispatch, duplicate delivery, concurrent cancel under load, propagation race

All tests assert Postgres state, not HTTP status codes. The WAL (`RunGraphMutation`) is the ground truth for causality and ordering. `RunRecord.status` is only FAILED via explicit operator action — never via automatic propagation.
