# Violated Assumptions

Each entry below describes a behaviour the production code implements incorrectly relative to the intended domain model. Each has: what was assumed, what the code actually does, the fix required, and the integration test assertion that would catch it. Tests for these are marked `xfail(strict=True)` in the test suite — see `5-test-harness.md` for conventions.

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
