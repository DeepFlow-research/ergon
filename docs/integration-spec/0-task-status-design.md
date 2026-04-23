# Task Status Design

> **Status:** DRAFT — for review before schema changes, integration test updates, or core logic changes.
>
> This document is the canonical reference for task status vocabulary, terminology, and propagation rules. It supersedes status semantics described elsewhere in the integration spec. The intended workflow: agree this doc → update schemas → rewrite integration tests against these semantics → fix core logic to pass.

---

## 1. Terminology

Two orthogonal relationships connect tasks. Propagation rules differ completely between them, so the terms must be used precisely.

### Containment (vertical axis)

Created by `plan_subtasks()` / `add_subtask()`. Stored via `parent_node_id` on `RunGraphNode`. Represents "this task owns the execution context for its children."

| Term | Definition |
|------|-----------|
| **Parent** | The task that spawned this task. One level up via `parent_node_id`. |
| **Children** | Tasks spawned by this task. One level down via `parent_node_id`. Collectively a sub-DAG — children can have dependency edges between themselves. |
| **Ancestors** | All parents, grandparents, etc. up the containment chain. |
| **Descendants** | All children, grandchildren, etc. — the full containment subtree. |

### Dependency (horizontal axis)

Created by the experiment definition or by `plan_subtasks()` dependency specs. Stored as `RunGraphEdge` rows. Represents "this task's outputs are inputs to its successors."

| Term | Definition |
|------|-----------|
| **Predecessors** | Tasks this task depends on. Incoming `RunGraphEdge`. Must COMPLETE before this task can start. "To the left." |
| **Successors** | Tasks that depend on this task. Outgoing `RunGraphEdge`. Waiting for this task's outputs. "To the right." |

**Hard constraint:** Cross-containment dependency edges are forbidden. A `RunGraphEdge` must not connect two nodes with different `parent_node_id` values. All dependency edges within a sub-DAG are between siblings (same `parent_node_id`). This keeps the two axes independent.

---

## 2. Status Definitions

| Status | Terminal? | Meaning |
|--------|-----------|---------|
| `PENDING` | No | Created. Not all predecessors have COMPLETED. Normal waiting state. |
| `READY` | No | All predecessors COMPLETED. Eligible for dispatch via `task/ready`. |
| `BLOCKED` | No | At least one predecessor is FAILED, or parent context is unavailable. Cannot proceed without operator action. |
| `RUNNING` | No | Worker executing in sandbox. |
| `COMPLETED` | Yes | Worker returned success. Outputs available in `RunResource`. |
| `FAILED` | Yes | Worker raised an error during execution. Outputs unavailable. |
| `CANCELLED` | Yes | Explicitly stopped by operator, or orphaned by parent cancellation. |

### Design principles

**BLOCKED is not PENDING.** PENDING means "waiting for normal upstream progress." BLOCKED means "progress has stopped — a dependency failed and operator action is required." Without this distinction, a stuck run with BLOCKED tasks looks identical to an active run with PENDING tasks.

**FAILED is reserved for tasks whose worker actually errored.** A task that never ran because its predecessor failed is BLOCKED, not FAILED. FAILED means "the execution attempt ran and something went wrong inside it."

**CANCELLED means orphaned or explicitly stopped.** A child whose parent was cancelled has no execution context to return to — it is CANCELLED. A task explicitly stopped by the operator is CANCELLED. A task that cannot proceed because a predecessor failed is BLOCKED, not CANCELLED.

**Successors are never automatically cancelled when a predecessor fails.** They become BLOCKED. The operator decides: restart the failed predecessor, manually cancel the successors, or cancel the run. The system holds state, not makes decisions.

---

## 3. Conditional FSM

### Transition table

| From | To | Trigger | Who can trigger |
|------|----|---------|----------------|
| `PENDING` | `READY` | All predecessors COMPLETED | Propagation (automatic) |
| `PENDING` or `READY` | `BLOCKED` | Any predecessor reaches FAILED | Propagation (automatic) |
| `BLOCKED` | `PENDING` | The FAILED predecessor is restarted (→ PENDING) | Propagation (automatic) |
| `READY` | `RUNNING` | Worker picks up `task/ready` | Inngest dispatch |
| `RUNNING` | `COMPLETED` | Worker returns success | Worker |
| `RUNNING` | `FAILED` | Worker raises error | Worker |
| `FAILED` | `PENDING` | Operator calls `restart_task()` | Operator |
| `COMPLETED` | `PENDING` | Operator calls `restart_task()` | Operator |
| Any non-terminal | `CANCELLED` | Operator calls `cancel_task()`, or parent → CANCELLED | Operator / cascade |

### Propagation rules per transition

---

#### PENDING → READY

**Trigger:** All incoming `RunGraphEdge` rows are `EDGE_SATISFIED` (all predecessors COMPLETED).

**Propagation:**
- Emit `task/ready`. Nothing else changes.

---

#### PENDING or READY → BLOCKED

**Trigger:** Any predecessor reaches FAILED.

**Propagation:**
- **Successors →** cascade BLOCKED rightward: any successor that is PENDING or READY → BLOCKED. RUNNING successors are not interrupted (they have live executions; let them finish or fail).
- **Descendants →** none (task has not started; no children exist yet).
- **Parent →** no direct effect. Parent is waiting for this task to be terminal; BLOCKED is non-terminal, so parent is now stuck.

---

#### BLOCKED → PENDING

**Trigger:** The predecessor that was FAILED is restarted (transitions to PENDING).

**Propagation:**
- Incoming edge from restarted predecessor resets to EDGE_PENDING.
- This task returns to PENDING (not READY — predecessor must complete again before this becomes READY).
- **Successors →** cascade PENDING rightward: successors that were BLOCKED because of this task → PENDING (they can re-evaluate once the chain resolves).

---

#### READY → RUNNING

**Trigger:** Worker picks up `task/ready` event and begins execution.

**Propagation:** None.

---

#### RUNNING → COMPLETED

**Trigger:** Worker returns success; `persist_outputs` writes to `RunResource`.

**Propagation:**
- **Outgoing edges →** flip to `EDGE_SATISFIED`.
- **Successors (horizontal) →** for each successor, re-evaluate all incoming edges:
  - All `EDGE_SATISFIED` → successor → READY
  - Any predecessor FAILED → successor stays BLOCKED
  - Any predecessor still PENDING/RUNNING → successor stays PENDING
- **Descendants (vertical) →** this task does NOT finalise as COMPLETED until all descendants are terminal. The propagation loop waits. If descendants are BLOCKED, this task is stuck.
- **Parent →** when this task becomes terminal, parent re-evaluates its completion condition. No transition is triggered yet; the parent waits for all its children.

---

#### RUNNING → FAILED

**Trigger:** Worker raises an unrecoverable error.

**Propagation:**
- **Successors (horizontal) →** each successor that is PENDING or READY → BLOCKED. RUNNING successors are not interrupted.
- **Descendants (vertical) →** each descendant that is PENDING or READY → BLOCKED. RUNNING descendants are not interrupted (they continue executing; they will succeed or fail on their own).
- **Parent →** no direct effect. Parent is waiting for all children to be terminal. BLOCKED descendants are non-terminal, so parent is now stuck.
- **Run-level →** `RunRecord.status` stays `RUNNING`. The run is not automatically failed. It is stuck.

**What does NOT happen:**
- Successors are not CANCELLED.
- Descendants are not FAILED (they didn't run and error — their predecessor did).
- `RunRecord` does not become FAILED.

---

#### FAILED → PENDING (restart)

**Trigger:** Operator calls `restart_task()`.

**Propagation:**
- **Own outgoing edges →** reset to `EDGE_PENDING`.
- **Successors (horizontal) →** successors that are BLOCKED because of this task → PENDING. Their incoming edge from this task resets to `EDGE_PENDING`. They re-evaluate when this task eventually completes.
- **Descendants (vertical) →** full subtree reset: **all descendants → PENDING** regardless of prior status, including previously COMPLETED ones. This is intentional: the new execution gets a fresh container; prior outputs are bound to the old container's context. Roots within the subtask group are dispatched via `task/ready`. Non-roots wait for propagation within the subtask group.
- **Parent →** no direct effect.

**Design note on plan_subtasks:** When the restarted task re-executes, it will call `plan_subtasks()` again. The prior children (now reset to PENDING) must be cancelled first, and the new execution creates a fresh set of children. Resetting to PENDING and then calling `plan_subtasks()` again would create duplicate child generations. The correct restart sequence is: cancel prior descendants → reset own edges → dispatch `task/ready` → new execution creates fresh children via `plan_subtasks()`.

---

#### Any non-terminal → CANCELLED

**Trigger:** Operator calls `cancel_task()` (cause: `manager_decision`) or parent reaches CANCELLED (cause: `parent_cancelled`).

**Propagation:**
- **Descendants (vertical) →** all descendants → CANCELLED (orphaned; their execution context is gone).
- **Successors (horizontal) →** stay BLOCKED. The cancelled task still did not produce outputs; successors cannot proceed. They are waiting, not orphaned. The operator must separately cancel them or find another path forward.
- **Parent →** no direct effect. CANCELLED is terminal; parent re-evaluates its completion condition.

---

### Upward propagation (child → parent)

When a child reaches a terminal status, the parent re-evaluates whether it can finalise.

| Child terminal status | Parent effect |
|----------------------|--------------|
| COMPLETED | Re-evaluate: if all children terminal → parent finalises (see below) |
| FAILED | Children that are BLOCKED are non-terminal → parent stuck |
| CANCELLED | Terminal. If all children terminal → parent evaluates |
| BLOCKED | Non-terminal → parent stuck |

**Parent finalisation:** When all descendants are terminal, the parent evaluates:

| Descendant terminal states | Parent result |
|---------------------------|--------------|
| All in `{COMPLETED, CANCELLED}` | Parent → COMPLETED (propagate normally) |
| Any FAILED | Parent → FAILED (its sub-execution did not fully succeed) |

---

## 4. RunRecord Lifecycle

`RunRecord` tracks the run-level view. It does **not** get a BLOCKED status.

| Status | Meaning |
|--------|---------|
| `CREATED` | Run record created; workflow not yet started |
| `RUNNING` | Workflow executing — includes stuck/blocked state |
| `COMPLETED` | All tasks terminal in `{COMPLETED, CANCELLED}`; scores aggregated |
| `FAILED` | Operator explicitly failed the run, or a run-level timeout fired |
| `CANCELLED` | Operator cancelled the run; all non-terminal tasks cascade to CANCELLED |

**Stuck detection:** A run with BLOCKED tasks shows `RUNNING`. Monitoring detects stuck runs by: `RunRecord.status == RUNNING` with no `RunGraphMutation` rows newer than a configurable threshold (e.g. 30 minutes). This is preferable to a `BLOCKED` RunRecord status because the condition is transient — once the operator restarts the failed task, the run is live again.

---

## 5. Schema Changes Required

### A. Add `BLOCKED` to node status and task execution status

```sql
-- Postgres enum extension (non-transactional; run outside a transaction block)
ALTER TYPE taskexecutionstatus ADD VALUE IF NOT EXISTS 'blocked';
```

- Add `BLOCKED = "blocked"` to `TaskExecutionStatus` in `ergon_core/core/persistence/shared/enums.py`
- Update `TERMINAL_STATUSES` in `status_conventions.py` — BLOCKED is **non-terminal**
- Alembic migration required

### B. Add `triggered_by_mutation_id` to `RunGraphMutation` (assumption L)

```sql
ALTER TABLE rungraphmutation
ADD COLUMN triggered_by_mutation_id UUID REFERENCES rungraphmutation(id);
```

- Add field to `RunGraphMutation` model
- All cascade-produced mutations must populate this field
- Alembic migration required

### C. Move `sandbox_id` from `RunRecord.summary_json` to `RunTaskExecution` (assumption A)

```sql
ALTER TABLE runtaskexecution ADD COLUMN sandbox_id VARCHAR;
```

- Remove sandbox_id from `RunRecord.summary_json`
- `run/cleanup` collects all `RunTaskExecution.sandbox_id` values for the run and terminates each
- Alembic migration required

### D. Remove `StubSandboxManager` and `is_stub_sandbox_id` from production code (assumption B)

No schema change — code cleanup only (four files, see violated assumption B).

### E. Add `batch_operation_id` to `RunGraphMutation` (bulk operations)

```sql
ALTER TABLE rungraphmutation
ADD COLUMN batch_operation_id UUID;

CREATE INDEX ON rungraphmutation (batch_operation_id)
WHERE batch_operation_id IS NOT NULL;
```

- Add field to `RunGraphMutation` model; `NULL` for non-batch mutations
- All mutations (direct + cascade) from a single bulk operator request share the same `batch_operation_id`
- Alembic migration required

---

## 6. Impact on Integration Spec

The following tests in `2-control-flow-spec.md` need rewriting against these semantics:

| Test | Current (wrong) | Correct |
|------|----------------|---------|
| Test 3 — failure cascade | Successors → CANCELLED with cause `dep_invalidated` | Successors → BLOCKED; nothing is cancelled |
| Test 6 — manager_decision cancel | Successors → BLOCKED (this part was correct) | Confirmed correct; add assertion `RunRecord.status == RUNNING` not FAILED |
| Test 7 — parent failure cascade | Children → FAILED | Children → BLOCKED; FAILED is only for tasks whose worker errored |
| Violated assumption J | "children should be FAILED not CANCELLED" | Correct target is BLOCKED, not FAILED |

---

## 8. Bulk Status Operations

Operators need to atomically move multiple tasks to different statuses in a single request — e.g., restart three tasks, cancel two others, and manually unblock one. This section specifies the semantics required for that to be safe.

### Request shape

```
PATCH /runs/{run_id}/tasks/status
{
  "changes": [
    { "task_id": "<uuid>", "target_status": "PENDING", "cause": "operator_restart" },
    { "task_id": "<uuid>", "target_status": "CANCELLED", "cause": "manager_decision" },
    { "task_id": "<uuid>", "target_status": "PENDING", "cause": "operator_unblock" }
  ]
}
```

Returns: the full set of `RunGraphMutation` rows created (direct + cascades).

---

### Execution protocol

#### Step 1 — Pre-flight validation (before any write)

For every `(task_id, target_status)` entry:

1. **FSM validity**: the transition `current_status → target_status` must appear in the transition table (section 3), including the two new operator transitions added below. Reject the entire batch on any violation.
2. **Duplicate detection**: if the same `task_id` appears more than once in the batch, reject the entire batch.
3. **Task existence**: all `task_id` values must exist in `RunGraphNode` for this run. Reject on unknown ID.

No writes occur during this phase. A batch that fails validation leaves the database unchanged.

#### Step 2 — Apply in topological order

Sort the `changes` list by the dependency graph topology (predecessors before successors). Within the same topological rank: **restarts before cancellations**, so that cascade-BLOCKED unlocking resolves before cancellations potentially re-BLOCK downstream tasks.

Apply each transition as a normal `RunGraphMutation` write (status column update + WAL row). All writes share the same `batch_operation_id` (see schema change E below).

#### Step 3 — Single propagation pass

After all specified transitions are written, run one propagation pass over the full affected subgraph (all successors and descendants of every changed task). Do not run propagation after each individual change — this avoids transient intermediate states being observed or emitted as events.

#### Step 4 — Cascade WAL attribution

Every cascade mutation produced by the propagation pass in Step 3 gets:
- `triggered_by_mutation_id` = the `RunGraphMutation.id` of the specific batch item that caused it
- `batch_operation_id` = same UUID as the rest of the batch

This makes "what did this bulk edit actually touch?" a single-key query on `batch_operation_id`.

---

### New operator FSM transitions

Two transitions not in the section 3 table are required for bulk edits to be useful:

| From | To | Cause | Notes |
|------|----|-------|-------|
| `BLOCKED` | `PENDING` | `operator_unblock` | Operator asserts "ignore the failed predecessor; re-evaluate this task." Incoming edge from the failed predecessor is reset to `EDGE_PENDING`. The failed predecessor is still FAILED — the operator is bypassing it, not fixing it. |
| `FAILED` | `CANCELLED` | `manager_decision` | Operator gives up on a task without restarting it. Propagates: all descendants → CANCELLED; successors stay BLOCKED (they still lack this task's outputs). |

`operator_unblock` requires explicit intent — it must not fire automatically. It is only reachable via a bulk or single-task operator call, never from propagation logic.

---

### Atomicity guarantee

The entire batch — Steps 2, 3, and 4 — executes inside a single database transaction. Either all mutations commit or none do. Inngest events (`task/ready`, etc.) are sent only after the transaction commits.

---

### Schema change E — `batch_operation_id` on `RunGraphMutation`

```sql
ALTER TABLE rungraphmutation
ADD COLUMN batch_operation_id UUID;
```

- Populated for all mutations (direct + cascade) that originate from a bulk operator request.
- `NULL` for single-task operator actions and for propagation-only cascades not part of a batch.
- No FK constraint — it is a correlation tag, not a parent row reference.
- Add index: `CREATE INDEX ON rungraphmutation (batch_operation_id) WHERE batch_operation_id IS NOT NULL;`

`batch_operation_id` is orthogonal to `triggered_by_mutation_id` (assumption L): the former groups by operator request, the latter traces causal lineage within that request.

---

### Impact on integration spec

Add to `2-control-flow-spec.md`:

| Test | Spec |
|------|------|
| Test B-1 — batch restart | 3-task linear chain: A→B→C all BLOCKED after A fails. Bulk restart A + manually unblock B. Assert: A → PENDING; B → PENDING (via `operator_unblock`); C → PENDING (via cascade); all share `batch_operation_id`; `triggered_by_mutation_id` on C points to B's mutation. |
| Test B-2 — batch conflict rejection | Batch with same task appearing twice with different targets. Assert: 422, no mutations written. |
| Test B-3 — batch FSM violation rejection | Batch with `RUNNING → PENDING` (not in FSM). Assert: 422, no mutations written. |
| Test B-4 — batch FAILED → CANCELLED | Task with descendant subtasks, all BLOCKED. Operator bulk-cancels the FAILED task. Assert: FAILED task → CANCELLED; descendants → CANCELLED; successors remain BLOCKED. |

---

## 9. Concurrency and Race Prevention

The current system has no explicit locking model. `only_if_not_terminal` is a weak guard — it prevents writing over a terminal status, but it does not prevent two concurrent non-terminal writes from interleaving. Under load, this produces silent lost updates and stuck runs.

---

### 9.1 Races that exist today

| Race | Scenario | Observed symptom |
|------|----------|-----------------|
| **Fan-in double dispatch** | Two predecessors of task C complete ~simultaneously. Both propagation handlers read each other's status before the write commits → both conclude "all predecessors COMPLETED" → both emit `task/ready` for C | C executes twice; second execution corrupts or duplicates outputs |
| **`task/ready` duplicate delivery** | Inngest provides at-least-once delivery. `task/ready` re-delivered after transient failure → second worker picks up the same task | Same as above |
| **Restart vs completion** | Worker commits COMPLETED for task A while operator restart is in-flight (FAILED→PENDING). COMPLETED propagation runs after the restart commits, clobbers PENDING | Task stuck in inconsistent state; successors may not be correctly unblocked |
| **Bulk batch vs concurrent propagation** | Bulk batch is modifying task B; simultaneously a worker completes B's predecessor → propagation also writes to B | Lost update — one write silently overwrites the other; final state depends on timing |
| **Operator cancel vs propagation** | Propagation is computing B→READY. Concurrently, operator cancels B. Both writes race | B ends up READY when it should be CANCELLED; a worker picks it up |
| **BLOCKED cascade interleave** | Task A fails → successors of A cascade to BLOCKED. Concurrently, task D (another predecessor of B) completes → propagation tries to set B→READY | B oscillates or lands in wrong state |

---

### 9.2 Required locking model

#### Rule 1 — Row-level lock before every status write

Any code path that writes `RunGraphNode.status` must first acquire a `SELECT ... FOR UPDATE` lock on the row. No exceptions. This serializes concurrent writes to the same node.

```sql
-- Pattern: lock then check-and-write
SELECT status FROM run_graph_node WHERE id = $1 FOR UPDATE;
-- (validate FSM transition is legal)
UPDATE run_graph_node SET status = $2 WHERE id = $1;
```

#### Rule 2 — Propagation locks the full affected subgraph before reading

When a propagation pass begins (triggered by any terminal transition), it must:

1. Compute the set of nodes it may write to (all successors + descendants of the triggering node).
2. Acquire `SELECT ... FOR UPDATE` on all of them **in `id` order** before reading any status. Ordering prevents deadlocks between two concurrent propagation passes that overlap on different subsets.
3. Read → compute → write within the same transaction.

Locking in `id` order is a hard requirement. Two propagation passes that lock in arbitrary order will deadlock.

#### Rule 3 — Bulk batch locks everything before pre-flight validation

Pre-flight validation (Section 8, Step 1) must not read any `RunGraphNode` status before first locking all directly-specified nodes **plus their full containment subtrees**. This prevents a concurrent propagation pass from modifying a node between the validation read and the write.

Lock acquisition order: same `id ASC` rule.

#### Rule 4 — `task/ready` handler: CAS on READY→RUNNING

The `task/ready` Inngest handler must, as its **first database operation**, execute:

```sql
UPDATE run_graph_node
SET status = 'RUNNING'
WHERE id = $node_id AND status = 'READY'
RETURNING id;
```

If 0 rows returned: exit immediately without creating a `RunTaskExecution`. The task was already picked up by a concurrent worker or was cancelled between dispatch and pickup. This is the only safe guard against duplicate delivery; the `only_if_not_terminal` check alone is insufficient because RUNNING is non-terminal.

---

### 9.3 Intra-batch conflict types

The pre-flight validation in Section 8 covers direct duplicates. Under concurrency, two additional conflict classes matter:

#### Class 1 — Cascade supersession (reject)

A batch that cancels task A and also restarts a descendant of A is incoherent: the cancel cascade will immediately CANCEL the descendant, making the restart a no-op at best and a state corruption at worst.

**Pre-flight check:** Compute the full cancellation cascade for every `→ CANCELLED` entry in the batch. If any node in that expansion also appears as a `→ PENDING` (restart or unblock) entry, reject the entire batch.

```
batch: cancel A, restart C (where C is a descendant of A)
cascade(cancel A) = {A, B, C, D, ...}
C ∈ cascade(cancel A) AND C ∈ restart targets → REJECT
```

#### Class 2 — Dependency incoherence (warn, allow, cancel wins)

A batch restarts task A and also explicitly cancels A's only non-failed successor B. The restart will propagate to unblock B, but the explicit cancel overrides it. This is not incoherent — the operator is saying "restart A but don't proceed to B." Cancel wins because it is an explicit operator instruction.

**Behavior:** Allow. Apply in topological order (restart A first, then cancel B). The explicit cancel in the batch takes precedence over any cascade that restart A would have triggered for B. Log a warning: "explicit cancel of B overrides cascade from restart of A."

#### Class 3 — Redundant cascade (allow, idempotent)

A batch restarts A (which would propagate B to PENDING via cascade) and also explicitly unblocks B. Both want B→PENDING. This is idempotent.

**Behavior:** Allow. Pre-flight removes the explicit B entry from the write list (it will be produced by the cascade anyway) and records it as a no-op in the batch response.

---

### 9.4 What the spec guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| Single status write is atomic | One transaction; row lock held throughout |
| Bulk batch is atomic | One transaction; all locks acquired before first write |
| Two concurrent writes to the same node cannot interleave | Row lock (`SELECT FOR UPDATE`) |
| `task/ready` is idempotent under duplicate delivery | READY→RUNNING CAS guard (Rule 4) |
| Propagation reads consistent state | Full subgraph locked before any read (Rule 2) |
| No deadlock between concurrent propagation passes | Locks acquired in `id ASC` order (Rules 2 & 3) |

**What the spec does NOT guarantee:**

- Global ordering of events across unrelated nodes in the same run. Two unrelated tasks completing simultaneously will have their propagation passes interleave at the run level — each node's writes are serialized, but the relative order of writes to different nodes is not. This is fine.
- Starvation freedom. A propagation pass over a large subtask group holds many row locks. Short single-task operations on nodes within that subtask group will wait. This is an acceptable tradeoff.

---

### 9.5 Impact on integration spec

Add to `2-control-flow-spec.md`:

| Test | Spec |
|------|------|
| Test R-1 — fan-in double dispatch | Two-predecessor fan-in. Simulate both predecessors completing in the same millisecond (hold first commit with advisory lock until second is ready, release both). Assert: exactly one `task/ready` emitted for the fan-in task; exactly one `RunTaskExecution` row created. |
| Test R-2 — duplicate `task/ready` delivery | Inject duplicate `task/ready` event for an already-RUNNING task. Assert: handler exits without creating a second `RunTaskExecution`; node stays RUNNING. |
| Test R-3 — cascade supersession rejection | Batch: cancel parent A + restart child C. Assert: 422, no mutations written, error body identifies C as the superseded node. |
| Test R-4 — concurrent operator cancel vs propagation | Task B is PENDING; its predecessor completes (propagation starts, B→READY in-flight). Concurrently cancel B. Assert: B ends up CANCELLED (not READY); no `task/ready` emitted for B. |

---

## 10. Agent-Facing Graph Tools

The operator-facing interfaces (Sections 8–9) allow humans to manage stuck runs. This section specifies two toolkit tools that expose equivalent power to agents during execution — letting agents self-diagnose and self-recover without operator involvement.

The design principle: **composability without raw access.** Agents get the full expressiveness of the FSM through validated interfaces. They do not get raw database writes that bypass the consistency invariants Sections 8–9 exist to enforce.

---

### 10.1 Motivation

The current toolkit exposes single-task atomic operations (`plan_subtasks`, `cancel_task`, `restart_task`). An agent that encounters a partially-stuck subtask group must either give up, call tools in sequence hoping no race occurs between calls, or wait for an operator. None of these are good.

The analogy: LLMs get very far with bash not because bash bypasses OS invariants, but because it exposes the full expressive power of the OS through one composable interface. The equivalent here is an agent that can:
1. **Read** the full current graph state to self-diagnose
2. **Write** any valid combination of FSM transitions atomically

These two tools together give agents a near-arbitrary action space over the run graph while keeping the consistency guarantees intact.

---

### 10.2 `query_run_graph` — read tool

**Signature:**
```python
query_run_graph(
    run_id: UUID,
    *,
    scope: Literal["run", "subtree"] = "subtree",
    include_wal: bool = False,
) -> RunGraphSnapshot
```

**Scope parameter:**
- `"subtree"` (default): returns only the calling task's containment subtree — its own descendants via `parent_node_id`. This is safe by default: an agent cannot observe sibling tasks' internal state or other agents' work.
- `"run"`: returns the full run graph. Allowed but recorded in the WAL with `actor="agent:query_run"`. Useful for agents that need to coordinate across the full run (e.g. a root orchestrator).

**Return shape:**
```python
class RunGraphSnapshot:
    nodes: list[NodeSnapshot]       # id, task_slug, status, parent_node_id, level
    edges: list[EdgeSnapshot]       # id, source_node_id, target_node_id, status
    mutations: list[MutationEntry]  # only if include_wal=True; full WAL for scope
    snapshot_at: datetime           # timestamp of the consistent read

class NodeSnapshot:
    node_id: UUID
    task_id: UUID | None
    task_slug: str
    status: NodeStatus              # includes BLOCKED
    parent_node_id: UUID | None
    level: int
    blocked_by: list[UUID] | None   # node_ids of FAILED predecessors, if BLOCKED
```

`blocked_by` is the most important field: it tells the agent *which* predecessor caused the BLOCK, so it can decide whether to restart that predecessor, unblock itself, or escalate.

**Consistency guarantee:** the snapshot is taken inside a single transaction with `REPEATABLE READ` isolation. The agent sees a consistent graph state, not a mix of pre- and post-propagation values.

**No WAL by default.** Including the WAL (`include_wal=True`) is expensive on large runs; agents should only request it when diagnosing causality (e.g. "why did this task fail three times?").

---

### 10.3 `bulk_update_tasks` — write tool

**Signature:**
```python
bulk_update_tasks(
    changes: list[TaskStatusChange],
    *,
    scope_check: bool = True,
) -> BulkUpdateResult
```

```python
class TaskStatusChange:
    task_id: UUID
    target_status: NodeStatus
    cause: AgentCause

AgentCause = Literal[
    "agent_restart",       # agent restarting a failed subtask
    "agent_cancel",        # agent explicitly cancelling a subtask it owns
    "agent_unblock",       # agent unblocking a BLOCKED subtask (operator_unblock equivalent)
]
```

**Relationship to Section 8:** This is the Section 8 bulk endpoint exposed as a toolkit function. It uses the same four-step protocol: pre-flight validation → topological application → single propagation pass → WAL attribution. All mutations share a `batch_operation_id`; cascade mutations carry `triggered_by_mutation_id`.

The only differences from the operator endpoint:
1. **Scope restriction** (see below)
2. **Cause vocabulary**: `agent_*` causes are used instead of `manager_decision` / `operator_restart`, keeping operator and agent mutations distinguishable in the WAL
3. **`batch_operation_id` carries the calling task's `execution_id`**: every bulk mutation emitted by an agent is traceable back to the specific execution that issued it

**Scope restriction — what agents can and cannot modify:**

By default (`scope_check=True`), an agent may only modify tasks within its own containment subtree — nodes where `parent_node_id` is the calling task's node, or further descendants. Attempting to modify a sibling, a parent, or an unrelated task raises a `ScopeViolationError` and the entire batch is rejected.

```
Calling task: parent
├── child-A  ← agent CAN modify (direct child)
│   └── grandchild-A1  ← agent CAN modify (descendant)
└── child-B  ← agent CAN modify

sibling (same level as parent)  ← agent CANNOT modify
parent itself                   ← agent CANNOT modify its own status
```

Root orchestrator agents (tasks with `parent_node_id IS NULL`) may set `scope_check=False` to modify the full run graph. This opt-out is recorded in the WAL.

**Why not allow agents to modify siblings?** Sibling tasks may be running concurrently under different agents. Cross-subtree writes create exactly the races Section 9 was designed to prevent, now driven by two concurrent agents instead of two concurrent propagation passes. The scope restriction is the agent-level equivalent of the locking model's `id ASC` rule: it prevents deadlock by making the locking hierarchy explicit.

**FSM validation still runs.** `bulk_update_tasks` does not bypass the FSM. An agent that attempts `RUNNING → PENDING` gets a 422 just like an operator would. The agent's broader action space comes from being able to combine multiple valid transitions atomically, not from bypassing validity constraints.

**Example — agent self-heals a stuck subtask group:**

```python
# Agent observes its subtask group via query_run_graph:
snapshot = query_run_graph(run_id, scope="subtree")

# Three tasks are BLOCKED because child-A failed.
# Agent decides: restart child-A; the others will unblock via propagation.
failed = [n for n in snapshot.nodes if n.status == "failed"]
blocked = [n for n in snapshot.nodes if n.status == "blocked"]

result = bulk_update_tasks([
    TaskStatusChange(task_id=failed[0].task_id, target_status="pending", cause="agent_restart"),
])
# Propagation automatically unblocks the BLOCKED tasks after child-A completes.
# Agent doesn't need to enumerate them — the system handles cascade.
```

**Example — agent implements a novel orchestration pattern:**

```python
# Agent decides to abandon branch A and proceed with branch B.
# Cancels all of A's subtasks, unblocks B's subtasks.
result = bulk_update_tasks([
    TaskStatusChange(task_id=a1.task_id, target_status="cancelled", cause="agent_cancel"),
    TaskStatusChange(task_id=a2.task_id, target_status="cancelled", cause="agent_cancel"),
    TaskStatusChange(task_id=b1.task_id, target_status="pending",   cause="agent_unblock"),
])
```

This is the "bash-level flexibility" the operator interface cannot easily express: the agent is making a dynamic orchestration decision in a single atomic operation that the system designers did not anticipate.

---

### 10.4 What agents cannot do

These are explicit non-goals, not oversights:

| Forbidden | Why |
|-----------|-----|
| Write raw SQL / bypass FSM | Invalidates locking model, corrupts WAL |
| Modify tasks outside own subtree (default) | Creates agent-vs-propagation races |
| Set `RunRecord.status` directly | Run-level lifecycle is operator/system-only |
| Access other runs' data | Isolation boundary |
| Emit Inngest events directly | Event dispatch is the system's responsibility post-mutation |
| Write mutations without `batch_operation_id` | Every agent write must be attributable |

---

### 10.5 Shipping order

**Ship `query_run_graph` first.** Read-only, no consistency risk, immediately useful for agent observability. Agents can self-diagnose and log what they see before any write tools exist.

**Ship `bulk_update_tasks` only after Section 9 locking model is implemented.** The locking guarantees (Rule 1–4 from Section 9.2) must be in place before agents issue bulk writes. Without row-level locking, two concurrent agents modifying overlapping subtrees create exactly the races `bulk_update_tasks` is designed to avoid.

**Do not ship `scope_check=False` as a default.** The opt-out exists for root orchestrators. It should require an explicit flag in the agent's worker configuration, not just a runtime parameter, so the expanded scope is auditable at definition time.

---

### 10.6 Schema change F — `calling_execution_id` on `RunGraphMutation`

To make agent-issued mutations distinguishable from operator and system mutations, add:

```sql
ALTER TABLE run_graph_mutations
ADD COLUMN calling_execution_id UUID REFERENCES run_task_executions(id);
```

- Populated on every mutation produced by `query_run_graph` (`include_wal=True` reads) and `bulk_update_tasks` calls
- `NULL` for system propagation and operator mutations
- Combined with `batch_operation_id`: "find all mutations this specific agent execution issued across all its bulk calls" is `WHERE calling_execution_id = $1`

---

### 10.7 Impact on integration spec

Add to `2-control-flow-spec.md`:

| Test | Spec |
|------|------|
| Test AG-1 — agent self-heal | Parent spawns subtask group; one subtask fails → others BLOCKED. Agent calls `query_run_graph` → observes BLOCKED nodes with `blocked_by`. Agent calls `bulk_update_tasks` to restart the failed task. Assert: BLOCKED tasks → PENDING via cascade; run eventually COMPLETED; all mutations carry `calling_execution_id` of the parent task's execution. |
| Test AG-2 — agent scope violation | Agent attempts `bulk_update_tasks` targeting a sibling task (outside own subtree). Assert: `ScopeViolationError`, zero mutations written. |
| Test AG-3 — agent bulk cancel branch | Agent cancels multiple subtasks in one call. Assert: all target tasks → CANCELLED; WAL entries share `batch_operation_id` and `calling_execution_id`; run's other tasks unaffected. |
| Test AG-4 — snapshot consistency | Agent calls `query_run_graph` while a propagation pass is in-flight. Assert: snapshot reflects a consistent pre- or post-propagation state, not a mix; `snapshot_at` timestamp is accurate. |

---

## 7. Open Questions

**Q1: Can CANCELLED tasks be restarted?**
Currently restart requires FAILED or COMPLETED. Should CANCELLED also be restartable? Logically yes — operator cancelled by mistake. Needs a decision before `restart_task` logic is rewritten.

**Q2: Stuck detection threshold.**
What is the right "no WAL activity" threshold before a run is flagged as stuck? Depends on expected task duration. Should be configurable per experiment definition, not hardcoded.

**Q3: BLOCKED propagation through the containment tree upward.**
If a child is BLOCKED, the parent is stuck (it cannot finalise). Should the parent itself transition to BLOCKED to make this visible, or is "RUNNING with stuck children" an acceptable observable state? Current design says parent stays RUNNING; this may make dashboards harder to interpret.

**Q4: What happens to BLOCKED successors when the run is cancelled?**
If the operator cancels the run (`RunRecord → CANCELLED`), all non-terminal tasks should cascade to CANCELLED — including BLOCKED ones. This is clean. Needs explicit handling in the run cancellation handler.
