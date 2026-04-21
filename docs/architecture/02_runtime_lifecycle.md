# 02 — Runtime Lifecycle

## 1. Purpose

The runtime layer turns a persisted `ExperimentDefinition` into a durable, observable execution of a DAG of tasks. It owns three jobs: fanning Inngest functions across the run→task→evaluator levels, driving each task through its state machine with every transition recorded as an append-only mutation, and finalizing the run — success, failure, or cancel — while keeping sandboxes and database rows in a consistent terminal state. It does not know about benchmarks, workers, or LLMs; those live at the providers and builtins layers. Its upward contract is narrow: the caller supplies a persisted definition and a run id, and the runtime guarantees the run reaches a terminal status and that history is reconstructable from storage alone.

## 2. Core abstractions

State at this layer is split between mutable graph rows and an immutable audit log. Runtime code treats the log as ground truth; the rows are a cache of the latest `new_value` per target.

### Graph state

- **`RunGraphNode`** — one row per task per run. Carries a free-form `status` string; the runtime only branches on "terminal vs not" (see `status_conventions.TERMINAL_STATUSES`).
- **`RunGraphEdge`** — one row per dependency. Transitions: `pending → satisfied | invalidated`. A dependent advances only when every incoming edge is `satisfied`.
- **`RunGraphMutation`** — append-only log of every node/edge transition. Monotonic `sequence`, `old_value`/`new_value`, `actor`, `reason`. This is the single source of truth for run history.
- **`WorkflowGraphRepository`** — the *only* legal path for mutating node or edge state. Every write takes a `MutationMeta(actor, reason)` and inserts the `RunGraphMutation` row inside the same transaction as the state change.
- **`GraphNodeLookup`** — read-side mediator indexing `definition_task_id → node_id` and `(src, tgt) → edge_id` inside a session.

### Service layer (pure business logic, no Inngest imports)

Each Inngest function is a thin wrapper around one service. The services are unit-testable without an event loop:

- `WorkflowInitializationService` — builds the graph from a definition, marks roots PENDING.
- `TaskExecutionService` — prepares a `RunTaskExecution` row, marks the node RUNNING, and finalizes success or failure.
- `TaskPropagationService` — on terminal, updates outgoing edge status and either activates or cancels downstream candidates (see Section 4).
- `SubtaskCancellationService` — BFS over `parent_node_id` to cancel every non-terminal descendant in one transaction.
- `EvaluatorDispatchService` / `RubricEvaluationService` — fan criteria out per evaluator binding.
- `WorkflowFinalizationService` — aggregates scores, closes the `RunRecord`.
- `TaskCleanupService` — marks a cancelled execution row CANCELLED (idempotent). Sandbox release is still a stub (`task_cleanup_service.py:53-54`).

### Inngest fabric

- **`inngest_client`** (`inngest_client.py:6`) — singleton app. All runtime functions register against it and are collected in `inngest_registry.ALL_FUNCTIONS`.
- **`RUN_CANCEL`** / **`TASK_CANCEL`** matchers (`inngest_client.py:17-32`) — declarative cancel predicates attached to every long-running function decorator. When a `run/cancelled` event arrives, Inngest kills every in-flight function whose trigger payload carries the matching `run_id`.
- **Event contracts** under `runtime/events/` — `WorkflowStartedEvent`, `TaskReadyEvent`, `TaskCompletedEvent`, `TaskFailedEvent`, `TaskCancelledEvent`, `WorkflowCompletedEvent`, `WorkflowFailedEvent`, `RunCancelledEvent`, `RunCleanupEvent`. Each defines its own Inngest event name and Pydantic payload; nothing else is allowed to trigger a transition.

### Freeze status

- `RunGraphNode` / `RunGraphEdge` / `RunGraphMutation` table shapes: **frozen** for existing runs. Schema changes require a migration plan.
- `TaskExecutionStatus`: **frozen** set. Adding a status requires coordinated changes in propagation, cascade cancellation, evaluator gating, and workflow-terminal checks.
- Inngest event payloads: **stable**. Adding optional fields is safe; renaming is a breaking change across the Inngest queue.

## 3. Control flow

```
CLI / API                                     run/cancelled ──────────┐
  │                                                                   │ (kills any
  ▼                                                                   │  in-flight
benchmark-run-start ─► workflow/started                               │  function via
                              │                                       │  RUN_CANCEL
                              ▼                                       │  matcher)
                    workflow-start
                     • builds graph from definition
                     • marks roots PENDING
                              │
                              ▼
                    task/ready (fan-out, one per root)
                              │
                              ▼
                    task-execute  ◄── concurrency=15, retries=0
                     ├─ prepare-execution     (insert RunTaskExecution, RUNNING)
                     ├─ invoke sandbox-setup  (provision via manager)
                     ├─ invoke worker-execute (yield GenerationTurns,
                     │                         persist RunContextEvents)
                     ├─ invoke persist-outputs (download + blob-publish)
                     └─ finalize + emit task/completed  (or task/failed on exc)
                              │
           ┌──────────────────┼──────────────────────┐
           ▼                  ▼                      ▼
   task-propagate     task-check-evaluators     cancel-orphans-on-completed
     • edges→SAT        • one evaluate-task-run    • BFS subtree →
     • deps-sat           per binding               CANCELLED
       node→PENDING     • terminate sandbox          (emits task/cancelled
     • workflow         after last criterion         per transitioned node)
       terminal?                  │
           │                      ▼
           ▼               RunTaskEvaluation row
   workflow/completed
     or workflow/failed
           │
           ▼
   workflow-complete / workflow-failed
     • close RunRecord
     • emit run/cleanup
           │
           ▼
   run-cleanup
     • BaseSandboxManager.terminate_by_sandbox_id
     • reconcile RunRecord.status
```

Three fan-out levels, each owned by a distinct function: `workflow-start` fans out ready tasks, `task-check-evaluators` fans out per-binding evaluator runs, and each evaluator's own criteria are executed as durable steps inside `evaluate-task-run`. The only synchronization point is `is_workflow_complete_v2` / `is_workflow_failed_v2`, which `task-propagate` consults on every terminal to decide whether to emit `workflow/completed` or `workflow/failed`.

Dashboard delivery hangs off state mutation (see `05_dashboard.md`); it is not a gating concern for runtime correctness — if the dashboard is down, runs still finish.

## 4. Invariants

1. **All state writes go through `WorkflowGraphRepository`.** Every node or edge transition is paired with a `RunGraphMutation` row in the same transaction, so the log is a complete replay. Enforced by convention and by the repository refusing a write without `MutationMeta`. Raw `session.add(RunGraphNode(...))` on live state is an anti-pattern (see Section 6).

2. **Terminal statuses are terminal.** `COMPLETED`, `FAILED`, and `CANCELLED` are absorbing. The one deliberate exception is re-activating a `CANCELLED` managed subtask (`parent_node_id is not None`) when its dependencies re-satisfy — see the `is_reactivatable_cancelled` guard in `ergon_core/core/runtime/execution/propagation.py:546-583`. New exceptions must live in that guard, not in an ad-hoc branch.

3. **Side-effectful tasks do not retry.** `task-execute` and `worker-execute` carry `retries=0` because they create sandboxes, call provider APIs, and write execution rows — replaying those would duplicate side effects and desynchronize the mutation log from Inngest's durable position. Orchestration and cleanup functions that are idempotent (`task-propagate`, `workflow-complete`, `cleanup-cancelled-task`) carry modest retries (1 or 3). Retry policy is owned by the decorator, never by inner code; do not wrap a worker call in a retry loop.

4. **Cancellation is event-driven, not write-driven.** A `TaskCancelledEvent` fires three consumers in parallel: `cancel-orphans-on-cancelled` (recurse through children), `cleanup-cancelled-task` (mark the execution row, release resources), and `execute-task` cancellation via the `TASK_CANCEL` matcher (drop any queued or still-running invocation). Writing `CANCELLED` to a node row without emitting the event skips all three and leaves the subtree live.

5. **Run-level cancellation uses a declarative matcher, not a side channel.** `ergon run cancel` (`ergon_cli/commands/run.py:50`, backed by `run_service.cancel_run`) does three things: marks the `RunRecord` CANCELLED, sends `run/cancelled`, sends `run/cleanup`. The `RUN_CANCEL` matcher on every long-running function — keyed on `event.data.run_id == async.data.run_id` — is what actually kills in-flight work; Inngest enforces it, not application code.

6. **Cascade cancellation is one transaction, not an event chain.** `SubtaskCancellationService.cancel_orphans` walks the entire descendant subtree via BFS on `parent_node_id` in a single DB transaction (`subtask_cancellation_service.py:66-111`). A dropped or delayed Inngest event cannot leave a grandchild running under a cancelled parent. The subsequent `task/cancelled` events are for per-node cleanup, not recursion.

7. **Sandbox lifecycle is per-task, teardown happens after evaluators.** `task-execute` provisions a sandbox through the benchmark's manager; the sandbox stays alive through worker execution, output persistence, the evaluator fan-out, and every criterion run. `task-check-evaluators` calls `BaseSandboxManager.terminate_by_sandbox_id` after the last criterion terminates (`check_evaluators.py:82`). `run-cleanup` terminates any residual sandbox recorded on the `RunRecord.summary_json`. See `03_providers.md` §4 for the definitive treatment.

8. **Workflow finalization is replay-safe.** `workflow-complete` and `workflow-failed` re-read the current `RunRecord` and evaluation rows each invocation; repeated delivery writes the same terminal status with the same completion timestamp logic. `run-cleanup` checks the status before overwriting.

### 4.1 Known limits

- **Static-sibling failure auto-cancels today.** When a static task (no `parent_node_id`) fails, `propagation.on_task_completed_or_failed` marks its siblings CANCELLED (`execution/propagation.py:515-526`). The intended fractal-OS semantic is that static siblings stay PENDING so a higher-level manager can adapt — matching managed-subtask behavior. Changing this also requires teaching `is_workflow_complete_v2` to terminate on blocked-by-failed chains, otherwise workflows hang. Tracked in `docs/rfcs/active/2026-04-17-static-sibling-failure-semantics.md`.
- **Cancellation releases the sandbox.** `cleanup_cancelled_task_fn` calls `BaseSandboxManager.terminate_by_sandbox_id` in its `release-sandbox` step when `sandbox_id` is present on the `TaskCancelledEvent`. Tasks that were cancelled before a sandbox was created (dep_invalidated with no execution) emit the event with `sandbox_id=None`; the step is a safe no-op in that case.
- **`RunTaskStateEvent` is deprecated and unread.** Propagation no longer writes to it (`propagation.py:7-8`). `StateEventsQueries` is the last reader and goes away with the table in `docs/rfcs/active/2026-04-17-delete-run-task-state-event.md`. New code must read state from `RunGraphNode` via `GraphNodeLookup`.

## 5. Extension points

- **Adding a new Inngest function.** Define the event payload in `runtime/events/` (subclass `InngestEventContract` with a `ClassVar[str] name`). Write the function in `runtime/inngest/<name>.py` as a thin wrapper around a service in `runtime/services/`. Import it in `inngest_registry.py` and append to `ALL_FUNCTIONS`. Give each function exactly one responsibility — either a single step or an explicitly durable multi-step sequence where every step is idempotent on replay. Attach `cancel=RUN_CANCEL` (or include `TASK_CANCEL` for per-task work) unless the function is explicitly the cleanup leg that must run after a cancel. Pick `retries` by blast radius: 0 for side-effect-bearing, 1 for idempotent orchestration, 3 for best-effort cleanup.

- **Adding a new task status.** Add the value to `TaskExecutionStatus` and the graph `status_conventions`. Update `TERMINAL_STATUSES` if terminal. Teach `on_task_completed_or_failed` the new transition, update `is_workflow_complete_v2` / `is_workflow_failed_v2`, and update the `is_reactivatable_cancelled` guard if the new status should be re-activatable. Every write goes through `WorkflowGraphRepository.update_node_status` with a `MutationMeta`.

- **Dynamic subtask creation.** The graph is eagerly built for static DAGs at `workflow-start`. Beyond that, managers grow the graph through `SubtaskLifecycleToolkit.add_subtask` → `TaskManagementService.add_subtask` → `WorkflowGraphRepository.add_node` / `add_edge` (mutation kind `node.added`, actor `manager-worker`). A `TaskReadyEvent` is emitted and the new node enters the normal `execute-task` flow. The graph is append-only at the row level on this path: no existing node or edge is mutated. This is the sanctioned seam for dynamic creation; managers must not touch the repository or a session directly.

## 6. Anti-patterns

- **Direct DB writes to `RunGraphNode.status`.** Skips the mutation log, breaks audit-replay, and is invisible to the dashboard emitter that listens on the repository. Always go through `WorkflowGraphRepository.update_node_status`.

- **Cancelling by writing `CANCELLED` to a row.** Must emit `TaskCancelledEvent` instead. The three consumers (`cancel-orphans`, `cleanup-cancelled-task`, `TASK_CANCEL` matcher) only fire on the event. A direct write leaves the subtree live and blocks finalization.

- **Importing a provider SDK (E2B, OpenAI, Anthropic) into a runtime function.** Runtime functions see sandboxes through `BaseSandboxManager` and models through `resolve_model_target` — both are providers-layer concerns. A runtime function reaching for `AsyncSandbox(...)` or `AsyncOpenAI(...)` directly couples orchestration to a specific substrate and breaks the substitution boundary described in `03_providers.md`.

- **Internal retry loops inside workers or services.** The `retries=` decorator argument is the only legal knob. Wrapping a provider call in a `for i in range(3):` loop multiplies sandbox cost, blurs the durable replay semantics, and desynchronizes execution-row state from Inngest's view of the function.

- **Branching inside an Inngest function on "should I also do X".** Emit a second event and add a second function instead. Conditional side-effect paths inside one function fight the single-responsibility rule and the retry contract — the replay semantics of each branch diverge.

- **Swallowing exceptions in a function body.** Each function must succeed, fail loudly (so Inngest retries per decorator), or emit a specific terminal event. Swallowing makes Inngest see "succeeded" while the mutation log and downstream events disagree with reality.

- **Using `ergon experiment cancel`.** That CLI does not exist. The entrypoint is `ergon run cancel <run_id>`.

## 7. Follow-ups

Active RFCs touching this layer:

- `docs/rfcs/active/2026-04-17-static-sibling-failure-semantics.md` — stop auto-cancelling static siblings on upstream failure; teach `is_workflow_complete_v2` about blocked-by-failed.
- `docs/rfcs/active/2026-04-17-cleanup-cancelled-task-release-sandbox.md` — land the `release-sandbox` step by extending `TaskCancelledEvent` with `sandbox_id` and `benchmark_slug`.
- `docs/rfcs/active/2026-04-17-delete-run-task-state-event.md` — drop the deprecated `RunTaskStateEvent` table and the last reader in `StateEventsQueries`.
- `docs/rfcs/active/2026-04-17-sandbox-lifetime-covers-criteria.md` — formalize the invariant that sandbox timeout >= task timeout + max criterion timeout, so the evaluator fan-out cannot outlive the sandbox.

## 8. Code map

A brief index of where runtime functions live. The architectural claims above stand without this table; it is onboarding reference material.

| Concern | File |
| --- | --- |
| Entry + init | `runtime/inngest/benchmark_run_start.py`, `runtime/inngest/start_workflow.py` |
| Task orchestration | `runtime/inngest/execute_task.py` |
| Task child steps | `runtime/inngest/sandbox_setup.py`, `runtime/inngest/worker_execute.py`, `runtime/inngest/persist_outputs.py` |
| Propagation | `runtime/inngest/propagate_execution.py` |
| Evaluator fan-out | `runtime/inngest/check_evaluators.py`, `runtime/inngest/evaluate_task_run.py` |
| Cancellation cascade | `runtime/inngest/cancel_orphan_subtasks.py`, `runtime/inngest/cleanup_cancelled_task.py` |
| Finalization | `runtime/inngest/complete_workflow.py`, `runtime/inngest/fail_workflow.py`, `runtime/inngest/run_cleanup.py` |
| Registry | `runtime/inngest_registry.py` |
| Client + cancel matchers | `runtime/inngest_client.py` |
| Event contracts | `runtime/events/task_events.py`, `runtime/events/infrastructure_events.py` |
| State-machine core | `runtime/execution/propagation.py` |
| Services | `runtime/services/` |
