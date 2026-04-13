# Event WAL Audit: Lossless State Reconstruction from Postgres

**Goal:** Given a run where 6 of 10 DAG tasks completed, worker 7 fails 10 tool calls in after 46 seconds — can we rebuild the full DAG and its execution state from PG alone?

**Answer today: no.** The DAG structure and task-level state survive, but the 10 turns of work inside the failed task are lost. Below is the full audit.

---

## 1. Two Parallel State Systems

Ergon currently has two independent DAG state representations that don't share writes.

### System A: Propagation Layer

**Files:** `propagation.py`, `RunTaskStateEvent` model

This is what the Inngest runtime actually uses. `get_current_task_status()` reads the latest `RunTaskStateEvent` row. `on_task_completed()` checks dependent readiness. `is_workflow_complete()` checks terminal state.

**What it captures:**
- Every task status transition (PENDING → RUNNING → COMPLETED/FAILED)
- Old status, new status, execution ID, error metadata
- `created_at` timestamps on each event
- Fully reconstructable: replay events in `created_at` order → exact task state at any point

**What it doesn't capture:**
- Nothing about what happened *inside* a task execution (turns, tool calls, intermediate agent state)
- No connection to the graph layer's mutation log

### System B: Graph Layer

**Files:** `run_graph_*` models, `WorkflowGraphRepository`

The more sophisticated system — append-only mutation WAL with sequence numbers, point-in-time annotation queries (`get_annotation_at`), structural invariant enforcement (acyclicity via Kahn's). The `RunGraphAnnotation` docstring explicitly says it exists for *"counterfactual replay and credit assignment in the training pipeline."*

**Tables:**
- `run_graph_nodes` — mutable task nodes per run, free-form status string
- `run_graph_edges` — mutable dependency edges per run
- `run_graph_annotations` — append-only namespaced metadata WAL (current = latest sequence, point-in-time = sequence ≤ N)
- `run_graph_mutations` — append-only audit log of every change (node.added, node.status_changed, edge.added, annotation.set, etc.) with old_value/new_value diffs and actor attribution

**What it captures:**
- Every structural change to the DAG
- Full old/new value diffs with actor and reason
- Point-in-time reconstruction at any mutation sequence number

**The problem:** The Inngest functions (`execute_task_fn`, `propagate_task_fn`) write to System A (`RunTaskStateEvent` via `propagation.py`) but **never write to System B** (`RunGraphMutation`). The graph repository exists and is well-designed, but the runtime doesn't route execution state through it. Reconstruction from PG requires replaying both systems independently and hoping they agree.

---

## 2. What Survives the Failure Scenario

### Tasks 1–6 (completed): Fully captured ✓

| Table | What's there |
|-------|-------------|
| `run_task_state_events` | PENDING → RUNNING → COMPLETED for each, with timestamps |
| `run_task_executions` | started_at, completed_at, output_text, status=COMPLETED |
| `run_generation_turns` | All turns: raw_request, raw_response, tool_calls, tool_results, logprobs |
| `run_actions` | Each action with started_at, completed_at, action_type, input/output |
| `run_resources` | Sandbox outputs downloaded and registered |
| `run_task_evaluations` | Scores, feedback, pass/fail per evaluator |

### Task 7 (failed mid-execution): Partially captured ⚠️

| Table | What's there |
|-------|-------------|
| `run_task_state_events` | PENDING → RUNNING (written by `prepare` step before worker started) |
| `run_task_executions` | status=RUNNING, started_at set, completed_at=NULL |

Then, after the `except` block fires:

| Table | What's written on failure |
|-------|--------------------------|
| `run_task_executions` | status=FAILED, completed_at=now, error_json={"message": ...} |
| `run_task_state_events` | RUNNING → FAILED with error in metadata |

### Task 7's 10 turns of work: **LOST** ✗

This is the critical gap. In `worker_execute.py`:

```python
result = await worker.execute(task, context=worker_context)    # ← crash here
_persist_generation_turns(payload, result)                      # ← never reached
```

`_persist_generation_turns()` is called **after** `worker.execute()` returns. If the worker crashes at turn 10:
- The `result` object never exists
- `_persist_generation_turns` never runs
- All 10 `RunGenerationTurn` rows that should exist **don't**
- The raw LLM exchanges, tool calls, tool results, logprobs — all gone

The "lossless per-turn records" are only lossless if the worker completes successfully.

### Task 7's sandbox state: **LOST** ✗

`persist_outputs_fn` only runs after worker success (it's `step.invoke`'d sequentially after `worker_execute_fn` returns). Crash = sandbox outputs never downloaded, `RunResource` rows never created.

### Tasks 8–10 (never started): Correctly absent ✓

If they depended on task 7: no `RunTaskStateEvent` rows exist (they were never marked ready). If independent of 7: they have a PENDING event and may have started/completed on their own timeline. The propagation layer handles this correctly.

---

## 3. Additional Gaps

### 3a. Per-Turn Timestamps

`RunGenerationTurn.created_at` is set when the batch is persisted — all turns from a single task execution get roughly the same timestamp. For continuous-time trajectory claims and replay fidelity, each turn needs:
- `started_at`: when the LLM call was dispatched
- `completed_at`: when the response arrived

These already exist on `RunAction` but not on `RunGenerationTurn`. Easy to add, but only meaningful once turns are persisted incrementally (see §4.1).

### 3b. Batch State Is Memory-Only

`RolloutService._batches` is a Python dict in the API process. If the API container restarts mid-training, all `batch_id → run_ids` mappings are lost. The trainer gets 404 and the training step fails. The code comments acknowledge this explicitly:

> *"Acceptable because the API container doesn't restart mid-training; if it does the trainer gets a 404 and the training step fails explicitly."*

### 3c. Thread ↔ Execution Linkage

`ThreadMessage` has `run_id` but no `task_execution_id`. To reconstruct "what messages did agent A send during task 7's execution," you must infer from timestamps. No direct FK path.

### 3d. Generation Turn `raw_request` Is Empty

In `GenerationTurnRepository.persist_turns()`:

```python
raw_request={},     # ← always empty
raw_response=turn.raw_response,
```

The request side of the LLM exchange is never persisted. For lossless reconstruction of what the agent saw before responding, this is a gap — you have the response but not the prompt/context that produced it.

### 3e. Prompt Fidelity in Trajectory Extraction

`RolloutService._extract_trajectories()` hardcodes the prompt:

```python
prompt_text = tokenizer.apply_chat_template(
    [{"role": "user", "content": "Complete the benchmark task."}],
    ...
)
```

This is not the actual prompt the agent saw. For on-policy RL training and for the paper's "lossless trajectory" claim, the prompt should come from the persisted `raw_request` (once that's populated — see §3d).

---

## 4. Recommended Fixes (Priority Order)

### 4.1 Incremental Turn Persistence [Critical]

**Problem:** Generation turns are batch-written post-completion. Crash loses all turns.

**Fix:** Persist each turn to PG as it happens during worker execution. Options:

- **A) Callback/sink pattern:** Pass a `TurnSink` to the worker that writes each `RunGenerationTurn` as it completes. The worker calls `sink.persist(turn)` after each LLM response + tool result cycle.
- **B) WorkerContext method:** Expose `context.persist_turn(turn)` that workers call incrementally. The context holds the session factory and execution IDs.
- **C) Per-turn Inngest steps:** Wrap each turn in its own `ctx.step.run()` for Inngest-level durability. Biggest architectural change but gives per-turn crash recovery semantics.

**Recommendation:** Option B. It's the smallest change to the worker interface, it doesn't require restructuring the Inngest function, and it gives us incremental writes. Option C is worth considering for the full paper but is a larger refactor.

**Side effect:** Once turns are written incrementally, `created_at` on each turn naturally reflects actual wall time, closing gap §3a for free.

### 4.2 Unify State Systems [High]

**Problem:** Propagation layer and graph layer are parallel systems with no shared writes.

**Fix options:**

- **A) Dual-write:** Every `mark_task_running()`, `mark_task_completed()`, `mark_task_failed()` also calls `graph_repo.update_node_status()` in the same transaction. One source of truth, two views. Smallest change.
- **B) Graph-primary:** Drop `RunTaskStateEvent` as the execution state source. Propagation functions query `RunGraphNode.status` directly. The graph mutation log becomes the single WAL. Cleaner, bigger refactor.

**Recommendation:** Option A first (can be done in a day), migrate to Option B when the graph layer is proven in production. The important thing for the paper is that *one* WAL captures everything — the graph mutation log with its sequence numbers and point-in-time queries is the better WAL, so route execution state through it.

### 4.3 Populate `raw_request` [Medium]

**Problem:** `RunGenerationTurn.raw_request` is always `{}`.

**Fix:** In `GenerationTurnRepository.persist_turns()`, change:

```python
raw_request=turn.raw_request if hasattr(turn, 'raw_request') else {},
```

Or better: ensure the `GenerationTurn` API type carries `raw_request` and workers populate it. This gives full round-trip fidelity on the LLM exchange.

### 4.4 Batch State to PG [Medium]

**Problem:** `RolloutService._batches` is memory-only.

**Fix:** Add a `rollout_batches` table:

```
rollout_batches:
  id: UUID (PK)
  definition_id: UUID (FK → experiment_definitions)
  status: str  (PENDING / RUNNING / COMPLETE)
  created_at: datetime

rollout_batch_runs:
  batch_id: UUID (FK → rollout_batches)
  run_id: UUID (FK → runs)
```

On API restart, `poll()` can reconstruct batch state from PG instead of returning 404.

### 4.5 Thread ↔ Execution FK [Low]

**Problem:** Can't directly query messages sent during a specific task execution.

**Fix:** Add optional `task_execution_id: UUID | None` FK to `ThreadMessage`. Workers set it when sending messages during task execution; None for out-of-band messages.

### 4.6 Per-Turn Timestamps [Low — Free with §4.1]

**Problem:** All turns share the same `created_at`.

**Fix:** Add `started_at` / `completed_at` to `RunGenerationTurn`. With incremental persistence (§4.1), `created_at` already reflects real time, but explicit start/end gives duration per turn which matters for the continuous-time trajectory paper claims.

---

## 5. Coverage Tracker

| § | Fix | Priority | Addressed by |
|---|---|---|---|
| 4.1 | Incremental turn persistence | Critical | `02_INCREMENTAL_PERSISTENCE.md` — async generator workers, per-yield PG writes |
| 4.2 | Unify state systems | High | `STATE_UNIFICATION_PLAN.md` — graph WAL as single source |
| 4.3 | Populate `raw_request` | Medium | `02_INCREMENTAL_PERSISTENCE.md` §6.2 + §11 (prompt fidelity fix) |
| 4.4 | Batch state to PG | Medium | Inline spec below — standalone small PR, ~1 day |
| 4.5 | Thread ↔ Execution FK | Low | Inline spec below — single column addition, ~half day |
| 4.6 | Per-turn timestamps | Low | `02_INCREMENTAL_PERSISTENCE.md` — `created_at` on each yield is wall-clock time |
| — | Workflow resumption | — | `03_WORKFLOW_RESUMPTION.md` — DAG-aware restart + worker resume from buffer |
| — | Prompt fidelity | — | `02_INCREMENTAL_PERSISTENCE.md` §11 — use persisted raw_request in extraction |

**§4.4 and §4.5** are small, self-contained fixes. Inline specs below — no separate plan doc.

### Unified implementation order across all docs

```
Phase 1: 02_ INCREMENTAL PERSISTENCE (4-5 days)
  ├── Async generator Worker.execute()
  ├── WorkerOutput replaces WorkerResult (breaking)
  ├── get_output(context) reads from PG via repository
  ├── from_buffer() for worker resumption
  ├── Migrate all workers (ReAct, Stub, SmokeTest, TrainingStub)
  ├── repo.persist_single() with dashboard listener
  ├── PG schema: execution_outcome column
  ├── Type tightening (enums, Literals, NewTypes, nullable fixes)
  └── Tests

Phase 2: 01_ INLINE FIXES (can overlap with Phase 1) (1.5 days)
  ├── §4.4 Batch state to PG
  ├── §4.5 Thread ↔ Execution FK
  └── Tests

Phase 3: STATE_UNIFICATION (can overlap with Phase 2) (3-4 days)
  ├── Dual-write: propagation → graph mutation log
  ├── Read migration: queries use graph layer
  ├── Drop RunTaskStateEvent writes
  └── Tests

Phase 4: 03_ WORKFLOW RESUMPTION (5-7 days)
  ├── Level 1: DAG-aware restart (resume_workflow_fn, RunResumeEvent)
  ├── Level 2: Worker resumption from buffer (from_buffer in execute_task_fn)
  ├── Level 3: Sandbox pause on failure (E2B pause/connect)
  ├── CLI + observability
  └── Tests

Phase 5: PROMPT FIDELITY FIX (0.5 day)
  ├── _extract_trajectories() uses persisted raw_request
  └── Test
```

---

### §4.4 Batch State to PG — Inline Spec

**When:** After 02_INCREMENTAL_PERSISTENCE Phase 1. Before 03_WORKFLOW_RESUMPTION
(resumption needs `poll()` to handle non-terminal states, which is easier if batch
state is already durable).

**Estimated effort:** ~1 day.

**Migration — add two tables:**

```python
class RolloutBatch(SQLModel, table=True):
    __tablename__ = "rollout_batches"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    definition_id: UUID = Field(foreign_key="experiment_definitions.id", index=True)
    status: BatchStatus = Field(default=BatchStatus.PENDING, index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

class RolloutBatchRun(SQLModel, table=True):
    __tablename__ = "rollout_batch_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    batch_id: UUID = Field(foreign_key="rollout_batches.id", index=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
```

**Files to modify:**

```
ergon_core/ergon_core/core/persistence/telemetry/models.py
    + add RolloutBatch and RolloutBatchRun models

ergon_core/ergon_core/core/rl/rollout_service.py
    - remove self._batches: dict[UUID, _BatchState]
    - remove _BatchState class
    + submit(): write RolloutBatch + RolloutBatchRun rows instead of dict insert
    + poll(): query RolloutBatch/RolloutBatchRun instead of dict lookup
    + cancel(): query from PG instead of dict pop

ergon_core/migrations/versions/XXXX_rollout_batch_state.py
    + create rollout_batches and rollout_batch_runs tables
```

**Tests:**

```
tests/state/test_rollout_batch_state.py
    - submit() creates batch + batch_run rows in PG
    - poll() returns correct status from PG
    - cancel() marks runs cancelled via PG query
    - API restart: poll() still finds the batch (no 404)
```

---

### §4.5 Thread ↔ Execution FK — Inline Spec

**When:** Same PR as §4.4 or immediately after. No dependencies.

**Estimated effort:** ~half day.

**Migration — add one column:**

```python
# ThreadMessage — add optional FK
task_execution_id: UUID | None = Field(
    default=None,
    foreign_key="run_task_executions.id",
    index=True,
)
```

**Files to modify:**

```
ergon_core/ergon_core/core/persistence/telemetry/models.py
    + ThreadMessage: add task_execution_id: UUID | None

ergon_core/ergon_core/core/runtime/services/communication_service.py
    + save_message(): accept and persist task_execution_id
    + get_thread_messages(): optionally filter by task_execution_id

ergon_core/ergon_core/core/runtime/services/communication_schemas.py
    + CreateMessageRequest: add task_execution_id: UUID | None = None
    + MessageResponse: add task_execution_id: UUID | None = None

ergon_core/migrations/versions/XXXX_thread_execution_fk.py
    + add task_execution_id column to thread_messages
```

**Tests:**

```
tests/state/test_thread_execution_link.py
    - save message with task_execution_id → persisted correctly
    - query messages by task_execution_id → returns only matching messages
    - save message without task_execution_id → None, backward compatible
```

---

## 6. Reconstruction Test

Once §4.1 and §4.2 are implemented, the following should be possible:

```python
def reconstruct_run_state(session: Session, run_id: UUID, at_time: datetime) -> RunSnapshot:
    """Rebuild the complete DAG execution state at a given wall-clock time."""

    # 1. Graph structure — from mutation log
    mutations = get_mutations_before(session, run_id, at_time)
    graph = replay_mutations(mutations)  # nodes, edges, statuses

    # 2. Per-task execution state — from state events
    task_states = get_state_events_before(session, run_id, at_time)
    # Each task: which status, which execution, when

    # 3. Per-turn agent behavior — from generation turns
    turns = get_turns_before(session, run_id, at_time)
    # Each turn: what the agent saw, what it said, what tools returned, when

    # 4. Inter-agent communication — from thread messages
    messages = get_messages_before(session, run_id, at_time)

    # 5. Evaluations (for completed tasks) — from task evaluations
    evals = get_evaluations_before(session, run_id, at_time)

    return RunSnapshot(graph, task_states, turns, messages, evals)
```

For the failure scenario: at t=46s, this returns tasks 1–6 completed with full turns, task 7 running with 10 turns of partial progress, tasks 8–10 in whatever state the DAG dictates. No data loss.

---

## 7. Implications for the Workshop Paper

The paper claims Ergon is a "durable event-driven substrate" for agentic RL. The current implementation doesn't fully support that claim for the most interesting case (mid-execution failure). Specifically:

- **"Lossless trajectory collection"** — only true if the worker completes. §4.1 makes it true regardless.
- **"Fault-tolerant execution"** — Inngest provides task-level retry/recovery, but sub-task state (the 10 turns) is lost. §4.1 preserves it.
- **"Continuous-time event log"** — the graph mutation WAL has sequence numbers and timestamps, but generation turns (the actual agent behavior) don't have per-turn wall-clock timing. §4.1 + §4.6 close this.
- **"Reconstruct POSG trajectories from the event log"** — requires both the DAG state and the per-agent turns to be in PG and queryable at any point in time. §4.1 + §4.2 make this possible.

The strongest version of the paper can say: *"Every agent action, tool result, LLM exchange, DAG state transition, and inter-agent message is durably persisted to an append-only event log with wall-clock timestamps. The complete execution state of a multi-agent workflow can be reconstructed at any point in time from this log alone, including after arbitrary worker failures."*

That sentence requires §4.1 and §4.2 to be true. §4.3–§4.6 strengthen it but aren't strictly necessary for the core claim.
