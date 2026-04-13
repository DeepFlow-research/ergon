# Workflow Resumption from Durable State

**Status:** Draft  
**Depends on:** 01_AUDIT.md, 02_INCREMENTAL_PERSISTENCE.md  
**Goal:** Given a failed run where PG has lossless task state + turn buffers (thanks to the Redis → PG flush), resume the workflow from the point of failure rather than restarting from scratch.

---

## 1. The Problem

Today, a failed task means a failed workflow. The `task/failed` event propagates
up to `workflow/failed`, which marks the run as FAILED and triggers cleanup.
The only recovery path is to start a new run from scratch.

With the incremental persistence work (02), PG now has:
- DAG structure and every task's state (which completed, which failed, which never started)
- Lossless turn buffer for the failed task (everything up to the crash)
- Worker type and config for every task (so we can reconstruct workers)

This is everything needed to resume — not retry from scratch, but continue
from the exact point of failure. The question is: what's the mechanism?

---

## 2. What "Resume" Means

There are three levels, from least to most ambitious:

### Level 1: Re-dispatch failed tasks (DAG-aware restart)

The simplest. Look at the run's task states in PG, find every task that's
FAILED or was never started (blocked by a failed dependency), and re-emit
`task/ready` events for them. Completed tasks are not re-run.

This is **not** worker-level resumption — the failed task restarts from scratch
with a fresh sandbox and fresh worker. But the DAG doesn't restart — tasks 1–6
keep their results, only task 7+ re-execute.

**What's needed:**
- A new event: `run/resume`
- A new Inngest function: `resume_workflow_fn` that reads task states from PG
  and re-emits `task/ready` for failed/blocked tasks
- Update `RunRecord.status` from FAILED back to EXECUTING
- Re-create `RunTaskExecution` rows for the tasks being retried

**Complexity:** Low. This is mostly wiring — the propagation layer already knows
how to dispatch ready tasks, we just need to re-enter the DAG mid-flight.

### Level 2: Resume failed workers from turn buffer

The interesting one. Instead of restarting task 7 from scratch, reconstruct the
worker's state from the persisted turn buffer and continue from where it left off.

The worker crashed 10 turns in. PG has those 10 turns (from the Redis flush).
`Worker.from_buffer()` reconstructs a pre-seeded worker instance. The worker's
`execute()` picks up from turn 10 instead of turn 0.

**What's needed (in addition to Level 1):**
- `resume_workflow_fn` detects that the failed task has a turn buffer in PG
- Loads the turns, calls `worker_cls.from_buffer(turns, task, **kwargs)`
- If `from_buffer()` returns a worker (not None), uses that for re-execution
- If `from_buffer()` returns None, falls back to Level 1 (fresh restart)
- The sandbox situation: the original sandbox is dead. Options:
  - (a) Create a fresh sandbox and accept the worker resumes without filesystem state
  - (b) If sandbox outputs were persisted incrementally (future work), restore them
  - (c) Accept that sandbox-dependent workers can't resume, only restart

**Complexity:** Medium. The worker interface is already there (`from_buffer()`).
The gap is the orchestration logic that detects a resumable failure and routes
to the seeded worker instead of a fresh one.

### Level 3: Checkpoint-based mid-turn resumption

The most ambitious. Not just "continue from the last completed turn" but
"continue from the exact token/tool-call where the crash happened." This
would require reconstructing the LLM context window mid-generation, which
most inference backends don't support.

**What's needed:** Inference-level checkpoint restore. Not practical today.

**Recommendation:** Not worth pursuing. Level 2 already recovers all completed
turns; the cost of replaying the in-progress turn (one LLM call) is negligible.

---

## 3. Recommended Design: Levels 1 + 2

### 3.1 New event

```python
class RunResumeEvent(InngestEventContract):
    """Emitted to resume a failed run from its last good state."""

    name: ClassVar[str] = "run/resume"

    run_id: UUID
    definition_id: UUID
    resume_mode: Literal["restart_failed", "resume_from_buffer"]
```

- `restart_failed`: Level 1 — re-dispatch failed tasks fresh
- `resume_from_buffer`: Level 2 — attempt worker resumption from turn buffer,
  fall back to restart if `from_buffer()` returns None

### 3.2 Two responsibilities, cleanly separated

**The orchestrator (`resume_workflow_fn`)** handles:
- Validating the run is resumable
- Classifying tasks (completed/failed/blocked/pending)
- Deciding which failed tasks to resume vs restart
- Picking which execution to resume from (latest failed attempt)
- Re-entering the DAG — emitting `task/ready` events for tasks that need re-execution
- Updating run status

**The worker execution (`execute_task_fn`)** handles:
- Detecting a `resume_from_execution_id` on the incoming event
- Loading turns from the previous execution's buffer
- Calling `worker_cls.from_buffer()` to get a seeded worker
- Falling back to a fresh worker if `from_buffer()` returns None
- Running the rest of execution identically (sandbox, persist, propagate)

The orchestrator doesn't touch workers. The worker execution doesn't touch the DAG.

### 3.3 Orchestrator: `resume_workflow_fn`

```python
@inngest_client.create_function(
    fn_id="workflow-resume",
    trigger=inngest.TriggerEvent(event="run/resume"),
    retries=1,
    output_type=WorkflowResumeResult,
)
async def resume_workflow_fn(ctx: inngest.Context) -> WorkflowResumeResult:
    payload = RunResumeEvent.model_validate(ctx.event.data)

    # 1. Validate resumable
    run, definition = _load_resumable_run(payload.run_id)

    # 2. Classify tasks from PG state
    task_states = _classify_tasks(run, definition)
    #   COMPLETED → skip
    #   FAILED    → re-dispatch (with resume_from_execution_id if mode is resume_from_buffer)
    #   BLOCKED   → will unblock via normal DAG propagation once dependencies complete
    #   PENDING   → never reached, will dispatch via normal propagation

    # 3. Build dispatch list
    dispatch = []
    for task in task_states.failed:
        resume_exec_id = None
        if payload.resume_mode == "resume_from_buffer":
            resume_exec_id = task.latest_failed_execution_id
        dispatch.append((task, resume_exec_id))

    # 4. Update run status, create new RunTaskExecution rows
    _mark_run_resuming(run)
    _create_execution_rows(dispatch)

    # 5. Emit task/ready events — with resume_from_execution_id where applicable
    events = [
        inngest.Event(
            name=TaskReadyEvent.name,
            data=TaskReadyEvent(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=task.id,
                resume_from_execution_id=resume_exec_id,
            ).model_dump(mode="json"),
        )
        for task, resume_exec_id in dispatch
    ]
    await inngest_client.send(events)

    return WorkflowResumeResult(...)
```

The orchestrator emits standard `task/ready` events. The only difference from
a normal dispatch is the optional `resume_from_execution_id` field. No new
event type needed.

### 3.4 Worker execution: resume branch in `execute_task_fn`

```python
async def execute_task_fn(ctx: inngest.Context) -> TaskExecuteResult:
    payload = TaskReadyEvent.model_validate(ctx.event.data)

    # Resume-aware worker construction — small branch, same execution path after
    if payload.resume_from_execution_id is not None:
        worker = _build_resumed_worker(payload)
        # If from_buffer() returned None (worker doesn't support resumption),
        # _build_resumed_worker falls back to a fresh worker — Level 1 behaviour.
    else:
        worker = _build_fresh_worker(payload)

    # ... rest is identical: sandbox setup, execute, flush Redis → PG, propagate
```

```python
def _build_resumed_worker(payload: TaskReadyEvent) -> Worker:
    """Load turn buffer from previous execution, attempt from_buffer()."""
    worker_cls = WORKERS.get(payload.worker_type)

    turns = _load_turns_from_execution(payload.resume_from_execution_id)
    if turns:
        task = _load_benchmark_task(payload)
        resumed = worker_cls.from_buffer(
            turns, task,
            name=payload.worker_binding_key,
            model=payload.model_target,
        )
        if resumed is not None:
            return resumed

    # Fallback: fresh worker (Level 1)
    return worker_cls(name=payload.worker_binding_key, model=payload.model_target)
```

**Why this split matters:**
- The operator chooses "resume" vs "restart" at the run level (via the API/CLI)
- The orchestrator chooses *which execution to resume from* (DAG knowledge)
- The worker execution handles *how* to resume (framework knowledge via `from_buffer()`)
- Each layer only knows what it needs to know

### 3.5 `TaskReadyEvent` change

```python
class TaskReadyEvent(InngestEventContract):
    name: ClassVar[str] = "task/ready"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    resume_from_execution_id: UUID | None = None  # NEW — None for fresh, set for resume
```

No new event type. The standard `task/ready` event gains one optional field.
Normal dispatches leave it as None. Resume dispatches set it to the failed
execution's ID. `execute_task_fn` branches on its presence.

### 3.6 State transitions

```
RunRecord.status:

  PENDING → EXECUTING → COMPLETED     (happy path)
  PENDING → EXECUTING → FAILED        (current failure path)
  FAILED  → RESUMING  → EXECUTING → COMPLETED  (resume path)
  FAILED  → RESUMING  → EXECUTING → FAILED     (resume also fails)
```

New status: `RESUMING` — transient state while `resume_workflow_fn` is
classifying tasks and dispatching. Moves to `EXECUTING` once tasks are dispatched.

```python
class RunStatus(StrEnum):
    PENDING = "pending"
    EXECUTING = "executing"
    RESUMING = "resuming"    # NEW
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

### 3.7 RunTaskExecution handling

When resuming a task, we create a **new** `RunTaskExecution` row with an
incremented `attempt_number` (field already exists on the model — no
migration needed for this). The previous execution's row stays as-is
(status=FAILED, with its turn buffer intact in `RunGenerationTurn`).

This preserves the full history: attempt 1 failed with 10 turns, attempt 2
resumed from those 10 turns and completed with 15 total.

The `RunTaskExecution` for the resumed attempt gets a reference back:

```python
class RunTaskExecution(SQLModel, table=True):
    # ... existing fields ...

    # NEW: links to the execution we resumed from (None for fresh executions)
    resumed_from_execution_id: UUID | None = Field(
        default=None,
        foreign_key="run_task_executions.id",
    )
```

---

## 4. API Surface

### 4.1 HTTP endpoint

```
POST /runs/{run_id}/resume
Body: { "mode": "restart_failed" | "resume_from_buffer" }
```

Validates the run is in FAILED state, emits `RunResumeEvent`, returns 202 Accepted.

### 4.2 CLI command

```
ergon run resume <run_id> [--mode restart_failed|resume_from_buffer]
```

Default mode: `resume_from_buffer` (try Level 2, fall back to Level 1).

---

## 5. What This Means for the Paper

The paper's durability claim becomes concrete and demonstrable:

> *"When a worker fails mid-execution, the system preserves all completed
> work (DAG state, turn buffers, tool outputs) and can resume the workflow
> from the point of failure. On a 10-task DAG where task 7 fails after
> 10 tool calls, resumption re-executes only task 7 (from turn 10, not
> turn 0) and propagates to tasks 8–10. Tasks 1–6 are not re-run."*

The experiment to demonstrate this:
1. Run a multi-task workflow
2. Inject a failure mid-execution (kill the worker after N turns)
3. Show that PG has lossless state (turns 1–N preserved)
4. Resume the run
5. Show that the resumed worker continues from turn N
6. Show total wall-clock time is dominated by the remaining work, not replay

This is the "fault injection → recovery → measure overhead" experiment from
the earlier paper discussion, and it's now mechanically possible.

---

## 6. Implementation Order

### Phase 1: Level 1 — DAG-aware restart (2-3 days)

1. Add `RESUMING` to `RunStatus` enum
2. Add `RunResumeEvent` to event contracts
3. Add `resume_from_execution_id` to `RunTaskExecution`
4. Implement `resume_workflow_fn` (classify tasks, re-dispatch failed ones)
5. Add optional `resume_from_execution_id` field to `TaskReadyEvent`
6. Add `POST /runs/{run_id}/resume` endpoint
7. Tests: fail task 7 → resume → tasks 1-6 skipped, task 7 restarted fresh, 8-10 propagate

### Phase 2: Level 2 — Worker resumption from buffer (2-3 days)

1. Add `_build_resumed_worker()` to `execute_task_fn` (loads turns, calls `from_buffer()`)
2. Implement `ReActWorker.from_buffer()` with `_seed_messages` (already in 02_ plan)
3. Update `resume_workflow_fn` to detect resumable tasks and set `resume_from_execution_id`
4. Tests: fail task 7 at turn 10 → resume → worker continues from turn 10 → completes

### Phase 3: Sandbox pause on failure + resume (1-2 days)

1. In `worker_execute_fn` finally block: if `not success`, call `sandbox.pause()` instead of `sandbox.kill()`
2. Set `on_timeout="pause"` when creating sandboxes (covers SIGKILL case)
3. On resume: `Sandbox.connect(sandbox_id)` before `from_buffer()`; if fails, fall back to Level 1
4. On successful resume completion: `sandbox.kill()` to clean up
5. Tests: worker exception → sandbox paused → resume → full state; sandbox dead → fallback to Level 1

### Phase 4: CLI + observability (1 day)

1. Add `ergon run resume` CLI command
2. Dashboard shows resume status (which tasks were skipped, resumed, restarted)
3. Tracing spans for the resume lifecycle

---

## 7. Interaction with Other Plans

- **02_INCREMENTAL_PERSISTENCE.md**: Required. Without lossless turn buffers in PG,
  Level 2 resumption has nothing to resume from.
- **01_AUDIT.md §4.2 (Graph WAL unification)**: Nice to have. If the graph mutation
  log tracks resume events, you get a complete audit trail of "run failed at sequence N,
  resumed at sequence M, tasks X/Y/Z re-dispatched."
- **Batch state durability (RolloutService)**: The trainer's `poll()` needs to handle
  the case where a run transitions FAILED → RESUMING → EXECUTING → COMPLETED. Currently
  `poll()` treats FAILED as terminal. This needs a small change: if a run is in RESUMING
  or if `resume_from_execution_id` is set on any execution, `poll()` should wait rather
  than returning a failure.

---

## 8. File Map

### ADD

```
ergon_core/ergon_core/core/runtime/inngest/resume_workflow.py
    - resume_workflow_fn: classify tasks, emit task/ready events with resume_from_execution_id
    - _classify_tasks(): read PG, return completed/failed/blocked/pending
    - _create_execution_rows(): new RunTaskExecution rows for re-dispatched tasks

ergon_core/ergon_core/core/runtime/events/infrastructure_events.py
    + RunResumeEvent

ergon_core/ergon_core/core/runtime/services/inngest_function_results.py
    + WorkflowResumeResult

tests/state/test_workflow_resumption.py
    - Level 1: fail task 7 → resume restart → 1-6 skipped, 7 restarted fresh, 8-10 propagate
    - Level 2: fail task 7 at turn 10 → resume from buffer → worker pre-seeded with 10 turns
    - from_buffer() returns None → falls back to Level 1 (fresh restart)
    - resume non-failed run → error

tests/state/test_sandbox_resume.py
    - worker crash → sandbox paused → Sandbox.connect() restores full state
    - sandbox crash → connect fails → falls back to Level 1 (fresh sandbox)
    - turn_complete event has sandbox_id in payload
    - resume from latest turn → correct sandbox_id resolved
```

### MODIFY

```
ergon_core/ergon_core/core/persistence/shared/enums.py
    + RunStatus.RESUMING

ergon_core/ergon_core/core/persistence/telemetry/models.py
    + RunTaskExecution.resumed_from_execution_id: UUID | None

ergon_core/ergon_core/core/runtime/events/task_events.py
    + TaskReadyEvent: add resume_from_execution_id: UUID | None = None

ergon_core/ergon_core/core/runtime/inngest/execute_task.py
    + resume branch: if payload.resume_from_execution_id, _build_resumed_worker()
    + add _build_resumed_worker(): load turns from PG, call from_buffer(), fallback to fresh
    + add _replay_sandbox_state(): load tool events, filter sandbox tools, replay in order

ergon_core/ergon_core/core/providers/sandbox/manager.py
    + add pause_sandbox() / resume_sandbox() methods wrapping E2B pause/connect

ergon_core/ergon_core/core/runtime/inngest_registry.py
    + register resume_workflow_fn in ALL_FUNCTIONS

ergon_core/ergon_core/core/api/app.py (or runs.py)
    + POST /runs/{run_id}/resume endpoint

ergon_core/ergon_core/core/rl/rollout_service.py
    + poll() handles RESUMING status (don't treat as terminal)

migrations/versions/XXXX_workflow_resumption.py
    + resumed_from_execution_id column on run_task_executions
    + (RunStatus.RESUMING is Python-side only, no DDL)
```

---

## 9. Sandbox State on Resume

### 9.1 The problem

Level 2 resumption gives the worker its conversation history (via `from_buffer()`)
but the sandbox may be dead. For benchmarks where the agent writes files, runs
commands, or modifies the environment (gdpeval, code tasks), the conversation
references artifacts that may no longer exist.

There are two distinct failure modes with different recovery properties:

- **Worker crash (our process dies, sandbox still alive on E2B):** The sandbox
  is intact. We just need to reconnect to it.
- **Sandbox crash (E2B container dies):** The sandbox state is gone. The
  conversation history is preserved but the filesystem is not.

### 9.2 Solution: E2B pause on failure only

E2B natively supports `sandbox.pause()` and `Sandbox.connect(sandbox_id)`.
Pause preserves **both filesystem and memory state** — all files, running
processes, loaded variables, environment. Resume takes ~1 second. Pause takes
~4 seconds per GiB of RAM.

**We only pause on failure, never during normal execution.** Paused sandboxes
aren't cleaned up by normal timeout culling — if we paused on every turn,
we'd leak paused sandboxes. The pause happens in the `finally` block of
`worker_execute_fn`, only when the execution failed.

```
Normal execution:
  sandbox created → worker runs → sandbox killed on completion
  (no pausing, no overhead)

On worker crash (Python exception — finally block runs):
  1. finally block detects failure
  2. sandbox.pause()              → ~2-4 seconds, full state saved
  3. flush Redis → PG             → turns persisted with sandbox_id
  4. sandbox stays paused (not killed)

On resume:
  1. Load failed execution → get sandbox_id from RunTaskExecution
  2. Sandbox.connect(sandbox_id)  → ~1 second, full state restored
  3. Worker.from_buffer(turns)    → conversation history restored
  4. execute() continues with matching sandbox + history
  5. On completion (success or failure): sandbox.kill()

On SIGKILL (finally doesn't run):
  Sandbox survives on E2B with on_timeout="pause" → auto-pauses
  after timeout. Resume path tries Sandbox.connect() — works if
  sandbox hasn't been manually killed.
```

**Zero overhead on the happy path.** The sandbox is never paused during
normal execution. The 2-4 second pause cost is paid only on failure, which
is when you're already in a degraded state and 4 seconds is negligible.

The `sandbox_id` is already stored in PG when the sandbox is created
(via `sandbox_setup_fn`). No new storage needed — the resume path looks
up the failed execution's sandbox ID from the existing data.

### 9.3 Sandbox crashes: fall back to Level 1

If the sandbox itself is dead (E2B infra failure, container OOM, etc.),
there's nothing to pause or resume. The sandbox state is gone.

**Recovery:** Fall back to Level 1 (DAG-aware restart). The failed task
re-executes from scratch with a fresh sandbox and fresh worker. The
conversation buffer is preserved in PG for observability/debugging but
can't be used for resumption because the sandbox context it references
no longer exists.

The resume path handles this gracefully:

```python
def _build_resumed_execution(payload):
    """Try Level 2 (sandbox + conversation resume), fall back to Level 1."""
    sandbox_id = _get_sandbox_id_from_execution(payload.resume_from_execution_id)

    # Try to reconnect to the paused sandbox
    sandbox = None
    if sandbox_id:
        try:
            sandbox = Sandbox.connect(sandbox_id)
        except (SandboxNotFoundError, SandboxTimeoutError):
            pass  # Sandbox dead → will fall through to Level 1

    if sandbox is not None:
        # Sandbox alive → try Level 2 (conversation + sandbox resume)
        turns = _load_turns(payload.resume_from_execution_id)
        worker = worker_cls.from_buffer(turns, task, **kwargs)
        if worker is not None:
            return worker, sandbox
        # from_buffer() returned None → can't resume conversation,
        # but sandbox is alive. Kill it, start fresh.
        sandbox.kill()

    # Level 1: fresh sandbox, fresh worker
    return worker_cls(name=..., model=...), _create_fresh_sandbox()
```

### 9.4 Options we considered and rejected

**Option A: Replay tool calls from the stream**

Re-execute sandbox-affecting tool calls (file_write, shell_exec, etc.) in order
against a fresh sandbox to reconstruct filesystem state.

*Why we rejected it:*
- Tool results are not the same as tool side effects. `shell_exec("make build")`
  returns `"Compiled successfully"` but the side effect is a binary file on disk.
  The stream has the return value, not the side effect.
- To truly reconstruct state, you'd need to replay ALL tools in order — including
  expensive ones (API calls, long compilations, GPU operations). A 40-tool execution
  with $0.50/call tools costs $20 to replay.
- Non-determinism: network-dependent commands, timestamps, random seeds. Replayed
  state may diverge from what the agent's conversation history references.
- Classification problem: workers would need to declare which tools are
  "sandbox-affecting" vs "external." This is error-prone and framework-specific.

**Option B: Restore files from stream events**

Instead of replaying tools, extract file contents from `file_write` tool inputs
in the stream and write them directly to a fresh sandbox.

*Why we rejected it:*
- Only covers `file_write`. Doesn't cover files created by shell commands
  (`make build`, `python setup.py`, `pip install`), which is most of the
  interesting sandbox state.
- Shell command side effects are not in the stream at all — the stream has
  the command input and the stdout/stderr result, not the filesystem diff.
- Binary files may be truncated or absent from the stream payload.

**Option C: Periodic sandbox filesystem snapshots to object storage**

Tar the sandbox filesystem periodically, upload to S3/GCS, restore on resume.

*Why we rejected it:*
- Slow: tar + upload of a sandbox filesystem could be 10-30 seconds depending
  on size. Much slower than E2B's native pause (~4 seconds for full memory + fs).
- Incomplete: captures filesystem but not memory state (running processes,
  loaded variables, open connections).
- Infrastructure overhead: need object storage, upload/download plumbing,
  snapshot scheduling.
- E2B's native pause/resume does this better, faster, and more completely.

**Option D: E2B snapshots (one-to-many)**

E2B offers `createSnapshot()` which captures sandbox state and allows spawning
multiple new sandboxes from it. More flexible than pause/resume.

*Why we deferred it (not rejected):*
- Snapshots are slightly more complex than pause/resume (snapshot → new sandbox
  vs pause → reconnect to same sandbox).
- For single-worker-resume, pause/resume is simpler and sufficient.
- Snapshots become useful if we ever need to fork a sandbox (e.g., branching
  proof search, parallel exploration). Worth revisiting for the MAS use case
  but not needed for the initial resumption implementation.

### 9.5 Durability tiers (what the paper can claim)

| Failure mode | Conversation | Sandbox | Recovery | Cost |
|---|---|---|---|---|
| Worker exception (finally runs) | Lossless (Redis → PG) | Lossless (pause in finally) | Level 2: resume conversation + sandbox | ~1s reconnect |
| Worker SIGKILL (finally doesn't run) | Lossless (Redis survives process) | Alive (on_timeout=pause) | Level 2: resume conversation + sandbox | ~1s reconnect |
| Sandbox crash (container dies) | Lossless (Redis → PG) | Lost | Level 1: restart task fresh | Full re-execution of failed task |
| Worker + sandbox both crash | Lossless (Redis → PG) | Lost | Level 1: restart task fresh | Full re-execution of failed task |
| Redis crash | Lost (current execution only) | Alive but orphaned | No recovery for in-flight data | Re-execute from last PG state |

The paper can say: *"Worker failures recover losslessly — conversation state
from the event log, sandbox state via E2B pause/resume. Infrastructure failures
(sandbox crash, Redis crash) preserve all completed work at the DAG level and
restart only affected tasks."*

### 9.6 Sequencing

Sandbox pause on failure is **Phase 3 of 03_WORKFLOW_RESUMPTION**.

- Phase 1 (Level 1 DAG restart) and Phase 2 (Level 2 conversation resumption)
  work without sandbox state — valuable for research/tool-use benchmarks.
- Phase 3 adds `sandbox.pause()` in the failure path only. Zero overhead on
  happy path. For sandbox-heavy benchmarks (gdpeval, code tasks), this closes
  the gap between "conversation resumed but sandbox empty" and "full state
  recovery."

**Implementation:**

1. In `worker_execute_fn` finally block: `sandbox.pause()` instead of
   `sandbox.kill()` when `not success`
2. Set `on_timeout="pause"` on sandbox creation (covers SIGKILL)
3. On resume: `Sandbox.connect(sandbox_id)` → if alive, Level 2; if dead, Level 1
4. On successful resume completion: `sandbox.kill()` to clean up

---

## 10. Open Questions

1. **Multiple failures.** If the resumed task also fails, can you resume again?
   Yes — create another `RunTaskExecution` with `attempt_number=3` and
   `resumed_from_execution_id` pointing to attempt 2. The turn buffer from
   attempt 2 is the new resume point. No limit on attempts (but a configurable
   max would be sensible).

2. **Partial DAG resume.** What if tasks 3 and 7 both failed? The resume
   dispatches both. Task 3's dependents (4, 5, 6) may need re-execution even
   though they completed in the original run, because task 3's output changed.
   This is a DAG invalidation problem. Simplest approach: only re-dispatch
   FAILED tasks and their transitive dependents (tasks that transitively depend
   on a FAILED task get re-dispatched regardless of their original status).
   Tasks with no path to a FAILED task keep their original results.

3. **Paused sandbox cleanup.** Paused sandboxes persist indefinitely on E2B.
   If a failed run is never resumed, the paused sandbox leaks. Need a cleanup
   mechanism: either a TTL-based sweep ("kill paused sandboxes older than X
   hours if the run is still FAILED") or explicit cleanup when the operator
   decides not to resume (the `run/cleanup` event kills the paused sandbox
   instead of a running one).

4. **E2B pause cost at scale.** Need to confirm storage cost for paused sandboxes
   during large-scale RL training. If hundreds of rollouts fail concurrently
   (e.g., model checkpoint is bad), that's hundreds of paused sandboxes.
   Probably fine — E2B docs say indefinite retention — but worth verifying.
