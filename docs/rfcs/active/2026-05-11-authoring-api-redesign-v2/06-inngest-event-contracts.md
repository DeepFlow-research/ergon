# 06 — Inngest event contracts

> The complete event taxonomy for v2: every event the runtime fires,
> what payload it carries, who produces it, who consumes it, how
> fan-out works, and what idempotency / retry semantics apply.
>
> Supersedes v1's [`05-migration.md` §14.B "Inngest payloads"](../2026-05-08-authoring-api-redesign/05-migration.md).
> The headline difference: **one Inngest function per task, not two**.
> See [`03-runtime.md`](03-runtime.md) "Synchronous fanout" for why.
>
> See [`04-walkthrough.md`](04-walkthrough.md) for the trace of these
> events firing in order, and
> [`02-persistence-layer.md`](02-persistence-layer.md) for the row
> writes each event triggers.

## The job graph

```
                              ┌──────────────────┐
   API: launch_run() ───►     │  workflow/started │
                              └────────┬──────────┘
                                       │
                                       │ on receive: prepare_run service
                                       │   (1) copy definition→run rows
                                       │   (2) for each ready task, fire task/ready
                                       ▼
                              ┌──────────────────┐
                              │   task/ready     │  (one per ready task)
                              └────────┬──────────┘
                                       │
                                       │ on receive: dispatcher
                                       │   fires task/worker-execute
                                       ▼
                              ┌──────────────────────┐
                              │ task/worker-execute  │  (the work)
                              └────────┬──────────────┘
                                       │
                  ┌────────────success──┴──failure──┐
                  ▼                                 ▼
          ┌──────────────────┐            ┌──────────────────┐
          │ task/completed   │            │  task/failed     │
          └────────┬──────────┘            └────────┬──────────┘
                   │                                 │
                   │  on receive (both):             │
                   │   advance_run service           │
                   │   - mark this task terminal     │
                   │   - mark dependents ready ──────┘
                   │   - if no more pending, fire workflow/completed
                   ▼
          ┌──────────────────┐
          │  task/ready      │  (fan-out for newly-ready tasks)
          └──────────────────┘

                              ┌──────────────────┐
        run reaches terminal  │ workflow/         │
        state ───►            │   completed       │
                              └────────┬──────────┘
                                       │
                                       │ on receive: run/cleanup (best-effort)
                                       ▼
                              ┌──────────────────┐
                              │  run/cleanup     │  (sandbox sweep)
                              └──────────────────┘
```

## Events

For every event below: producer, consumer, payload, idempotency key,
retry policy.

### `workflow/started`

| Property | Value |
|---|---|
| **Producer** | `launch_run(definition_id, *, metadata)` — public API |
| **Consumer** | `prepare_run` Inngest function |
| **Idempotency key** | `run_id` (assigned by `launch_run` before dispatch; same key on retry) |
| **Retries** | up to 3 with exponential backoff |
| **Side effects on consume** | (1) copy `experiment_definition_tasks` → `run_graph_nodes` for this `run_id`; (2) copy `experiment_definition_edges` → `run_graph_edges`; (3) mark `runs.status = RUNNING`; (4) for each task with no incoming edges, fire `task/ready` |

```python
class WorkflowStartedPayload(BaseModel):
    run_id: UUID
    definition_id: UUID
    metadata: Mapping[str, Any]
```

`prepare_run` is the only place definition-tier tables are read by the
runtime path (per [`02-persistence-layer.md` §4 read
boundary](02-persistence-layer.md)). After `prepare_run` returns, no
subsequent Inngest function reads from definition tables.

### `task/ready`

| Property | Value |
|---|---|
| **Producer** | `prepare_run` (initial fan-out); `advance_run` (dependency-driven fan-out after a task completes) |
| **Consumer** | `dispatch_task` Inngest function |
| **Idempotency key** | `(run_id, task_id, generation)` where `generation` increments on restart_task |
| **Retries** | up to 3 |
| **Side effects on consume** | fire `task/worker-execute` with the same `(run_id, task_id, execution_id)` |

```python
class TaskReadyPayload(BaseModel):
    run_id: UUID
    task_id: UUID
    execution_id: UUID                        # fresh UUID per attempt
    generation: int = 0                       # incremented by restart_task
```

The reason this is a separate event from `task/worker-execute`: it's the
fan-out point. `prepare_run` and `advance_run` both fire `task/ready`
events; the dispatcher consumes them and fires the actual work events.
Decoupling means restart-task / requeue logic only has to fire
`task/ready`, not understand the worker-execute payload shape.

### `task/worker-execute`

The orchestrator event. Reshapes v1's pair: `worker_execute` is still
one Inngest function per task, but it now **synchronously invokes**
`evaluate_task_run` once per evaluator via `ctx.step.invoke`. Eval
runs as a separate Inngest function (own retry, own concurrency cap,
own observability slug); the parent `gather`s on every invocation
before releasing the sandbox.

| Property | Value |
|---|---|
| **Producer** | `dispatch_task` (in response to `task/ready`) |
| **Consumer** | `worker_execute` Inngest function |
| **Idempotency key** | `(run_id, task_id, execution_id)` |
| **Retries** | up to N (configurable per task; default 1 — workers are expensive) |
| **Side effects on consume** | (1) acquire sandbox via `SandboxLifecycleHub` and stamp `sandbox_id` onto `run_task_executions`; (2) run `worker.execute()`; (3) persist `worker_output` to `run_graph_nodes`; (4) `asyncio.gather(*[ctx.step.invoke(evaluate_task_run, …) for each evaluator])` — sandbox stays alive through gather; (5) release sandbox in `finally` after gather returns; (6) fire `task/completed` or `task/failed` |

```python
class TaskWorkerExecutePayload(BaseModel):
    run_id: UUID
    task_id: UUID
    execution_id: UUID
    definition_id: UUID                       # for WorkerContext convenience
```

The function body is the canonical sequence in
[`03-runtime.md` "Synchronous fanout"](03-runtime.md). Concretely:

```python
@inngest_function(event="task/worker-execute", retries=N, concurrency=...)
async def worker_execute(ctx, event: TaskWorkerExecutePayload) -> None:
    node = await graph_repo.node(session, run_id=event.run_id, task_id=event.task_id)
    task = node.task

    sandbox = await lifecycle_hub.acquire(
        task.sandbox, run_id=event.run_id, task_id=event.task_id,
    )
    # Stamp sandbox_id onto the execution row so eval workers can attach.
    await task_execution_repo.set_sandbox_id(
        execution_id=event.execution_id, sandbox_id=sandbox.sandbox_id,
    )
    try:
        worker_ctx = WorkerContext._for_job(
            run_id=event.run_id, task_id=event.task_id,
            execution_id=event.execution_id,
            definition_id=event.definition_id,
            task_mgmt=..., task_inspect=..., resource_repo=...,
        )
        final_output: WorkerOutput | None = None
        async for chunk in task.worker.execute(task, context=worker_ctx):
            if isinstance(chunk, WorkerOutput):
                final_output = chunk
            await graph_repo.persist_stream_chunk(
                run_id=event.run_id, task_id=event.task_id,
                execution_id=event.execution_id, chunk=chunk,
            )
        await graph_repo.persist_worker_output(
            run_id=event.run_id, task_id=event.task_id,
            execution_id=event.execution_id, output=final_output,
        )

        # Synchronous fanout: each ctx.step.invoke suspends the parent
        # until that eval invocation returns. asyncio.gather lets all
        # evals run in parallel against the same live external sandbox.
        # The sandbox stays alive through gather because the parent is
        # still in its try block.
        await asyncio.gather(*[
            ctx.step.invoke(
                f"eval-{i}",
                evaluate_task_run,
                TaskEvaluateRequest(
                    run_id=event.run_id,
                    task_id=event.task_id,
                    execution_id=event.execution_id,
                    evaluator_index=i,
                ),
            )
            for i in range(len(task.evaluators))
        ])

        await graph_repo.mark_task_succeeded(
            run_id=event.run_id, task_id=event.task_id,
            execution_id=event.execution_id, output=final_output,
        )
        await fire_event("task/completed", TaskCompletedPayload(
            run_id=event.run_id, task_id=event.task_id,
            execution_id=event.execution_id,
        ))
    except Exception as exc:
        await graph_repo.mark_task_failed(
            run_id=event.run_id, task_id=event.task_id,
            execution_id=event.execution_id, error=str(exc),
        )
        await fire_event("task/failed", TaskFailedPayload(
            run_id=event.run_id, task_id=event.task_id,
            execution_id=event.execution_id, error=str(exc),
        ))
        raise            # let Inngest see the failure for retry/observability
    finally:
        # Always reached — sandbox release is bounded by this function's
        # lifetime, never delegated to a sibling job. Eval workers only
        # attach/detach; only the orchestrator terminates.
        await lifecycle_hub.release(sandbox)
```

### `task/evaluate`

Per-evaluator fanout target. Receives a thin id-only payload; reloads
task state via the same `graph_repo.node(...)` the orchestrator used.

| Property | Value |
|---|---|
| **Producer** | `worker_execute` via `ctx.step.invoke` |
| **Consumer** | `evaluate_task_run` Inngest function |
| **Idempotency key** | `(run_id, task_id, execution_id, evaluator_index)` |
| **Retries** | up to 3 (judge LLMs are flaky; per-function retry is the point of keeping the fanout) |
| **Concurrency** | function-level cap (e.g. 50) for global eval throttling independent of `worker_execute` concurrency |
| **Side effects on consume** | (1) load task via `graph_repo.node` with `sandbox_id` from execution row, producing a Task with live `_runtime` attached; (2) pick `task.evaluators[payload.evaluator_index]`; (3) load `worker_output` from `run_graph_nodes`; (4) call `evaluator.evaluate(task, worker_output)`; (5) persist outcome; (6) detach (drop local `_runtime`, never terminate the external sandbox) |

```python
class TaskEvaluateRequest(BaseModel):
    run_id: UUID
    task_id: UUID
    execution_id: UUID
    evaluator_index: int                      # position in task.evaluators
```

Note what is **not** in the payload: `sandbox_id` (read off
`run_task_executions`), `evaluator_type` / `binding_key` (recovered
from `task.evaluators[index]`), `task_payload` (carried in
`task_json`), `worker_output` (loaded from `run_graph_nodes`). The
payload is identifiers only; everything else is a side-channel lookup
against persisted state, which means restart and retry are trivially
correct.

```python
@inngest_function(event="task/evaluate", retries=3, concurrency=50)
async def evaluate_task_run(ctx, event: TaskEvaluateRequest) -> None:
    execution = await task_execution_repo.get(event.execution_id)
    node = await graph_repo.node(
        session,
        run_id=event.run_id,
        task_id=event.task_id,
        sandbox_id=execution.sandbox_id,      # makes task.sandbox live
    )
    task = node.task
    output = await graph_repo.load_worker_output(
        run_id=event.run_id, task_id=event.task_id,
        execution_id=event.execution_id,
    )
    evaluator = task.evaluators[event.evaluator_index]

    try:
        outcome = await evaluator.evaluate(task=task, worker_output=output)
        await graph_repo.persist_evaluation(
            run_id=event.run_id, task_id=event.task_id,
            execution_id=event.execution_id, outcome=outcome,
        )
    finally:
        # Drop the local _runtime handle. The external sandbox keeps
        # running — termination is the orchestrator's job.
        await task.sandbox.detach()
```

### `task/completed`

| Property | Value |
|---|---|
| **Producer** | `worker_execute` (success path) |
| **Consumer** | `advance_run` Inngest function |
| **Idempotency key** | `(run_id, task_id, execution_id)` |
| **Retries** | up to 5 (advance_run is a small DB transaction; tolerant of more retries) |
| **Side effects on consume** | (1) for each downstream task whose deps are now all satisfied, fire `task/ready`; (2) if no pending tasks remain in run, fire `workflow/completed` |

```python
class TaskCompletedPayload(BaseModel):
    run_id: UUID
    task_id: UUID
    execution_id: UUID
```

Note: `worker_output` is **not** in the payload — it's persisted to
`run_graph_nodes` and read from there if a downstream needs it.
Keeping payloads small keeps Inngest replay cheap.

### `task/failed`

| Property | Value |
|---|---|
| **Producer** | `worker_execute` (terminal failure path) |
| **Consumer** | `advance_run` Inngest function |
| **Idempotency key** | `(run_id, task_id, execution_id)` |
| **Retries** | up to 5 |
| **Side effects on consume** | (1) walk the spawn subtree (recursive `parent_task_id` walk) of the failed task; mark every descendant FAILED. (2) leave dependency-dependents (tasks whose `depends_on` includes the failed task) at PENDING — they are never dispatched and never marked. (3) leave non-descendants alone — they continue running. (4) re-evaluate run terminal state (no RUNNING tasks AND no dispatchable PENDING tasks ⇒ fire `workflow/completed`). |

```python
class TaskFailedPayload(BaseModel):
    run_id: UUID
    task_id: UUID
    execution_id: UUID
    error: str                               # truncated to 4KB; full error is in run_graph_nodes.last_error
    failure_class: Literal["worker_error", "criterion_error", "sandbox_error", "timeout", "cancelled"]
```

`failure_class` is a coarse classification that lets `advance_run` log
the right way without re-parsing the error string. It does **not**
gate whether descendants cascade — the cascade is unconditional on
spawn-subtree, never on dependency-dependents.

#### Failure semantics — the four-axis lock `[v2: locked]`

The workshop resolved this explicitly. v2's failure model:

| Axis | Behavior |
|---|---|
| **Spawn-children of failed task** (lifecycle-coupled, via `parent_task_id`) | Cascade FAILED. Recursive walk — grandchildren, great-grandchildren also marked FAILED. Their sandboxes are released by the same `lifecycle_hub.terminate_all_for_run` backstop that handles any orphaned sandbox. |
| **Dependency-dependents of failed task** (data-coupled, via `depends_on`) | Stay **PENDING** indefinitely. Never dispatched, never marked, never cancelled. They show up in the final run snapshot as PENDING — that's the signal "this task was blocked by a failed upstream." |
| **Non-descendants** (independent subtrees) | Continue executing happily. Other parallel tasks finish normally. |
| **`runs.status` final** | `SUCCEEDED` iff every task ended SUCCEEDED. Otherwise `FAILED`. PENDING-stuck tasks at run-end count as "did not succeed" ⇒ run is FAILED. |

Why the spawn/dependency asymmetry: spawn-relationships are
*lifecycle-coupled* — when the parent dies, the child has no reason
to exist (it was created to serve the parent). Dependency-relationships
are *data-coupled* — task B needs A's output but is otherwise
independent; there's no lifecycle reason to mark B failed when A
failed (B never started, has no sandbox, holds no resources).

Marking dependency-dependents as PENDING (rather than CANCELLED or
SKIPPED) preserves a useful operator affordance: an admin can manually
restart the failed upstream and the run will pick up the
dependency-dependents naturally without an explicit "unblock" step.
Marking them CANCELLED would force a manual reset before retry.

**Run termination check** (run by `advance_run` after every task
terminal):

```python
def is_run_terminal(run_id: UUID) -> bool:
    """A run is terminal when no task is RUNNING and no PENDING task
    is dispatchable (every PENDING task has at least one FAILED or
    PENDING dep — i.e. is permanently blocked)."""
    if any_task_running(run_id):
        return False
    for task in pending_tasks(run_id):
        if all_deps_succeeded(task):
            return False                     # this task can still be dispatched
    return True
```

When `is_run_terminal` flips to True, `advance_run` fires
`workflow/completed` with `final_status = SUCCEEDED` if all tasks
SUCCEEDED, else `FAILED`.

### `workflow/completed`

| Property | Value |
|---|---|
| **Producer** | `advance_run` (when all tasks are terminal) |
| **Consumer** | `run_cleanup` Inngest function |
| **Idempotency key** | `run_id` |
| **Retries** | up to 5 |
| **Side effects on consume** | (1) call `lifecycle_hub.terminate_all_for_run(run_id)` as a backstop sweep — should be a no-op in normal cases since each `worker_execute` released its own sandbox; (2) mark `runs.completed_at` |

```python
class WorkflowCompletedPayload(BaseModel):
    run_id: UUID
    final_status: Literal["succeeded", "failed", "cancelled"]
```

### `run/cleanup`

`run/cleanup` is **not a separate event** in v2. v1 had it as a
distinct event with its own handler; the audit found it duplicated
work `worker_execute`'s `finally` block already does. v2 folds the
cleanup logic into `workflow/completed`'s `run_cleanup` consumer.

If a use case for explicit cleanup (re-running a sweep on a stuck
run) emerges, it can be reintroduced as a manual admin-triggered
event. None of the current code paths need it.

## Idempotency in detail

Every event consumer is idempotent on its primary key:

- `prepare_run` keyed on `run_id`: re-firing `workflow/started` for a
  run already in `RUNNING` state is a no-op (no double row writes).
- `dispatch_task` keyed on `(run_id, task_id, execution_id)`:
  re-firing `task/ready` for an already-dispatched execution is a
  no-op.
- `worker_execute` keyed on `(run_id, task_id, execution_id)`:
  re-firing for an already-completed execution is a no-op (status
  guard checks before doing real work).
- `advance_run` keyed on `(run_id, task_id, execution_id)`:
  re-firing `task/completed` for an already-advanced row is a no-op.
- `run_cleanup` keyed on `run_id`: idempotent by construction.

This means at-least-once delivery semantics from Inngest are safe.

## Retries vs. restarts

Two distinct concepts:

| Concept | Trigger | What happens |
|---|---|---|
| **Retry** | Inngest re-fires the same event after a transient failure (network blip, pod kill) | Same `execution_id`. The consumer's idempotency guard either no-ops (work already done) or resumes (work was interrupted). Sandbox is re-acquired (cross-pod) or reattached (same-pod). |
| **Restart** | User or worker calls `restart_task` via `WorkerContext` or admin CLI | Fresh `execution_id`. New row appended to `task_executions`. New `task/ready` event fired. Old execution's outputs are kept for audit but a fresh sandbox is provisioned. |

A retry never produces a new `execution_id`. A restart always does.

## Concurrency & fan-out

`worker_execute` events are processed concurrently up to a
per-Inngest-function concurrency cap. For a benchmark with 4 ready
tasks and a cap of 4, all four `worker_execute` functions run in
parallel. The `SandboxLifecycleHub` lives per-pod; if the four are
sharded across pods, four separate hubs each manage their own
sandboxes. This is fine — sandboxes are keyed by `(run_id, task_id)`
which is unique per event.

For a benchmark with 100 ready tasks and a cap of 8, Inngest queues
the surplus and processes them as workers free up. No code in the
`worker_execute` body manages concurrency; it's all Inngest config.

## Diff vs. v1

| v1 | v2 | Why |
|---|---|---|
| `task/worker-execute` + `task/evaluate` (fire-and-forget; release in `check_evaluators`) | `task/worker-execute` orchestrates + `task/evaluate` via synchronous `ctx.step.invoke` + release in orchestrator's `finally` | Audit's finding was the **lifecycle**, not the topology: fire-and-forget eval lost sandbox ownership. Synchronous fanout fixes that without giving up Inngest-level retry/concurrency/observability for eval. |
| `EvaluateTaskRunRequest` payload (definition-coupled, multi-field) | `TaskEvaluateRequest` (id-only: `run_id, task_id, execution_id, evaluator_index`) | Thin contract; everything else side-channels from persisted state |
| `evaluate_task_run.py` Inngest module (definition-row reader, registry-driven) | `evaluate_task_run.py` reshaped (run-tier reader via `graph_repo.node`, no registry) | Same function name and slug; reshaped body |
| `run/cleanup` as an event | folded into `workflow/completed`'s consumer | Same handler, no need for a separate event |
| `terminate_sandbox_by_id(sandbox_id)` (no-op stub) | (deleted) | `SandboxLifecycleHub.release(sandbox)` is the canonical path; no string-id-keyed termination needed |

## Decisions locked at workshop `[v2: locked]`

- **`task/failed` cascade semantics** — **locked.** Spec'd in full in
  the "Failure semantics — the four-axis lock" subsection of
  `task/failed` above. Spawn-subtree cascades FAILED;
  dependency-dependents stay PENDING; non-descendants continue;
  run.status is `FAILED` if anything didn't succeed. v1's strict
  semantics are preserved with the addition of explicit
  PENDING-blocking for dependency-dependents.
- **`workflow/completed` payload** — **locked: minimal.** Payload
  carries `run_id` and `final_status` only. Consumers needing
  summary data read from `runs` and `run_graph_nodes` directly. One
  source of truth, smaller replays.
- **Retry policy** — **locked: framework-only.** Retry counts live
  on the Inngest function definition. They are not exposed on
  `Task` or `Experiment`. Authors who want different retry behavior
  for different task kinds either (a) accept the framework default,
  or (b) raise the discussion as a follow-up RFC if a real workload
  surfaces the need.
- **Stream-chunk persistence** — **locked: annotation-WAL.**
  `WorkerStreamItem` chunks are persisted as `run_graph_annotations`
  rows. No dedicated `task_execution_stream` table; annotations are
  already "things attached to a node at a moment in time" and chunks
  fit that shape.
