# Integration Tier Audit — 2026-04-23

Scope: `tests/integration/` only.

---

## Directory Structure

```
tests/integration/
├── conftest.py
├── smokes/
│   └── test_smoke_harness.py
├── swebench_verified/
│   ├── test_benchmark.py
│   ├── test_criterion.py
│   ├── test_rubric.py
│   ├── test_sandbox_manager.py
│   ├── test_smoke_e2e.py
│   ├── test_task_schemas.py
│   └── test_toolkit.py
└── minif2f/
    ├── test_sandbox_manager.py
    └── test_verification_integration.py
```

---

## What Is Actually Covered

| File | What it tests | Live infra required |
|------|--------------|-------------------|
| `smokes/test_smoke_harness.py` | seed → read → reset HTTP round-trip against a real server + Postgres | Server + Postgres |
| `swebench_verified/test_criterion.py` | `SWEBenchTestCriterion.evaluate()` with a mock `CriterionRuntime` | None |
| `swebench_verified/test_benchmark.py` | `build_instances()` with mocked `_load_rows` | None |
| `swebench_verified/test_task_schemas.py` | `SWEBenchInstance`, `SWEBenchTaskPayload` parsing, `_parse_test_list` | None |
| `swebench_verified/test_toolkit.py` | bash and str_replace_editor tools with a mock sandbox | None |
| `swebench_verified/test_rubric.py` | Rubric has one criterion named "test-resolution" with weight 1.0 | None |
| `swebench_verified/test_sandbox_manager.py` | Template resolution + `AsyncSandbox.create` call shape (mocked) | None |
| `swebench_verified/test_smoke_e2e.py` | Dockerfile and `e2b.toml.template` exist on disk | None |
| `minif2f/test_sandbox_manager.py` | Template resolution + sandbox create/verify lifecycle (mocked) — **3 tests uncollected** | None |
| `minif2f/test_verification_integration.py` | `ProofVerificationCriterion` — live test skipped without E2B key; static 'sorry' rejection test | Optional E2B |

**There are no Postgres persistence round-trip tests for `RunRecord`, `RunTaskExecution`, `RunResource`, or `RunGraphNode`. There are no Inngest event schema or propagation tests. The single test that exercises real infrastructure is `test_smoke_harness.py::test_seed_then_read_then_reset_roundtrip`, and it only asserts HTTP response codes — not Postgres state.**

---

## Existing Issues

### Critical

#### 1. Three tests have never been collected — `minif2f/test_sandbox_manager.py`

Three functions are named `testresolve_*` instead of `test_*`. pytest never collects them. They have passed in CI since they were written only because they are invisible to the runner.

```python
# Current — never collected:
def testresolve_template_falls_back_to_name_when_registry_missing(...): ...
def testresolve_template_prefers_registry_template_id(...): ...
def testresolve_template_falls_back_on_malformed_registry(...): ...

# Should be:
def test_resolve_template_falls_back_to_name_when_registry_missing(...): ...
def test_resolve_template_prefers_registry_template_id(...): ...
def test_resolve_template_falls_back_on_malformed_registry(...): ...
```

**Fix:** Rename the three functions. Zero-risk, one commit.

---

### High

#### 2. The Inngest preflight gates tests that do not use Inngest

`conftest.py` probes Inngest TCP connectivity at session start and calls `pytest.exit()` if it is unreachable. This applies to every file in `tests/integration/` regardless of whether the test needs Inngest.

Eight of the ten test files require no live infrastructure at all — they are fully mocked unit tests sitting behind the integration preflight for no reason. A ten-line rubric test that checks a list length cannot run in any environment without a running Inngest server.

**Fix:** Move the fully-mocked files to `tests/unit/` where they belong, or introduce a sub-conftest scoped only to the files that actually need Inngest.

#### 3. Eight of ten files are misclassified unit tests

Every file below needs no live infrastructure and is currently blocked behind the integration preflight:

- `swebench_verified/test_benchmark.py` — mocks `_load_rows`
- `swebench_verified/test_criterion.py` — mocks `CriterionRuntime`
- `swebench_verified/test_rubric.py` — instantiates a local object
- `swebench_verified/test_sandbox_manager.py` — mocks `AsyncSandbox`
- `swebench_verified/test_smoke_e2e.py` — filesystem stat only
- `swebench_verified/test_task_schemas.py` — pure data parsing
- `swebench_verified/test_toolkit.py` — mocks `AsyncSandbox`
- `minif2f/test_sandbox_manager.py` — mocks `AsyncSandbox`

These should live in `tests/unit/` and run under `pnpm run test:be:fast`.

---

### Medium

#### 4. `_reset_sandbox_singleton` fixture is duplicated

The fixture that resets `BaseSandboxManager` class-level state is defined independently in both `minif2f/test_sandbox_manager.py` and `minif2f/test_verification_integration.py`. It is identical in both files.

**Fix:** Extract to `tests/integration/minif2f/conftest.py`.

#### 5. The one real integration test covers a narrow happy path

`test_smoke_harness.py` has a single test: seed → read → reset, ending in a 404. It asserts HTTP status codes only. It does not assert Postgres state, does not test non-happy-path statuses, and does not verify that reset actually cascades to child rows.

---

## What the System Actually Is (and What Integration Tests Should Assert)

The integration tier is testing the wrong things because it is not oriented around the actual system model. Understanding that model is a prerequisite for knowing what to test.

### The system model

Ergon is an Inngest-driven, append-only workflow engine. Every meaningful invariant lives in Postgres. The unit of truth is **the database state after events settle**, not HTTP response codes.

The four persistence tables that record all meaningful state:

| Table | Purpose |
|-------|---------|
| `RunRecord` | One row per benchmark run; owns the run-level lifecycle status |
| `RunGraphNode` / `RunGraphEdge` / `RunGraphMutation` | DAG execution state; the WAL is the ground truth |
| `RunTaskExecution` | One row per execution attempt; records start/end, output, error |
| `RunResource` / `ThreadMessage` | Task outputs and agent-to-agent communication |

### The state machine

**Node statuses:** `PENDING → READY → RUNNING → {COMPLETED | FAILED | CANCELLED}`

Valid transitions only. The `only_if_not_terminal` guard prevents any second write once a node reaches `COMPLETED`, `FAILED`, or `CANCELLED`. This guard is the critical idempotency mechanism for concurrent event delivery.

**RunRecord statuses:** `CREATED → RUNNING → {COMPLETED | FAILED}`

`RunRecord.status == COMPLETED` is only valid if all nodes in the run are in `{COMPLETED, CANCELLED}`.

**Edge statuses:** `EDGE_PENDING → EDGE_SATISFIED | EDGE_INVALIDATED`

An edge flips to `EDGE_SATISFIED` when its source node reaches `COMPLETED`. It flips to `EDGE_INVALIDATED` when a downstream task is restarted and its prior completion is no longer valid.

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
      INSERT RunTaskExecution (status=PENDING)
      UPDATE RunGraphNode → RUNNING
      [sandbox_setup_fn]
      [worker_execute_fn]       ← worker code runs here
          optionally: plan_subtasks() → inserts child RunGraphNodes, emits task/ready for roots
          optionally: save_message() → inserts Thread + ThreadMessage
      [persist_outputs_fn]      → INSERT RunResource rows
      UPDATE RunTaskExecution (status=COMPLETED)
      UPDATE RunGraphNode → COMPLETED
      INSERT RunGraphMutation (audit entry)
      emit task/completed

    [on any failure]
      UPDATE RunTaskExecution (status=FAILED, error_json=...)
      UPDATE RunGraphNode → FAILED
      INSERT RunGraphMutation
      emit task/failed

task/completed  →  [propagate_execution]
      flip source edges → EDGE_SATISFIED
      check each dependent: if all incoming edges EDGE_SATISFIED → mark READY, emit task/ready
      if all nodes terminal → emit workflow/completed

task/failed  →  [propagate_execution]
      find all non-terminal dependents (direct + transitive)
      emit task/cancelled for each (cause=dep_invalidated)

task/cancelled  →  [cancel_orphans_fn]
      cascade CANCELLED to all non-terminal children (cause=parent_terminal)
      UPDATE RunTaskExecution → CANCELLED
      UPDATE RunGraphNode → CANCELLED
      INSERT RunGraphMutation

workflow/completed
  →  [complete_workflow_fn]
      aggregate scores from RunTaskExecution outputs
      UPDATE RunRecord (status=COMPLETED, completed_at=now, summary_json={scores})
      emit run/cleanup

workflow/failed
  →  [fail_workflow_fn]
      UPDATE RunRecord (status=FAILED, error_message=...)
      emit run/cleanup
```

### Subtask spawning (dynamic DAG mutation)

A worker can call `plan_subtasks()` or `add_subtask()` during execution. This inserts child `RunGraphNode` rows under the currently-executing node and immediately emits `task/ready` for the new roots. The containment tree is recorded via `parent_node_id` (self-referential FK) and `level` (precomputed depth: `parent.level + 1`).

**Key invariants of the subtask tree:**
- Every node with `parent_node_id != NULL` has `level == parent.level + 1`
- Cycle detection runs at `plan_subtasks` time; any cycle is rejected before any DB write
- The parent task does not finalize until all its children are terminal (the propagation loop handles this)

### The cancellation causes

When a `task/cancelled` event is emitted, the `cause` field records why:

| Cause | Trigger |
|-------|---------|
| `manager_decision` | Agent explicitly called `cancel_task(node_id)` via the toolkit |
| `parent_terminal` | Parent node reached COMPLETED, FAILED, or CANCELLED |
| `dep_invalidated` | A dependency failed; this task's inputs are no longer valid |
| `run_cancelled` | Run-level cancellation broadcast |

The WAL (`RunGraphMutation`) records the cause for every cancellation. This is the only place it is permanently stored.

### The restart / interrupt flow

`refine_task(node_id, new_description)` → updates description, allowed on any non-RUNNING node.

`restart_task(node_id)` → resets a terminal node back to `PENDING`. Also:
- Flips all outgoing `EDGE_SATISFIED` edges back to `EDGE_INVALIDATED`
- Emits `task/cancelled` for all non-terminal downstream nodes (their inputs are now stale)
- A new `task/ready` is emitted, incrementing `attempt_number` on the new `RunTaskExecution`

---

## The Nine Control Flows Integration Tests Must Cover

Each of these should use stub/mock workers (no E2B, no real LLM), submit a real event to the local Inngest dev server, poll until `RunRecord.status` is terminal, then assert the exact Postgres state.

### 1. Single-task happy path

Submit a run with one task and a worker that returns `WorkerOutput(success=True)`.

Assert:
- `RunRecord.status == COMPLETED`, `completed_at` is set
- `RunGraphNode.status == COMPLETED`
- `RunTaskExecution.status == COMPLETED`, `started_at ≤ completed_at`
- At least one `RunResource` row with correct `run_id` and `task_execution_id`
- `RunGraphMutation` WAL contains entries for `PENDING → RUNNING → COMPLETED`

### 2. Linear dependency chain — propagation

Three tasks A → B → C. All workers succeed.

Assert:
- Tasks reach `COMPLETED` in topological order (`completed_at` ordering: A before B before C)
- `RunGraphEdge` rows: all `EDGE_SATISFIED`
- After A completes, B transitions to `RUNNING` before C does (WAL timestamps)
- `RunRecord.status == COMPLETED`
- WAL has a `READY` transition for B only after A's `COMPLETED` entry, ditto C after B

### 3. Failure cascade — dep_invalidated

Tasks A → B → C. A succeeds. B fails. C never ran.

Assert:
- A: `COMPLETED`
- B: `FAILED`, `RunTaskExecution.error_json` non-null
- C: `CANCELLED`, no `RunTaskExecution` with `status == COMPLETED` or `RUNNING`
- WAL entry for C contains `reason` reflecting `dep_invalidated`
- `RunRecord.status == FAILED`
- No `RunResource` rows owned by C's execution

### 4. Diamond DAG — propagation convergence

Four tasks: root → left, root → right, left → sink, right → sink. All succeed.

Assert:
- `left` and `right` both reach `RUNNING` before `sink` becomes `READY`
- `sink` transitions to `READY` only after both `left` AND `right` are `COMPLETED` (both edges `EDGE_SATISFIED`)
- `sink` transitions to `READY` exactly once (the `only_if_not_terminal` idempotency guard is exercised — sink receives two "dep satisfied" signals)
- Final: all four `COMPLETED`, `RunRecord.status == COMPLETED`

### 5. Subtask spawning — dynamic DAG

A parent worker that calls `plan_subtasks()` with this spec:

```
root_child (no deps within the subtask group)
    ↓
leaf_child (depends on root_child)
```

Both `root_child` and `leaf_child` are **direct children of the parent node** — they share the same `parent_node_id = parent.id` and the same `level = parent.level + 1`. The `→` is a **dependency edge between two siblings**, not a nesting level. The sublayer is flat: a set of new `RunGraphNode` rows all at the same depth, with their own `RunGraphEdge` rows connecting them internally. `plan_subtasks()` must insert both the containment rows (`parent_node_id`) and the inter-sibling edges in the same operation.

Assert:
- Two `RunGraphNode` rows exist with `parent_node_id == parent_node.id`
- Both have `level == parent.level + 1`
- `root_child` was the only node to transition to `READY` immediately after subtask insertion (`leaf_child` was `PENDING` at that point — its edge was not yet satisfied)
- `leaf_child` transitions to `READY` only after `root_child` reaches `COMPLETED` (WAL timestamps)
- `leaf_child.status == COMPLETED`
- Parent node reaches `COMPLETED` only after both children are terminal
- WAL has a `PENDING` entry for `root_child` timestamped after parent reached `RUNNING`
- No `RunGraphEdge` exists pointing directly from parent to either child — the parent/child relationship is expressed by `parent_node_id`, not by graph edges

### 6. Cancellation: manager_decision

A run with two sibling tasks (`target` and `sibling`). `target` itself has a two-level subtask tree spawned during execution:

```
target (cancelled via manager_decision)
├── target-child-A
│   ├── target-grandchild-A1
│   └── target-grandchild-A2
└── target-child-B

sibling (independent; must NOT be affected)
└── sibling-child
```

Call `cancel_task(target.node_id)` while `target` is `RUNNING` and its subtree is live.

Assert — cancellation target:
- `target.status == CANCELLED`
- WAL entry for `target` has cause `manager_decision`
- `target`'s `RunTaskExecution.status == CANCELLED`

Assert — full subtree cascade (all descendants, not just direct children):
- `target-child-A`, `target-child-B`: `CANCELLED` with cause `parent_terminal`
- `target-grandchild-A1`, `target-grandchild-A2`: `CANCELLED` with cause `parent_terminal`
- WAL entries for each grandchild are timestamped after the corresponding child's `CANCELLED` mutation (the cascade propagates level by level, not all at once)
- No `RunTaskExecution` with `status IN (RUNNING, COMPLETED)` exists for any descendant

Assert — sibling isolation (the cancellation is contained to the subtree):
- `sibling.status` is unchanged (`RUNNING` or `COMPLETED`)
- `sibling-child.status` is unchanged
- WAL for `sibling` and `sibling-child` contains no `CANCELLED` entries

Assert — idempotency:
- Calling `cancel_task(target.node_id)` a second time returns an error
- WAL mutation count for `target` does not increase after the second call

### 7. Parent-failure cascade — FAILED propagates through the full containment tree

**Note:** The original framing (parent COMPLETED while children PENDING) is architecturally impossible — the propagation loop prevents it. The correct scenario is parent FAILED.

**Correct semantics:** When a parent fails, all non-terminal nodes in its containment subtree (all nodes reachable via `parent_node_id`, recursively through every sublayer) must become `FAILED` with cause `parent_failed`. `CANCELLED` is wrong here — it means "stopped intentionally before getting a chance to run." `FAILED` correctly signals "this execution context collapsed and this work did not complete."

The test must use a multi-level tree to verify the cascade goes all the way down:

```
parent (raises controlled exception during execution)
├── child-A (PENDING when parent fails)
│   ├── grandchild-A1 (PENDING)
│   └── grandchild-A2 (RUNNING)
└── child-B (RUNNING when parent fails)
└── child-C (COMPLETED before parent fails — must survive)
```

Assert:
- Parent: `FAILED`, `RunTaskExecution.error_json` non-null
- `child-A`, `child-B`: `FAILED` with cause `parent_failed` — **not** `CANCELLED`
- `grandchild-A1`, `grandchild-A2`: `FAILED` with cause `parent_failed` — cascade reaches grandchildren
- WAL entries for grandchildren are timestamped after their respective parent's `FAILED` mutation (cascade propagates level by level)
- `child-C`: remains `COMPLETED` — already-terminal nodes are not overwritten
- No non-terminal node in the containment subtree has any status other than `FAILED`
- `RunRecord.status == FAILED`

Assert the positive invariant (COMPLETED is unreachable while children are live):
- In tests 1 and 5, assert `RunRecord.status == COMPLETED` is only set after every `RunGraphNode` in the run is in `{COMPLETED, FAILED, CANCELLED}` — directly tests the propagation loop's wait-for-children guarantee

**Depth parametrisation:** Run this test parametrised over sublayer depths N=1, N=3, N=10. At N=10, every one of the 10 levels of containment descendants must be `FAILED` — not just direct children. This catches iterative vs recursive implementation bugs in the cascade where only the first level is processed.

### 8. Interrupt and restart — full containment subtree resets recursively

**Correct semantics:** Restarting a task is a full reset of its entire containment subtree — not just non-terminal nodes, but *all* nodes including previously `COMPLETED` ones, all the way down through every sublayer. The new execution starts in a fresh container; any work the old execution's subtasks produced is bound to that container's context and must not be assumed valid. The restart dispatches `task/ready` for the subtree roots only; propagation drives the rest.

A node with `parent_node_id != NULL` cannot be restarted independently — it can only be reset as part of its parent restarting. This must be enforced as a guard.

Use a task that previously ran and produced a two-level subtask tree:

```
parent (FAILED after prior execution)
├── child-root (COMPLETED in prior run — must be reset)
│   └── child-leaf (COMPLETED in prior run — must be reset)
└── child-standalone (FAILED in prior run — must be reset)
```

Also set up one DAG-level successor of `parent` (connected by a `RunGraphEdge`, not `parent_node_id`) that was `COMPLETED` in the prior run and must be invalidated.

**Step 1 — refine:**

`refine_task(parent.node_id, new_description)`:
- `parent.description` updated in `RunGraphNode`
- `parent.status` unchanged (still `FAILED`)

**Step 2 — restart:**

`restart_task(parent.node_id)`:

Assert — parent reset:
- `parent.status == PENDING`, then transitions to `RUNNING` once `task/ready` fires
- WAL records `FAILED → PENDING` with cause `operator_restart`
- New `RunTaskExecution` row created with `attempt_number` incremented

Assert — full containment subtree reset (all children, regardless of prior status):
- `child-root`, `child-leaf`, `child-standalone`: all reset to `PENDING`
- No node in the containment subtree retains `COMPLETED` or `FAILED` from the prior run
- Recursive: grandchildren reset alongside direct children

Assert — subtree root dispatch:
- `task/ready` fired for `child-root` only (it has no in-edges within the subtask group)
- `child-leaf` is `PENDING` waiting for propagation — it does NOT receive `task/ready` until `child-root` completes
- `child-standalone` is `PENDING` waiting for propagation (or `READY` if it has no deps)

Assert — DAG successor invalidated:
- The `RunGraphEdge` from `parent` to its DAG successor is reset to `EDGE_PENDING`
- The DAG successor transitions from `COMPLETED` to `CANCELLED` (its inputs are stale)

Assert — independent guard:
- Calling `restart_task(child-root.node_id)` directly (without going through the parent) raises an error — nodes with `parent_node_id != NULL` cannot be restarted independently

**Step 3 — restarted execution completes:**

Assert:
- All containment children reach `COMPLETED` via normal propagation
- `parent.status == COMPLETED`
- DAG successor re-activates (edges re-satisfied) and reaches `COMPLETED`
- `RunRecord.status == COMPLETED`
- Exactly two `RunTaskExecution` rows exist for `parent` (attempt 1 and attempt 2)

**Depth parametrisation:** Run this test parametrised over sublayer depths N=1, N=3, N=10. At N=10, every containment descendant at every level must be reset to `PENDING`, and `task/ready` must fire only for the roots at each level — not every node simultaneously. This validates that propagation, not bulk-dispatch, drives the non-root activations.

### 9. Communication service — message routing

A stub worker that calls `communication_service.save_message()` to send a message with `from_agent_id=leaf-X`, `to_agent_id=parent`, `thread_topic=smoke-completion`.

Assert:
- A `Thread` row exists scoped to `run_id` with the correct `topic`
- A `ThreadMessage` row exists with the correct `from_agent_id`, `to_agent_id`, `run_id`, `task_execution_id`
- `sequence_num == 1` for the first message in the thread
- A second message to the same thread gets `sequence_num == 2` (ordering guarantee)

### Edge Cases and Boundary Conditions

The nine control flows above cover the primary happy and failure paths. The tests below cover timing races, idempotency, forbidden graph structures, and boundary conditions that the primary tests do not exercise.

#### EC-1: Fan-in convergence race under failure

Setup: Diamond DAG — `root → left`, `root → right`, `left → sink`, `right → sink`. Arrange for left to FAIL at the same moment right is completing successfully. Use a sleep/barrier in the stub workers to make the race reproducible.

Two propagation events race to the `sink`: `dep_invalidated` (from left's failure) and `edge_satisfied` (from right's completion). Depending on which lands first, `sink` may briefly reach `READY` before being cancelled, or may be cancelled before it is ever activated.

Assert:
- `sink.status == CANCELLED` regardless of event arrival order
- `RunRecord.status == FAILED`
- `sink` has exactly ONE terminal WAL mutation (`CANCELLED`) — no `COMPLETED` entry exists for `sink`
- The `only_if_not_terminal` guard prevented any post-cancellation write if right's completion arrived after the cancellation

Mark `pytest.mark.slow` and run with `--count=5` to reliably trigger the race.

#### EC-2: Duplicate `task/ready` delivery — idempotency at prepare

Inngest guarantees at-least-once delivery. A duplicate `task/ready` event for a node that is already `RUNNING` must be a no-op.

This is a unit-tier test — no Inngest required. Seed a `RunGraphNode` in `RUNNING` state and a corresponding `RunTaskExecution`, then call the `prepare-execution` logic directly.

Assert:
- No second `RunTaskExecution` row is created
- No second sandbox is provisioned
- No duplicate `RUNNING` WAL entry exists
- The function returns without error (idempotent skip, not a crash)

#### EC-3: Cross-containment dependency edges are forbidden

A `RunGraphEdge` where `source.parent_node_id != target.parent_node_id` (i.e. the two endpoints live in different containment subtrees) must be rejected at graph construction time. Without this guard, cascade and restart logic would need to reason about cross-containment dependencies, which is undefined.

This is a unit-tier test.

Assert:
- `add_edge(source, target)` raises an error when `source.parent_node_id != target.parent_node_id`
- `add_edge` raises an error when one node has a `parent_node_id` and the other does not
- The error is raised before any DB write — no partial edge rows are created

#### EC-4: Evaluation after restart — which attempt's score counts

Setup:
1. Task completes (attempt 1) → `RunTaskEvaluation` row created with score X
2. `restart_task` is called → task re-runs (attempt 2) → second `RunTaskEvaluation` row created with score Y

Assert:
- Exactly two `RunTaskEvaluation` rows exist for the same `definition_task_id` and `run_id`
- `RunRecord.summary_json` reflects score Y (the most recent attempt), not score X
- The attempt-1 `RunTaskEvaluation` is preserved (append-only audit) but not used in the summary
- The row used in the summary can be identified by matching `execution_id` to the most recent `RunTaskExecution` for the node

If the system does not yet implement "use most recent attempt's score", mark as `pytest.mark.xfail(strict=True, reason="evaluation after restart: score selection across attempts not yet defined")`.

#### EC-5: Concurrency queue + node cancellation while queued

Context: `execute_task_fn` has `concurrency limit=15`. If a 16th `task/ready` fires, Inngest queues the invocation.

Setup: Saturate the 15 slots with long-running stub tasks, then fire a 16th `task/ready`. Cancel the 16th node via `cancel_task` while it is queued (before Inngest dispatches it).

Assert:
- When Inngest eventually dispatches the queued invocation, `prepare-execution` detects the node is `CANCELLED` and exits without creating a `RunTaskExecution` row
- No sandbox is provisioned for the cancelled node
- No `TaskCompletedEvent` or `TaskFailedEvent` is emitted for the cancelled node
- The node's WAL has a `CANCELLED` entry but no `RUNNING` entry

Mark `pytest.mark.slow` — requires saturating the concurrency pool.

---

## Cross-Cutting Invariants (shared assertion helpers)

These are properties that can be written once as helper functions and called from every test above.

| Invariant | What to assert |
|-----------|---------------|
| WAL completeness | Every `RunGraphNode` in the run has at least one `RunGraphMutation` entry |
| Execution coverage | Every node that reached `COMPLETED` or `FAILED` has a `RunTaskExecution` with non-null `completed_at` |
| No orphaned executions | Every `RunTaskExecution.node_id` references an existing `RunGraphNode` in the same run |
| RunRecord terminal consistency | `COMPLETED` implies all nodes are in `{COMPLETED, CANCELLED}`; `FAILED` implies at least one node is `FAILED` |
| Edge–node consistency | Every `EDGE_SATISFIED` edge has a source node with `status == COMPLETED`; every `EDGE_INVALIDATED` edge does not |
| Level consistency | Every node with `parent_node_id != NULL` has `level == parent.level + 1` |
| Append-only WAL | Mutation count for any given node only ever increases; no mutation rows are deleted or updated |
| Timeline consistency | `started_at ≤ completed_at` on every `RunTaskExecution` |

---

## How the Test Harness Should Work

Every test needs four ingredients:

**1. Stub workers** — workers that deterministically succeed, fail, or spawn subtasks with no E2B or LLM dependency. The system already has `training-stub` and the smoke worker fixtures. The integration tier needs its own small named set:
- `StubSuccessWorker` — returns `WorkerOutput(success=True)` immediately
- `StubFailWorker` — raises a controlled exception
- `StubSubtaskWorker(plan)` — calls `plan_subtasks()` with a provided spec, then succeeds

**2. A run submitter** — posts a `benchmark/run-request` event to the local Inngest dev server via the existing `inngest_client` and returns the `run_id`.

**3. A run poller** — polls `RunRecord.status` directly against Postgres until terminal. Times out with a clear message if convergence doesn't happen within a threshold (suggested: 30s for stub-only runs).

**4. Shared assertion helpers** — functions that take a `run_id` and assert the cross-cutting invariants above. These live in `tests/integration/helpers/` and are imported by every test, not copy-pasted.

The pattern for every test is then:

```python
run_id = submit_run(worker="stub-success", tasks=[...])
await wait_for_terminal(run_id, timeout=30)

assert_run_completed(run_id)           # RunRecord
assert_all_nodes_terminal(run_id)      # graph
assert_wal_complete(run_id)            # mutations
assert_executions_have_outputs(run_id) # telemetry
# ...plus test-specific assertions
```

---

---

## Beyond the Nine Flows: Additional Bulletproofing Categories

The nine control flows are about *runtime correctness* — does the system reach the right Postgres state after events settle? The categories below protect a different surface: *structural correctness* — does the codebase wire things up consistently in the first place? Some of these are best placed in the unit tier (no infra required), but they belong in the same TDD mandate.

---

### 10. Event Pub→Sub Call Graph (static analysis — unit tier)

**Problem:** A simple "every event name has a handler" check is one-directional. It catches orphaned event types (defined but nothing subscribes), but misses two equally dangerous failure modes:

1. **Dead handlers** — a handler is registered in `ALL_FUNCTIONS` but nothing in the codebase ever emits the event it listens for. The handler is live but unreachable.
2. **Missing fan-out** — an event should trigger multiple handlers (Inngest supports N subscribers per event), but one is missing from `ALL_FUNCTIONS`. Publisher and one subscriber are fine; the second subscriber is silently absent.

The fix is a bidirectional call graph: map every event to its expected publishers and expected subscribers, then assert both sides.

**How to build the graph:**

The subscriber side is trivially introspectable — `ALL_FUNCTIONS` is the source of truth:

```python
from ergon_core.core.runtime.inngest_registry import ALL_FUNCTIONS

def build_subscriber_map() -> dict[str, list[str]]:
    """event_name → [handler_id, ...]"""
    result: dict[str, list[str]] = {}
    for fn in ALL_FUNCTIONS:
        event = fn.trigger.event
        result.setdefault(event, []).append(fn.id)
    return result
```

The publisher side cannot be introspected automatically without AST analysis, so it is declared explicitly as a canonical fixture. This has a secondary benefit: the fixture **is the architecture document** for the event graph. Anyone reading it can trace the full flow.

```python
# tests/unit/state/test_event_call_graph.py

# Canonical pub→sub map. Each entry states:
#   publishers: which Inngest function IDs emit this event (or "external" for CLI/API entrypoints)
#   subscribers: which Inngest function IDs must handle it
EXPECTED_CALL_GRAPH: dict[str, dict[str, list[str]]] = {
    "benchmark/run-request": {
        "publishers": ["external:cli"],
        "subscribers": ["benchmark-run-start"],
    },
    "workflow/started": {
        "publishers": ["benchmark-run-start"],
        "subscribers": ["start-workflow"],
    },
    "task/ready": {
        # emitted by start-workflow (initial roots), by propagate-execution (after
        # dep satisfied), and by execute-task (when plan_subtasks inserts new roots)
        "publishers": ["start-workflow", "propagate-execution", "execute-task"],
        "subscribers": ["execute-task"],
    },
    "task/completed": {
        "publishers": ["execute-task"],
        "subscribers": ["propagate-execution"],
    },
    "task/failed": {
        "publishers": ["execute-task"],
        "subscribers": ["propagate-execution"],
    },
    "task/cancelled": {
        "publishers": ["propagate-execution", "cancel-orphans"],
        "subscribers": ["cancel-orphans"],
    },
    "workflow/completed": {
        "publishers": ["propagate-execution"],
        "subscribers": ["complete-workflow"],
    },
    "workflow/failed": {
        "publishers": ["propagate-execution"],
        "subscribers": ["fail-workflow"],
    },
    "run/cancelled": {
        "publishers": ["external:api"],
        "subscribers": ["cancel-run"],
    },
    "run/cleanup": {
        "publishers": ["complete-workflow", "fail-workflow"],
        "subscribers": ["cleanup-run"],
    },
    # criterion/evaluate: publishers unknown, subscribers MISSING — this is the live bug
    # this entry must be completed and a handler added before this test can pass
    "criterion/evaluate": {
        "publishers": [],   # TODO: identify where this is emitted
        "subscribers": [],  # BUG: no handler registered in ALL_FUNCTIONS
    },
}
```

**Three assertions from one fixture:**

```python
def test_every_declared_subscriber_is_registered():
    """All expected subscribers exist in ALL_FUNCTIONS."""
    registered = {fn.id for fn in ALL_FUNCTIONS}
    for event, graph in EXPECTED_CALL_GRAPH.items():
        for expected_sub in graph["subscribers"]:
            assert expected_sub in registered, (
                f"Event '{event}' expects handler '{expected_sub}' "
                f"but it is not in ALL_FUNCTIONS"
            )

def test_no_registered_handler_is_absent_from_call_graph():
    """Every handler in ALL_FUNCTIONS appears as a subscriber somewhere in the graph.
    A handler that appears in no event's subscriber list is unreachable dead code."""
    declared_subs = {s for g in EXPECTED_CALL_GRAPH.values() for s in g["subscribers"]}
    for fn in ALL_FUNCTIONS:
        assert fn.id in declared_subs, (
            f"Handler '{fn.id}' is registered in ALL_FUNCTIONS but does not appear "
            f"in EXPECTED_CALL_GRAPH — either add it or remove the handler"
        )

def test_every_declared_event_type_has_a_model_class():
    """Every event slug in the call graph has a corresponding Pydantic event model.
    Catches typos in the fixture and models that were deleted without updating the graph."""
    from ergon_core.core.runtime.events import all_event_models  # hypothetical collector
    known_slugs = {m.model_fields["name"].default for m in all_event_models()}
    for event in EXPECTED_CALL_GRAPH:
        assert event in known_slugs, (
            f"Event '{event}' in call graph has no corresponding event model class"
        )
```

**What this catches that the original one-liner missed:**

| Failure mode | Simple slug check | Call graph |
|---|---|---|
| Event defined, no handler | ✅ | ✅ |
| Handler registered, nothing emits to it | ❌ | ✅ |
| Event should fan out to N handlers, only N-1 registered | ❌ | ✅ |
| Event slug in graph but no Pydantic model class | ❌ | ✅ |
| Handler slug typo in `ALL_FUNCTIONS` | ❌ | ✅ |

**Concrete live example — `criterion/evaluate`:** The fixture above documents the bug explicitly. The test `test_every_declared_subscriber_is_registered` will fail on the `criterion/evaluate` entry the moment a subscriber is declared in the fixture but absent from `ALL_FUNCTIONS`. Until the fixture entry has a non-empty `subscribers` list AND a matching registered handler, the bug is recorded but the test doesn't crash the suite — which is the right behaviour during a fix. Add the handler, update the fixture, the test goes green.

---

### 11. Inngest Function Catalog Integrity (static analysis — unit tier)

**Problem:** `ALL_FUNCTIONS` could have duplicate slugs (two functions with the same name) or functions with no trigger at all. Inngest silently accepts duplicate registrations and last-write-wins, meaning one handler silently shadows another.

**What to test:**

```python
def test_no_duplicate_inngest_slugs():
    slugs = [fn.id for fn in inngest_registry.ALL_FUNCTIONS]
    assert len(slugs) == len(set(slugs)), f"Duplicate slugs: {[s for s in slugs if slugs.count(s) > 1]}"

def test_all_inngest_functions_have_event_trigger():
    for fn in inngest_registry.ALL_FUNCTIONS:
        assert hasattr(fn.trigger, "event"), f"{fn.id} has no event trigger"
```

---

### 12. Registry Integrity (static analysis — unit tier)

**Problem:** A slug can be registered in `BENCHMARKS`, `WORKERS`, `EVALUATORS`, or `CRITERIA` that points to a class that cannot be instantiated — wrong base class, missing required class vars, or import error at collection time.

**What to test:** For each registry (`CORE_BENCHMARKS`, `WORKERS`, etc.), assert that every value is a class, that it is a subclass of the correct ABC, and that it can be constructed with minimal arguments (or at least that `__init__` doesn't immediately raise on a no-arg call where no args are required). The `onboarding_deps` benchmark contract in `test_benchmark_contract.py` is a partial model for this; extend the pattern to all registries.

```python
@pytest.mark.parametrize("slug,cls", list(CORE_BENCHMARKS.items()))
def test_benchmark_registry_entries_are_valid_subclasses(slug, cls):
    assert issubclass(cls, Benchmark), f"{slug} is not a Benchmark subclass"
    assert hasattr(cls, "type_slug"), f"{slug} missing type_slug"
```

---

### 13. Event Payload Round-Trips (static analysis — unit tier)

**Problem:** All Inngest events are Pydantic models. A broken `model_dump()` / `model_validate()` cycle (e.g. a UUID field that serialises to a non-string in one environment) means events cannot be deserialized by the Inngest dev server or the handler.

**What to test:** For every concrete event class defined in `task_events.py`, `evaluation_events.py`, and `infrastructure_events.py`, construct a minimal valid instance, round-trip it through `model_dump()` + `model_validate()`, and assert equality. Use `mode="json"` on `model_dump` to catch UUID/datetime serialisation issues that only surface over the wire.

```python
@pytest.mark.parametrize("event_cls,kwargs", [
    (TaskReadyEvent, {"run_id": uuid4(), "node_id": uuid4(), ...}),
    ...
])
def test_event_round_trips(event_cls, kwargs):
    original = event_cls(**kwargs)
    payload = original.model_dump(mode="json")
    restored = event_cls.model_validate(payload)
    assert original == restored
```

---

### 14. Toolkit Tool Name Uniqueness (static analysis — unit tier)

**Problem:** The Inngest worker toolkit is assembled by combining tool lists from different providers. If two providers define a tool with the same `__name__`, the second silently shadows the first at the model-context level — the LLM sees duplicate names and the worker may call the wrong function.

**What to test:** For each registered worker class, instantiate its toolkit (with a mock sandbox/runtime) and assert that all tool `__name__` values within that toolkit are unique.

```python
def test_swebench_toolkit_tool_names_are_unique():
    tools = build_swebench_toolkit(sandbox=MockSandbox(), runtime=MockRuntime())
    names = [t.__name__ for t in tools]
    assert len(names) == len(set(names)), f"Duplicate tool names: {set(n for n in names if names.count(n) > 1)}"
```

---

### 15. Worker / Benchmark / Evaluator ABC Compliance (static analysis — unit tier)

**Problem:** Every concrete worker, benchmark, and evaluator must implement specific abstract methods. Python's ABC machinery only raises at *instantiation time*, not at import/collection time. A class that forgets to implement `execute()` passes all static checks until someone tries to run it.

**What to test:** Attempt instantiation of every registered concrete class (with minimal stub arguments) and assert no `TypeError` is raised for missing abstract methods. This goes one step beyond the subclass check in category 12.

```python
@pytest.mark.parametrize("slug,cls", list(WORKERS.items()))
def test_worker_is_fully_concrete(slug, cls):
    # Should not raise TypeError: Can't instantiate abstract class
    try:
        instance = cls.__new__(cls)
    except TypeError as e:
        pytest.fail(f"Worker '{slug}' is not fully concrete: {e}")
```

---

### 16. DB Schema Reflection (Postgres only — integration tier, no Inngest)

**Problem:** SQLModel generates table DDL from Python models. If a migration is applied in the wrong order or skipped, the live Postgres schema diverges from the models. This silently breaks writes to new columns or reads of renamed columns.

**What to test:** Connect to the Postgres instance, reflect every table that `SQLModel.metadata` knows about, and assert that every column on every model exists in the reflected schema with the correct type and nullability. This test needs Postgres but not Inngest, so it should be gated separately from the event-flow tests.

```python
def test_db_schema_matches_models(postgres_engine):
    from sqlalchemy import inspect
    inspector = inspect(postgres_engine)
    for table_name, table in SQLModel.metadata.tables.items():
        reflected_cols = {c["name"] for c in inspector.get_columns(table_name)}
        model_cols = {c.name for c in table.columns}
        assert model_cols <= reflected_cols, (
            f"Table '{table_name}' missing columns: {model_cols - reflected_cols}"
        )
```

---

### 17. Sandbox Container Builds (Docker — slow tier)

**Problem:** Each benchmark sandbox is built from a `Dockerfile` in the repo. A broken base image pin, a removed system package, or a pip install that fails silently produces a container that appears to build but crashes at runtime. This is only caught when someone actually tries to run a benchmark.

**Two Dockerfiles to test:**
- `ergon_builtins/benchmarks/minif2f/Dockerfile` (Lean4 toolchain)
- `ergon_builtins/benchmarks/swebench_verified/Dockerfile` (Python dev environment)

**What to test:** A `docker build` that must exit zero. These are slow (minutes each) and should be gated behind a `pytest.mark.docker_build` marker so they run in CI nightly but not on every PR push. A basic smoke: build succeeds, `docker run --rm <image> echo ok` exits zero.

```python
@pytest.mark.docker_build
@pytest.mark.parametrize("dockerfile_path,context_dir", [
    ("ergon_builtins/benchmarks/minif2f/Dockerfile", "ergon_builtins/benchmarks/minif2f/"),
    ("ergon_builtins/benchmarks/swebench_verified/Dockerfile", "ergon_builtins/benchmarks/swebench_verified/"),
])
def test_sandbox_container_builds(dockerfile_path, context_dir, tmp_path):
    result = subprocess.run(
        ["docker", "build", "-f", dockerfile_path, "-t", f"ergon-test-{tmp_path.name}", context_dir],
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, f"Docker build failed:\n{result.stderr}"
```

---

### 18. Concurrency Race: `only_if_not_terminal` Under Concurrent Cancellation (full-stack integration)

**Problem:** The `only_if_not_terminal` guard is the single mechanism preventing double-writes on a terminal node. If two `task/cancelled` events race to update the same node (which happens in diamond DAG failure cascades where multiple parents can independently trigger cancellation), one write must win and the other must be silently discarded. If the guard has a bug, the WAL gets a spurious second mutation and downstream assertions about node count and status are corrupted.

This is the hardest test to write and the one most likely to catch real bugs. It requires the full Inngest + Postgres stack.

**What to test:** Construct a DAG where a single leaf node has two parents, and both parents fail at approximately the same time. The leaf should receive two independent `task/cancelled` events nearly simultaneously. Assert:

- The leaf has exactly one `CANCELLED` `RunGraphNode` row
- The WAL for the leaf has exactly one `CANCELLED` mutation (no duplicate entries)
- The `RunRecord` reaches `FAILED` (not stuck)
- The `RunTaskExecution` for the leaf (if any was started) has a single terminal row

This test should be marked `pytest.mark.slow` and `pytest.mark.flaky_risk` with a note that it is exercising a race condition — it should be run with `--count=5` (using `pytest-repeat`) in CI to increase the chance of hitting the race.

---

## Summary

The current `tests/integration/` has one real integration test that checks HTTP response codes on a narrow happy path. The nine critical control flows above — propagation, failure cascade, subtask spawning, cancellation, restart, communication — have never had their Postgres state asserted at any tier.

The Postgres state after any interesting event sequence is the system's ground truth. That is what the integration tier should be testing.

The nine additional categories above protect structural correctness: events that are defined but never handled, duplicate tool names, schema drift, and concurrency races. Several of these (categories 10–15) are pure static analysis and belong in the unit tier — they require no running infrastructure and can fail fast in CI. Category 16 needs Postgres but not Inngest. Category 17 needs Docker and should run nightly. Category 18 needs the full stack and should run on every feature branch.

**Priority order for implementation:**

| Priority | Category | Tier | Value |
|----------|----------|------|-------|
| 1 | Fix 3 uncollected tests (`testresolve_*`) | Integration | Critical bug — tests have never run |
| 2 | Event subscriber coverage | Unit | Catches live `criterion/evaluate` orphan |
| 3 | Nine control flows | Integration | Core runtime correctness, zero coverage today |
| 4 | Inngest catalog + registry integrity | Unit | Cheap, high signal |
| 5 | DB schema reflection | Integration | Catches migration drift |
| 6 | Event payload round-trips | Unit | Catches serialisation bugs before they hit wire |
| 7 | Toolkit tool name uniqueness | Unit | Prevents silent shadowing |
| 8 | ABC compliance | Unit | Catches broken registrations at test time |
| 9 | Concurrency race | Full-stack | Validates the system's critical idempotency guard |
| 10 | Container builds | Docker/nightly | Catches broken sandbox images before E2E |

---

## Found Violated Assumptions

Issues discovered by reading the actual production code during this session. Each entry states what we assumed, what the code actually does, the concrete fix needed, and the integration test assertion that would have caught it.

---

### A. `run/cleanup` terminates one sandbox per run, not one per task execution

**Assumed:** Container teardown happens per task-execution-attempt; `run/cleanup` kills all of them at run end.

**Reality:** `run_cleanup.py:69` reads `run.parsed_summary().get("sandbox_id")` — a single string stored at run level. Only one sandbox ID is ever killed. If multiple tasks executed in parallel each had their own sandbox, all but the last one stored in the summary are silently leaked.

**Fix:** Store sandbox IDs on `RunTaskExecution` rows (or in a separate table), not in `RunRecord.summary_json`. `run/cleanup` should collect all sandbox IDs across all `RunTaskExecution` rows for the run and terminate each one.

**Integration test assertion:** After `run/cleanup` fires, query all `RunTaskExecution.sandbox_id` values for the run. For each non-stub ID, assert that `BaseSandboxManager.get(sandbox_id)` returns a terminated/not-found state.

---

### B. Stub sandbox logic (`is_stub_sandbox_id`) leaks into four production files

**Assumed:** Test infrastructure is confined to test code; the production path does not branch on whether a sandbox is "real" or a test stub.

**Reality:** `is_stub_sandbox_id` and `StubSandboxManager` are defined in `manager.py` and imported into three production Inngest handlers:

| File | Line | Usage |
|------|------|-------|
| `ergon_core/ergon_core/core/providers/sandbox/manager.py` | 578–613 | Definition of `_STUB_SANDBOX_PREFIX`, `is_stub_sandbox_id()`, `StubSandboxManager` |
| `ergon_core/ergon_core/core/runtime/inngest/run_cleanup.py` | 72 | Guards sandbox termination |
| `ergon_core/ergon_core/core/runtime/inngest/check_evaluators.py` | 96 | Guards evaluation dispatch |
| `ergon_core/ergon_core/core/runtime/inngest/execute_task.py` | 102–116 | Creates stub sandbox ID for stub-worker path |

**Fix:** Remove the stub concept from production code entirely. Tests should inject a real test-double at the `BaseSandboxManager` boundary (e.g. a subclass that returns a deterministic ID and no-ops on terminate) rather than relying on a magic string prefix to short-circuit production logic.

**Static analysis test assertion:** `is_stub_sandbox_id` must not be imported in any module outside of `tests/`. This can be a simple grep-based unit test.

---

### C. `evaluate_task_run` constructs `BenchmarkTask` with empty strings

**Assumed:** Evaluation runs against the actual task data (description, instance key, task slug) fetched from the database.

**Reality:** `evaluate_task_run.py:99–103` constructs `BenchmarkTask` with hardcoded empty strings:

```python
task = BenchmarkTask(
    task_slug="",
    instance_key="",
    description="",
)
```

The payload contains `task_id` and `execution_id` — enough to fetch the real data — but it is never queried. Criteria that inspect the task description or instance key for evaluation logic receive empty strings.

**Fix:** Fetch the `RunGraphNode` (or definition task) using `payload.task_id` before constructing `BenchmarkTask`. Populate `task_slug`, `instance_key`, and `description` from the DB row.

**Integration test assertion:** After evaluation completes, assert that `RunTaskEvaluation.summary_json` contains a non-empty `criterion_description` that matches the actual task description.

---

### D. `criterion_description`, `feedback`, and `evaluation_input` use empty-string defaults instead of nullable

**Assumed:** Missing evaluation fields are represented as `None`, not as empty strings.

**Reality:** `CriterionResultEntry` (and the `_build_evaluation_summary` call at `evaluate_task_run.py:114`) uses `feedback=cr.feedback or ""` and `evaluation_input=evaluation_input` (passed as `""`). These are suppressed by the `# slopcop: ignore[no-str-empty-default]` comments rather than fixed.

**Fix:** Change the fields to `str | None = None`. Update all callers to pass `None` instead of `""`. Remove the `slopcop: ignore` suppressions.

**Unit test assertion:** Construct a `CriterionResultEntry` with no feedback provided and assert `entry.feedback is None`, not `entry.feedback == ""`.

---

### E. `InngestCriterionExecutor` sandbox connection is unverified — may spin up its own container

**Assumed:** The evaluator reuses the still-standing task sandbox (the one that was kept alive specifically for rubric evaluation) by connecting to it via `payload.sandbox_id`.

**Concern:** `evaluate_task_run.py:82–90` creates `sandbox_manager = manager_cls()` and passes `payload.sandbox_id` into `TaskEvaluationContext`. Whether `InngestCriterionExecutor` actually connects to the existing sandbox via that ID — or ignores it and provisions a new one — is not verified by any test.

**File to investigate:** `ergon_core/ergon_core/core/runtime/evaluation/inngest_executor.py`

**Fix (pending investigation):** If `InngestCriterionExecutor` does not use `task_context.sandbox_id` to reconnect to the existing sandbox, it must be fixed to do so. Spinning up a second sandbox per evaluation doubles cost and breaks criteria that depend on inspecting the state the agent left behind in the original sandbox.

**Integration test assertion:** Run a task that leaves a known artefact in the sandbox, then run evaluation. Assert the criterion received access to that artefact (i.e. it executed against the same sandbox, not a fresh one).

---

### F. `restart_task` does not cancel stale subtask children from the prior execution

**Assumed:** Restarting a task invalidates all outputs from its prior execution, including subtask children it previously spawned via `plan_subtasks`.

**Reality:** `task_management_service.py::_invalidate_downstream` traverses outgoing `RunGraphEdge` only (the dependency DAG). It does not traverse the containment tree (`parent_node_id`). Subtask children from the prior execution are not touched.

**Consequence:** A restarted task that previously called `plan_subtasks` leaves its old children completed in the graph. When the task re-executes and calls `plan_subtasks` again, duplicate child nodes are inserted — one set from the old execution (status `COMPLETED`) and one from the new (status `PENDING`). The graph is now corrupt: two generations of children coexist under the same parent.

**Fix:** Before re-dispatching `task/ready` in `restart_task`, cancel all non-terminal descendants of the node (traversing `parent_node_id`) and reset any already-`COMPLETED` children to `CANCELLED` so the new execution starts from a clean subtask slate. This is the containment-axis equivalent of `_invalidate_downstream`.

**Integration test assertion (part of test 8 — interrupt and restart):** After restarting a task that previously spawned two subtasks, assert that those old subtask nodes have status `CANCELLED`. Assert that after the restarted task completes and spawns subtasks again, there are exactly two nodes with `parent_node_id == restarted_node.id` and both are in a non-stale terminal state — not four.

---

### G. `criterion/evaluate` event is defined but has no handler; `task/evaluate` is the actual evaluation trigger

**Assumed (from earlier in this audit):** `criterion/evaluate` / `CriterionEvaluationEvent` is the event that drives per-criterion evaluation and is simply missing its handler.

**Reality:** The actual evaluation handler (`evaluate-task-run`) is triggered by `task/evaluate`, not `criterion/evaluate`. `CriterionEvaluationEvent` in `evaluation_events.py` is a separate, orphaned event type with no handler anywhere in `ALL_FUNCTIONS`. It is unclear whether it is intended future infrastructure, dead code, or a vestige of a prior design.

**Fix:** Either wire a handler to `criterion/evaluate` if per-criterion fan-out is the intended design, or delete `CriterionEvaluationEvent` from `evaluation_events.py`. The call graph fixture in category 10 should be updated to reflect whichever path is chosen.

**Static analysis test assertion:** `criterion/evaluate` must either appear in `ALL_FUNCTIONS` as a trigger or must not exist as an event model class. The current state — defined but unhandled — must not pass the call graph test.

---

### H. Failed-attempt sandbox is not killed before the restart container starts; prior container leaks

**Assumed:** When a task is restarted, its failed attempt's sandbox is cleaned up before the new attempt begins.

**Reality:** `run_cleanup.py:69` reads `run.parsed_summary().get("sandbox_id")` — a single string stored at run level. Only one sandbox ID is ever killed. If multiple tasks executed in parallel each had their own sandbox, all but the last one stored in the summary are silently leaked.

This compounds on restart: every `task/ready` event provisions a fresh container (confirmed in `execute_task.py:140`). When a task fails and is restarted, the failed attempt's container is not killed at `task/failed` time — it sits live until `run/cleanup`. At that point `run/cleanup` kills whichever sandbox ID was last written to the summary, and the prior attempt's container leaks permanently.

**Fix:** Store sandbox IDs on `RunTaskExecution` rows, not in `RunRecord.summary_json`. `run/cleanup` should collect all sandbox IDs across all `RunTaskExecution` rows for the run and terminate each one. Additionally, kill the failed attempt's sandbox immediately when `task/failed` fires — don't defer to run-level cleanup.

**Integration test assertion:** After `restart_task` is called on a failed node, assert that the sandbox_id from the failed `RunTaskExecution` is no longer live. After `run/cleanup` fires, assert that every `RunTaskExecution.sandbox_id` for the run is terminated.

---

### I. A completed run with evaluators configured may have zero `RunTaskEvaluation` rows with no published signal

**Assumed:** If evaluation criteria are configured for a run, a completed run will always have a corresponding `RunTaskEvaluation` row per task per evaluator. If evaluation fails or is skipped, something is published to make this observable.

**Reality:** If `check_evaluators` fires but dispatches no `task/evaluate` events (due to the `criterion/evaluate` orphan, a registry miss, or any silent failure in the dispatch path), the run reaches `RunRecord.status == COMPLETED` with zero `RunTaskEvaluation` rows. No event is emitted, no error is logged at run level, and the training loop receives a completed run with no scores. The absence of evaluation is indistinguishable from a run where evaluation genuinely returned a zero score.

**Fix:** At `workflow/completed` time (or in `check_evaluators`), assert that the number of `RunTaskEvaluation` rows matches the expected count derived from the experiment definition (tasks × evaluator bindings). If the count is wrong, emit a distinct event or set a flag on `RunRecord` indicating evaluation was incomplete. Do not allow `RunRecord.status == COMPLETED` to coexist with missing evaluations silently.

**Integration test assertion:** For any run where the experiment definition includes at least one evaluator binding, assert after terminal state that `COUNT(RunTaskEvaluation WHERE run_id = X) == expected_evaluation_count`. Assert that `RunRecord.summary_json` contains a non-null, non-empty scores field. A run that completes with zero evaluations must either have no evaluators configured or must have an explicit `evaluation_skipped` marker — never silent absence.

---

### J. When a parent task fails, non-terminal containment children must become FAILED, not CANCELLED, recursively through all sublayers

**Assumed:** When a parent task fails, its non-terminal containment children (all nodes reachable via `parent_node_id`, recursively) are marked `CANCELLED`.

**Correct semantics (per domain model):** `CANCELLED` means "stopped intentionally before it got a chance to run" — an operator decision or a deliberate dependency invalidation. When a parent's execution context collapses (the container breaks, the worker raises), children whose work is now unreachable are not cancelled — they failed because their execution environment no longer exists. The correct status is `FAILED` with cause `parent_failed`.

This distinction matters for operators: `CANCELLED` subtasks are treated as expected cleanup and get little scrutiny. `FAILED` subtasks surface in failure dashboards and signal "the scope of this failure was N nodes deep."

**Scope:** Only non-terminal nodes are affected. Already-`COMPLETED` nodes represent genuinely finished work and must not be overwritten. Already-`FAILED` or `CANCELLED` nodes are left as-is.

**Guard:** A node with `parent_node_id != NULL` should not be individually restartable — it can only be reset as part of a parent restart. Enforcing this prevents operators from retrying individual subtasks before their parent context is restored.

**Reality (current code):** The current cascade code marks containment children `CANCELLED` with cause `parent_terminal`. This is the wrong status and the wrong cause string.

**Fix:** Change the containment cascade to emit `FAILED` with cause `parent_failed`. Separate this from the existing `dep_invalidated` cascade (which operates on `RunGraphEdge` and correctly uses `CANCELLED`).

**Integration test assertion:** See test 7 above. Assert that after a parent fails, every non-terminal containment descendant has status `FAILED` and no node in the subtree has status `CANCELLED` as a result of the parent's failure.

---

### K. `restart_task` must reset the full containment subtree recursively, including COMPLETED children

**Assumed:** Restarting a task only resets the task itself and invalidates its DAG-level dependency successors.

**Correct semantics (per domain model):** A restart is a full reset of the node's entire containment subtree — every node reachable via `parent_node_id` recursively, including `COMPLETED` ones. The new execution starts in a fresh container; outputs from prior-attempt subtasks were written into the old container's context and cannot be assumed valid. Preserving COMPLETED subtask children from a prior run creates a mixed-generation problem where some outputs are from attempt N and some from attempt N+1.

The restart should:
1. Reset every containment descendant to `PENDING` regardless of its current status
2. Dispatch `task/ready` for the subtree roots only (nodes with no in-edges within the subtask group)
3. Let normal propagation drive the rest as roots complete
4. Recurse: grandchildren and deeper sublayers reset alongside direct children

**Reality (current code):** `_invalidate_downstream` in `task_management_service.py` traverses outgoing `RunGraphEdge` only (the dependency DAG). It does not traverse the containment tree (`parent_node_id`). Children from prior executions are left in their old states entirely — see issue F above.

**Fix:** Add a containment-subtree reset pass to `restart_task` that runs before re-dispatching `task/ready`. Walk all nodes with `parent_node_id == node_id` recursively, reset each to `PENDING`, and dispatch `task/ready` for roots. This is distinct from and in addition to `_invalidate_downstream` (which handles DAG-level successors separately).

**Integration test assertion:** See test 8 above. After `restart_task`, assert no `RunGraphNode` with `parent_node_id == restarted_node.id` (or deeper) retains `COMPLETED` or `FAILED` from the prior run.

**Design clarification — `plan_subtasks` on a restarted execution:** Resetting prior children to `PENDING` (rather than `CANCELLED`) creates a conflict: the new parent execution will call `plan_subtasks` again, producing a second generation of child nodes alongside the reset first generation. The correct design is to **cancel** all prior containment children as part of `restart_task` (not reset to `PENDING`), then let the new execution call `plan_subtasks` fresh to create new nodes. This is cleaner: the worker's new decomposition may differ from the prior attempt's (especially after `refine_task`), and reusing old node rows assumes the plan is identical across attempts. The full-reset described above applies to the containment subtree reset at restart time; `plan_subtasks` in the new execution then builds the next generation from scratch.

---

### L. `RunGraphMutation` has no causal lineage field — cascades are undebuggable

**Assumed:** The WAL records enough information to reconstruct *why* any given state transition happened, including which upstream event triggered it.

**Reality:** `RunGraphMutation` records `actor` and `reason` for each individual mutation, but has no pointer to the mutation that caused it. A cascade that sets 15 nodes to `FAILED` produces 15 independent WAL entries with the same `reason="parent_failed"` string. There is no way to query "what single event caused all of these?" or "what triggered this specific restart?" The WAL shows *what* happened but not *why* in a traceable, machine-queryable form.

**Proposed fix — self-referential `triggered_by_mutation_id`:**

Add `triggered_by_mutation_id: UUID | None` to `RunGraphMutation`. Root-level mutations (operator actions, external events) have `NULL`. Every mutation produced by a cascade points to the mutation that triggered it. The result is a causal tree:

```
mutation 1: node A → FAILED           triggered_by=NULL   reason="worker_error"
mutation 2: node B → FAILED           triggered_by=1      reason="parent_failed"
mutation 3: node C → FAILED           triggered_by=1      reason="parent_failed"
mutation 4: node D → FAILED           triggered_by=2      reason="parent_failed"  ← grandchild
mutation 5: node A → PENDING          triggered_by=NULL   reason="operator_restart"
mutation 6: node B → PENDING          triggered_by=5      reason="parent_restart"
mutation 7: node C → PENDING          triggered_by=5      reason="parent_restart"
mutation 8: node D → PENDING          triggered_by=6      reason="parent_restart"
```

This enables:
- **Root cause query:** "Why is node D FAILED?" → mutation 4 → triggered by 2 → triggered by 1 → worker error on A.
- **Blast radius query:** "What did restarting A cause?" → all mutations with `triggered_by` in the transitive closure of mutation 5.
- **Orphan detection:** Any cascade mutation with `triggered_by=NULL` is a bug — something set a node's status without a traceable cause.

**Integration test assertion (cross-cutting invariant):** Add to the shared assertion helpers: for any run, every `RunGraphMutation` whose `reason` is in `{parent_failed, parent_restart, dep_invalidated, downstream_invalidation}` must have a non-null `triggered_by_mutation_id`. A cascade mutation with no `triggered_by` is a test failure.

---

### H. Failed-attempt sandbox is not killed before the restart container starts; prior container leaks

**Assumed:** When a task is restarted, its failed attempt's sandbox is cleaned up before the new attempt begins.

**Reality:** Every `task/ready` event goes through `sandbox-setup` (confirmed in `execute_task.py:140`), which provisions a fresh container. But when a task fails, `TaskFailedEvent` carries the sandbox_id and nothing kills that container at that point — teardown only happens at `run/cleanup`, which fires at run end. So between `restart_task` firing and the run eventually ending, two live containers exist for the same task simultaneously: the one from the failed attempt and the one from the current attempt.

This compounds issue A: `run/cleanup` kills whichever sandbox_id was last written to `RunRecord.summary_json`, so the prior-attempt container leaks permanently.

**Fix:** When `task/failed` fires (or when `restart_task` is called), kill the failed execution's sandbox immediately rather than waiting for run-level cleanup. The `execution_id` is available in both events and uniquely identifies which sandbox to terminate.

**Integration test assertion:** After `restart_task` is called on a failed node, assert that the sandbox_id from the failed `RunTaskExecution` is no longer live. Assert that only one sandbox (from the new attempt) is live while the restart is in progress.

---

### I. A completed run with evaluators configured may have zero `RunTaskEvaluation` rows with no published signal

**Assumed:** If evaluation criteria are configured for a run, a completed run will always have a corresponding `RunTaskEvaluation` row per task per evaluator. If evaluation fails or is skipped, something is published to make this observable.

**Reality:** If `check_evaluators` fires but dispatches no `task/evaluate` events (due to the `criterion/evaluate` orphan, a registry miss, or any silent failure in the dispatch path), the run reaches `RunRecord.status == COMPLETED` with zero `RunTaskEvaluation` rows. No event is emitted, no error is logged at run level, and the training loop receives a completed run with no scores. The absence of evaluation is indistinguishable from a run where evaluation genuinely returned a zero score.

**Fix:** At `workflow/completed` time (or in `check_evaluators`), assert that the number of `RunTaskEvaluation` rows matches the expected count derived from the experiment definition (tasks × evaluator bindings). If the count is wrong, emit a distinct event or set a flag on `RunRecord` indicating evaluation was incomplete. Do not allow `RunRecord.status == COMPLETED` to coexist with missing evaluations silently.

**Integration test assertion:** For any run where the experiment definition includes at least one evaluator binding, assert after terminal state that `COUNT(RunTaskEvaluation WHERE run_id = X) == expected_evaluation_count`. Assert that `RunRecord.summary_json` contains a non-null, non-empty scores field. A run that completes with zero evaluations must either have no evaluators configured or must have an explicit `evaluation_skipped` marker — never silent absence.
