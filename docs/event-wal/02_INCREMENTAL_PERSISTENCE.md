# Tech Plan: Incremental Turn Persistence via Async Generator Workers

**Status:** Draft  
**Depends on:** 01_AUDIT.md §4.1  
**Goal:** No data loss on worker crash. Every completed turn is in PG
before the next one starts. No Redis. No streaming infrastructure.

---

## 1. Architecture

Workers yield `GenerationTurn` objects. The runtime persists each one
to PG as it arrives. That's the whole design.

```
Worker.execute() — async generator
  │
  │  yield GenerationTurn   ←── turn 0 (written to PG immediately)
  │  yield GenerationTurn   ←── turn 1 (written to PG immediately)
  │  yield GenerationTurn   ←── turn 2 (written to PG immediately)
  │  ...                         ↑ crash here = turns 0-2 in PG, turn 3 lost
  │  yield GenerationTurn   ←── turn N
  │  return WorkerOutput    ←── final output text + metadata
  │
  ▼
worker_execute_fn (runtime)
  │
  │  async for turn in worker.execute(...):
  │      write RunGenerationTurn row to PG
  │      emit dashboard event
  │      turn_count += 1
  │
  │  output = worker.get_output()  (or from generator return value)
  │
  ▼
PG: RunGenerationTurn rows (one per yield, wall-clock timestamps)
```

**No Redis.** No TurnSink. No StreamEvent. No AgentEventPayload.
No flush_to_pg(). No materialize_turns(). No stream keys. No TTLs.
No orphan reconciliation.

**One type flows through the system:** `GenerationTurn`. The worker
produces it. The runtime persists it. The extraction pipeline reads it.
No conversion, no post-hoc assembly, no vendor-specific flush logic.

**Workers choose their granularity:**
- Yield per-turn during execution → incremental persistence, live dashboard, stronger crash recovery
- Yield all turns at the end → functionally identical to today, zero migration effort

---

## 2. Worker Interface Changes

### 2.1 execute() becomes an async generator

```python
# ergon_core/api/worker.py

from collections.abc import AsyncGenerator

class Worker(ABC):
    type_slug: ClassVar[str]

    @abstractmethod
    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        """Run the worker's task behavior, yielding turns as they complete.

        Each yielded GenerationTurn is persisted to PG immediately by the
        runtime. Workers that can detect turn boundaries mid-execution
        yield incrementally (one turn per ReAct loop iteration). Workers
        that can't yield all turns at the end in one batch.

        The final output text and metadata are returned via get_output(),
        called by the runtime after the generator exhausts.
        """
        ...

    def __init__(
        self,
        *,
        name: str,
        model: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.metadata: dict[str, Any] = dict(metadata or {})
        self._turn_repo = GenerationTurnRepository()

    def get_output(self, context: WorkerContext) -> WorkerOutput:
        """Build output from persisted turns. Override for custom output.

        Called by the runtime after the async generator is fully consumed.
        Default reads turns from PG via self._turn_repo and returns the
        last turn's response text. Workers that need structured output,
        summaries, or custom logic override this — self._turn_repo is
        available to all subclasses.

        The turns are already in PG (persisted by the runtime on each yield),
        so this is a read — not a computation.
        """
        with get_session() as session:
            turns = self._turn_repo.get_for_execution(session, context.execution_id)
        last_turn = turns[-1] if turns else None
        return WorkerOutput(
            output=last_turn.response_text if last_turn else "",
            success=True,
        )

    @classmethod
    def from_buffer(
        cls,
        turns: list[GenerationTurn],
        task: BenchmarkTask,
        **kwargs,
    ) -> "Self | None":
        """Construct a worker pre-seeded with recovered turn history.

        Returns a new worker instance whose execute() will continue
        from where the previous execution left off, or None if this
        worker type doesn't support resumption.
        """
        return None
```

### 2.2 WorkerOutput replaces WorkerResult

`WorkerResult` is deleted. Turns are yielded by the generator. The non-turn
fields move to `WorkerOutput`:

```python
# ergon_core/api/results.py

class WorkerOutput(BaseModel):
    """Non-turn output from a worker execution.

    Turns are yielded by the async generator. This carries everything else.
    """
    model_config = {"frozen": True}

    output: str
    success: bool = True
    artifacts: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

**Breaking change.** `WorkerResult` is removed. All workers must be migrated
to the async generator pattern in the same commit series. No backward compat
shim — this is a clean cut.

---

## 3. ReActWorker Implementation

### 3.1 Eager yielding (incremental persistence)

```python
# ergon_builtins/workers/baselines/react_worker.py

class ReActWorker(Worker):
    type_slug = "react-v1"

    def __init__(self, *, name, model=None, tools=None,
                 system_prompt=None, max_iterations=10):
        super().__init__(name=name, model=model)
        self.tools = tools or []
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations

    async def execute(self, task, *, context):
        resolved = resolve_model_target(self.model)
        agent = Agent(
            model=resolved.model,
            instructions=self.system_prompt,
            tools=self.tools,
            output_type=_AgentOutput,
        )

        task_prompt = _format_task(task)
        node_count = 0
        prev_message_count = 0

        async with agent.iter(task_prompt, model_settings=model_settings) as run:
            async for _node in run:
                node_count += 1

                current_messages = run.result.new_messages() if run.result else []
                if len(current_messages) > prev_message_count:
                    new_turns = _build_turns(current_messages[prev_message_count:])
                    for turn in new_turns:
                        yield turn  # ← persisted to PG by the runtime
                    prev_message_count = len(current_messages)

                if node_count >= self.max_iterations:
                    break

    def get_output(self, context):
        """Extract structured _AgentOutput from the last turn's raw_response."""
        with get_session() as session:
            turns = self._turn_repo.get_for_execution(session, context.execution_id)
        if not turns:
            return WorkerOutput(output="", success=False)
        last_turn = turns[-1]
        raw = last_turn.raw_response
        # Extract the structured output PydanticAI embedded in the response
        output_text = _extract_agent_output(raw)
        return WorkerOutput(
            output=output_text,
            success=True,
            metadata={"turn_count": len(turns), "model": self.model},
        )

    @classmethod
    def from_buffer(cls, turns, task, **kwargs):
        worker = cls(**kwargs)
        worker._seed_messages = []
        for turn in turns:
            if turn.raw_request:
                worker._seed_messages.append(_reconstruct_request(turn.raw_request))
            worker._seed_messages.append(_reconstruct_response(turn.raw_response))
        return worker
```

No `self._output`. No stashing state during execution. `get_output()` reads
from PG via the repository — the turns are already there because the runtime
persisted each yield. The override just adds PydanticAI-specific extraction
of the structured `_AgentOutput`.

### 3.2 What a lazy worker looks like

A minimal worker that doesn't care about incremental persistence:

```python
class SimpleWorker(Worker):
    type_slug = "simple-v1"

    async def execute(self, task, *, context):
        response = await call_llm(task.description)
        yield GenerationTurn(raw_response=response, tool_results=[])

    # get_output() — uses the base implementation (last turn's response_text)
    # No override needed.
```

No framework knowledge needed. No hooks. No sinks. No stashing state.
Just yield a `GenerationTurn` when you have one. The base `get_output()`
reads the last turn from PG and returns its response text.

---

## 4. Runtime Integration (worker_execute_fn)

```python
# ergon_core/core/runtime/inngest/worker_execute.py

async def worker_execute_fn(ctx: inngest.Context) -> WorkerExecuteResult:
    payload = WorkerExecuteRequest.model_validate(ctx.event.data)

    worker_cls = WORKERS.get(payload.worker_type)
    worker = worker_cls(name=payload.worker_binding_key, model=payload.model_target)

    task = BenchmarkTask(
        task_key=payload.task_key,
        instance_key=str(payload.execution_id),
        description=payload.task_description,
    )
    context = WorkerContext(
        run_id=payload.run_id,
        task_id=payload.task_id,
        execution_id=payload.execution_id,
        sandbox_id=payload.sandbox_id,
    )

    turn_count = 0
    try:
        async for turn in worker.execute(task, context=context):
            _persist_turn(
                run_id=payload.run_id,
                execution_id=payload.execution_id,
                worker_binding_key=payload.worker_binding_key,
                turn=turn,
                turn_index=turn_count,
                execution_outcome="success",
            )
            turn_count += 1

        output = worker.get_output(context)

    except Exception as exc:
        # Turns already in PG (each yield was persisted).
        # Mark any already-written turns as from a failed execution.
        _mark_turns_as_failed(payload.execution_id)
        raise

    return WorkerExecuteResult(success=output.success, output_text=output.output)
```

**On crash:** The `except` block fires. Turns 0 through N-1 (everything
yielded before the crash) are already in PG with wall-clock timestamps.
Only the in-flight turn (the one that would have been yielded next) is lost.
`_mark_turns_as_failed()` updates the `execution_outcome` column on the
already-persisted turns so downstream consumers know this was a partial execution.

**No finally block.** No flush. No cleanup. Each yield is its own PG write.
There's nothing to flush because there's no buffer.

---

## 5. _persist_turn() — One PG Write Per Turn

```python
def _persist_turn(
    *,
    run_id: UUID,
    execution_id: UUID,
    worker_binding_key: str,
    turn: GenerationTurn,
    turn_index: int,
    execution_outcome: ExecutionOutcome = "success",
) -> None:
    with get_session() as session:
        session.add(RunGenerationTurn(
            id=new_id(),
            run_id=run_id,
            task_execution_id=execution_id,
            worker_binding_key=worker_binding_key,
            turn_index=turn_index,
            raw_request=turn.raw_request or {},
            raw_response=turn.raw_response,
            response_text=extract_text(turn.raw_response),
            tool_calls_json=extract_tool_calls(turn.raw_response),
            tool_results_json=turn.tool_results or None,
            logprobs_json=(
                [lp.model_dump() for lp in turn.logprobs]
                if turn.logprobs else None
            ),
            policy_version=turn.policy_version,
            execution_outcome=execution_outcome,
            created_at=utcnow(),  # wall-clock time of this turn
        ))
        session.commit()
```

One write, one commit, per turn. ~5-10ms overhead per turn. For a 10-turn
execution, 50-100ms total. Negligible compared to LLM inference latency.

`created_at` is set at persist time, which IS the wall-clock time the turn
completed (because we persist immediately after yield). No separate
`started_at` / `completed_at` needed — `created_at` on consecutive turns
gives you the inter-turn duration.

---

## 6. PG Schema Changes

### 6.1 RunGenerationTurn additions

```python
class RunGenerationTurn(SQLModel, table=True):
    # ... existing fields ...

    # NEW: execution outcome at time of persist
    execution_outcome: ExecutionOutcome | None = Field(
        default=None, index=True,
    )
    # "success" = persisted during successful execution
    # "failure" = execution failed (set retroactively by _mark_turns_as_failed)
    # None = legacy rows from before this feature
```

Note: `started_at` / `completed_at` removed from the plan. `created_at`
(already exists on the model) now carries real wall-clock time because
each turn is persisted immediately. Inter-turn duration = `created_at[N+1] - created_at[N]`.

### 6.2 raw_request population

Fix in `_persist_turn()` (above): `raw_request=turn.raw_request or {}`.
The `GenerationTurn.raw_request` field already exists and the `ReActWorker`
already populates it. The bug was in `GenerationTurnRepository.persist_turns()`
which hardcoded `raw_request={}`. With `_persist_turn()` replacing that
code path, the fix is automatic.

### 6.3 Type tightening (same migration / PR)

While touching the models, tighten `str` fields to use existing enums and `Literal` types.
No behavioral change — pure type narrowing that catches bugs at write time.

**Use existing enums instead of `str`:**

```python
# RunRecord
status: str  →  status: RunStatus

# RunTaskExecution
status: str  →  status: TaskExecutionStatus

# ExperimentCohort
status: str  →  status: ExperimentCohortStatus

# TrainingSession (needs new enum)
status: str  →  status: TrainingStatus  # "running" | "completed" | "failed"
```

**Introduce `Literal` unions for closed value sets:**

```python
# RunGraphMutation
MutationType = Literal[
    "node.added", "node.removed", "node.status_changed", "node.field_changed",
    "edge.added", "edge.removed", "edge.status_changed",
    "annotation.set", "annotation.deleted",
]
mutation_type: str  →  mutation_type: MutationType

# RunGraphMutation + RunGraphAnnotation
GraphTargetType = Literal["node", "edge"]
target_type: str  →  target_type: GraphTargetType

# RunGenerationTurn (new field from §6.1)
ExecutionOutcome = Literal["success", "failure"]
execution_outcome: str | None  →  execution_outcome: ExecutionOutcome | None

# WorkflowCompleteResult / WorkflowFailedResult
status: str = "completed"  →  status: Literal["completed"] = "completed"
status: str = "failed"     →  status: Literal["failed"] = "failed"

# RunResource
kind: str  →  kind: Literal["output"]
```

**Introduce `NewType` aliases for stringly-typed identifiers:**

```python
# ergon_core/core/persistence/shared/types.py

from typing import NewType

WorkerBindingKey = NewType("WorkerBindingKey", str)
BenchmarkSlug = NewType("BenchmarkSlug", str)
```

**Fix nullable fields that shouldn't be:**

```python
# DashboardTaskEvaluationUpdatedEvent
task_id: UUID | None = None  →  task_id: UUID

# DashboardSandboxCommandEvent — add missing run_id
run_id: UUID
```

**Replace empty-string defaults with explicit optionality:**

```python
WorkerExecuteRequest.task_description: str = ""       →  str | None = None
EvaluateTaskRunRequest.evaluator_binding_key: str = "" →  str | None = None
EvaluateTaskRunRequest.agent_reasoning: str = ""       →  str | None = None
EvaluateTaskRunRequest.sandbox_id: str = ""            →  str | None = None
RunCleanupResult.status: str = ""                      →  str | None = None
```

**Tighten bare `list` types on RunGenerationTurn JSON columns:**

```python
tool_calls_json: list | None   →  list[dict[str, object]] | None
tool_results_json: list | None →  list[dict[str, object]] | None
token_ids_json: list | None    →  list[int] | None
logprobs_json: list | None     →  list[dict[str, object]] | None
```

**Type untyped function parameters:**

```python
# GenerationTurnRepository.persist_turns()
turns: list  →  turns: list[GenerationTurn]
```

**Note:** `RunGraphNode.status` and `RunGraphEdge.status` stay as `str` —
the graph layer is intentionally domain-agnostic.

### 6.4 Migration

One Alembic migration:
- Add `execution_outcome` column to `run_generation_turns`
- Column type changes are Python-side only (no DDL)

---

## 7. What We Removed (and Why)

| Removed | Why |
|---|---|
| Redis | No streaming buffer needed. Each turn is written to PG on yield. |
| TurnSink | No buffer to manage. The runtime writes directly to PG. |
| StreamEvent / AgentEventPayload | No stream to parse. Workers yield typed `GenerationTurn` objects. |
| flush_to_pg() | No flush needed. Each yield is its own PG write. |
| materialize_turns() | No post-hoc assembly. Workers produce `GenerationTurn` during execution. |
| RunStreamEvent table | No stream events to persist. Turn-level granularity is sufficient. |
| Orphan key reconciliation | No Redis keys to orphan. |
| TTLs, MAXLEN, stream cleanup | No streams. |
| get_redis(), redis_client.py | No Redis. |
| docker-compose redis service | No Redis. |

**What we kept:**
- `GenerationTurn` — the one type that flows through the system
- `RunGenerationTurn` — the PG table the RL extraction pipeline reads
- `from_buffer()` — worker-specific resumption from recovered turns
- `WorkerContext` — unchanged (no turn_sink field needed)
- The RL extraction pipeline (`extraction.py`) — unchanged, reads `RunGenerationTurn` as before

---

## 8. Failure Matrix

| Failure mode | Turns persisted? | Recovery |
|---|---|---|
| Worker exception (Python crash) | All yielded turns in PG | Turns marked `execution_outcome="failure"`. Resume via 03_ plan. |
| Worker OOM / SIGKILL | All yielded turns in PG | Same — each yield committed individually. Process death doesn't roll back. |
| PG down | No turns persisted | Task fails on first yield. No silent degradation. |

The critical improvement over today: **worker OOM/SIGKILL no longer loses
everything.** Each yielded turn is an independent PG commit. Process death
can't roll them back. The only lost work is the in-flight turn (one LLM call).

---

## 9. Dashboard Events — Repository-Level Notification

### 9.1 Current flow (slow, indirect)

```
worker_execute_fn → _emit_generation_turn_events() → Inngest event
    → Next.js Inngest function → store.update() → Socket.io broadcast
```

Each turn notification bounces through Inngest (HTTP round-trip to Inngest
server, then Inngest calls the Next.js function endpoint). Adds 100-500ms
latency per turn. Dashboard updates are batched post-execution, not live.

### 9.2 New flow (direct, per-turn)

The repository notifies listeners when a turn is persisted. The dashboard
emitter is a listener. No Inngest hop.

```
_persist_turn() → GenerationTurnRepository.persist_single()
    ├── session.add(RunGenerationTurn)
    ├── session.commit()
    └── notify_listeners(turn)   ← fires after commit
            │
            └── DashboardEmitter.generation_turn_completed()
                    │
                    └── Inngest event → Next.js → Socket.io broadcast
```

The Inngest hop from emitter to dashboard still exists (the Python API
and the Next.js dashboard are separate processes — Socket.io lives in
Next.js). But the trigger is now per-turn and immediate, not batched.

### 9.3 Repository change

```python
# ergon_core/core/persistence/telemetry/repositories.py

class GenerationTurnRepository:

    def __init__(self) -> None:
        self._listeners: list[Callable[[RunGenerationTurn], Awaitable[None]]] = []

    def add_listener(self, listener: Callable[[RunGenerationTurn], Awaitable[None]]) -> None:
        self._listeners.append(listener)

    async def persist_single(
        self,
        session: Session,
        *,
        run_id: UUID,
        execution_id: UUID,
        worker_binding_key: str,
        turn: GenerationTurn,
        turn_index: int,
        execution_outcome: ExecutionOutcome = "success",
    ) -> RunGenerationTurn:
        row = RunGenerationTurn(
            id=new_id(),
            run_id=run_id,
            task_execution_id=execution_id,
            worker_binding_key=worker_binding_key,
            turn_index=turn_index,
            raw_request=turn.raw_request or {},
            raw_response=turn.raw_response,
            response_text=extract_text(turn.raw_response),
            tool_calls_json=extract_tool_calls(turn.raw_response),
            tool_results_json=turn.tool_results or None,
            logprobs_json=(
                [lp.model_dump() for lp in turn.logprobs]
                if turn.logprobs else None
            ),
            policy_version=turn.policy_version,
            execution_outcome=execution_outcome,
            created_at=utcnow(),
        )
        session.add(row)
        session.commit()

        for listener in self._listeners:
            try:
                await listener(row)
            except Exception:
                logger.warning("Turn listener failed", exc_info=True)

        return row
```

### 9.4 Wiring

At startup (or in `worker_execute_fn`), register the dashboard emitter
as a listener:

```python
repo = GenerationTurnRepository()
repo.add_listener(dashboard_emitter.on_turn_persisted)
```

The emitter method:

```python
# ergon_core/core/dashboard/emitter.py

class DashboardEmitter:
    async def on_turn_persisted(self, row: RunGenerationTurn) -> None:
        """Called by the repository after a turn is committed to PG."""
        if not self._enabled:
            return
        evt = DashboardGenerationTurnEvent(
            run_id=row.run_id,
            task_execution_id=row.task_execution_id,
            worker_binding_key=row.worker_binding_key,
            worker_name=row.worker_binding_key,
            turn_index=row.turn_index,
            response_text=row.response_text,
            tool_calls=row.tool_calls_json,
            policy_version=row.policy_version,
        )
        await inngest_client.send(
            inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
        )
```

### 9.5 What this replaces

- **Delete** `_emit_generation_turn_events()` in `worker_execute.py` — no longer called
- **Delete** `_emit_generation_turn_events_from_pg()` — never needed
- The `DashboardGenerationTurnEvent` contract and the Next.js Inngest
  function that handles it are unchanged — same event shape, just emitted
  per-turn instead of batched

### 9.6 What `worker_execute_fn` looks like now

```python
async for turn in worker.execute(task, context=context):
    await repo.persist_single(
        session_factory(),
        run_id=payload.run_id,
        execution_id=payload.execution_id,
        worker_binding_key=payload.worker_binding_key,
        turn=turn,
        turn_index=turn_count,
    )
    turn_count += 1
```

One call per turn. The repository handles PG write + dashboard notification.
`worker_execute_fn` doesn't know or care about the dashboard. The emitter
is a listener registered elsewhere.

### 9.7 Future: direct Socket.io (no Inngest hop)

The Inngest hop between the Python emitter and the Next.js Socket.io
server still adds latency. The long-term path is: Python emits directly
to a shared pub/sub (Redis pub/sub, or a WebSocket connection to the
dashboard server) instead of going through Inngest. This eliminates the
last async hop and gives sub-100ms dashboard updates.

This is out of scope for this plan but the listener pattern on the
repository makes it trivial to add later — just register a different
listener that publishes to Redis pub/sub instead of Inngest.

---

## 10. Implementation Order

### Single phase — breaking change (4-5 days)

All workers migrate in one commit series. No backward compat period.

1. Delete `WorkerResult`, add `WorkerOutput` in `results.py`
2. Change `Worker.execute()` return type to `AsyncGenerator[GenerationTurn, None]`
3. Add `get_output()` method to `Worker` ABC
4. Add `from_buffer()` classmethod to `Worker` ABC
5. Migrate all workers: `ReActWorker`, `StubWorker`, `SmokeTestWorker`, `TrainingStubWorker`
6. Implement `_persist_turn()` — one PG write per yielded turn
7. Rewrite `worker_execute_fn`: consume generator, persist per-yield, handle crash
8. Remove `_persist_generation_turns()` (old batch path)
9. Move dashboard events into the turn loop
10. Add `execution_outcome` column to `RunGenerationTurn` + migration
11. Apply type tightening from §6.3
12. Tests

---

## 11. Prompt Fidelity Fix

Depends on raw_request being populated (§6.2 fixes this). Separate small PR
after the main incremental persistence work lands.

In `RolloutService._extract_trajectories()`, replace the hardcoded prompt:

```python
# BEFORE
prompt_text = tokenizer.apply_chat_template(
    [{"role": "user", "content": "Complete the benchmark task."}],
    tokenize=False, add_generation_prompt=True,
)

# AFTER
first_turn = turns_by_run.get(run_id, [None])[0]
if first_turn and first_turn.raw_request:
    prompt_text = _extract_prompt_from_raw_request(first_turn.raw_request, tokenizer)
else:
    prompt_text = tokenizer.apply_chat_template(
        [{"role": "user", "content": "Complete the benchmark task."}],
        tokenize=False, add_generation_prompt=True,
    )
```

---

## 12. PydanticAI Type Mapping Reference

The existing `react_worker.py` (lines 142-179) already implements the
conversion. Reference, don't reinvent.

```
PydanticAI types              →  GenerationTurn fields
─────────────────────────────────────────────────────────
ModelResponse                 →  raw_response (via dataclasses.asdict + _make_json_safe)
ModelRequest (preceding)      →  raw_request (via dataclasses.asdict + _make_json_safe)
ToolReturnPart (from next     →  tool_results (list of {tool_call_id, tool_name, result})
  ModelRequest)
provider_details.logprobs     →  logprobs (list of TokenLogprob)
```

PydanticAI uses dataclasses for message types. The ReActWorker serializes
them with `dataclasses.asdict()` + `_make_json_safe()`. Other agent SDKs
serialize their own types differently — this mapping is PydanticAI-specific
and lives in `ergon_builtins`, not in core.

The inverse (`from_buffer()` reconstruction):

```python
# In ReActWorker — PydanticAI-specific, not in core
def _reconstruct_response(raw: dict) -> ModelResponse:
    return ModelResponse(**raw)

def _reconstruct_request(raw: dict) -> ModelRequest:
    return ModelRequest(**raw)
```

Round-trip through `dataclasses.asdict()` / `**raw` is lossless for
PydanticAI's message types.

---

## 13. Transaction Boundaries

**Rule:** Repository methods **flush but don't commit.** The caller **owns
the commit.** This matches the existing `WorkflowGraphRepository` pattern.

Exception: `GenerationTurnRepository.persist_single()` commits per-turn
because each turn must survive independently (the whole point of
incremental persistence). If the process dies between turns, the committed
ones are in PG.

| Caller | Commits? | Why |
|---|---|---|
| `GenerationTurnRepository.persist_single()` | Yes — per-turn | Each turn must survive process death independently |
| `propagation.on_task_completed()` | Yes — existing | Already commits at end |
| `graph_repo.update_node_status()` | No — flushes | Caller commits |
| `_create_execution_rows()` in resume | No — flushes | `resume_workflow_fn` commits |
| `TaskExecutionService.prepare()` | Yes — existing | Already commits |

---

## 14. File Map

### ADD

```
ergon_core/ergon_core/core/persistence/shared/types.py
    # NewType aliases: WorkerBindingKey, BenchmarkSlug

ergon_core/migrations/versions/XXXX_incremental_persistence.py
    # adds execution_outcome to run_generation_turns

tests/state/test_incremental_persistence.py
    # generator worker yields N turns → N RunGenerationTurn rows in PG
    # worker crash at turn 5 → turns 0-4 in PG, marked as failure
    # lazy worker yields all at end → same result, just batched
    # from_buffer() → pre-seeded worker produces turns continuing from buffer

tests/state/test_type_invariants.py
    # RunRecord.status only accepts RunStatus values
    # RunTaskExecution.status only accepts TaskExecutionStatus values
    # RunGraphMutation.mutation_type only accepts known Literal values
```

### MODIFY

```
# ── Worker interface ──────────────────────────────────────

ergon_core/ergon_core/api/worker.py
    ~ execute() return type: WorkerResult → AsyncGenerator[GenerationTurn, None]
    + __init__: add self._turn_repo = GenerationTurnRepository()
    + get_output(context): base reads from PG via self._turn_repo
    + from_buffer() classmethod (default returns None)

ergon_core/ergon_core/api/results.py
    - delete WorkerResult
    + add WorkerOutput model (output, success, artifacts, metadata — no turns)

ergon_core/ergon_core/api/generation.py
    (no changes — GenerationTurn is already correct)

ergon_core/ergon_core/api/worker_context.py
    (no changes — no turn_sink field needed)

# ── ReAct worker ──────────────────────────────────────────

ergon_builtins/ergon_builtins/workers/baselines/react_worker.py
    ~ execute(): return type → async generator, yield turns during loop
    ~ get_output(context): override to extract PydanticAI structured output
    + from_buffer(): reconstruct PydanticAI message history
    + _seed_messages field for resumption

ergon_builtins/ergon_builtins/workers/baselines/stub_worker.py
    ~ migrate to async generator pattern

ergon_builtins/ergon_builtins/workers/baselines/smoke_test_worker.py
    ~ migrate to async generator pattern

ergon_builtins/ergon_builtins/workers/baselines/training_stub_worker.py
    ~ migrate to async generator pattern

# ── Runtime / Inngest ─────────────────────────────────────

ergon_core/ergon_core/core/runtime/inngest/worker_execute.py
    ~ rewrite: consume async generator, repo.persist_single() per yield
    + _mark_turns_as_failed(): update execution_outcome on crash
    - remove _persist_generation_turns() (old batch path)
    - remove _emit_generation_turn_events() (replaced by repo listener)

ergon_core/ergon_core/core/persistence/telemetry/repositories.py
    + GenerationTurnRepository.persist_single(): single-turn PG write
    + GenerationTurnRepository._listeners: list of post-commit callbacks
    + GenerationTurnRepository.add_listener(): register a callback
    ~ persist_turns(): keep for backward compat (extraction pipeline) or deprecate

ergon_core/ergon_core/core/dashboard/emitter.py
    + DashboardEmitter.on_turn_persisted(): listener method, emits per-turn event

# ── PG models ─────────────────────────────────────────────

ergon_core/ergon_core/core/persistence/telemetry/models.py
    + RunGenerationTurn.execution_outcome: ExecutionOutcome | None
    ~ RunRecord.status: str → RunStatus
    ~ RunTaskExecution.status: str → TaskExecutionStatus
    ~ ExperimentCohort.status: str → ExperimentCohortStatus
    + TrainingSession: needs TrainingStatus enum
    ~ RunGenerationTurn: tighten bare list types on JSON columns

ergon_core/ergon_core/core/persistence/graph/models.py
    ~ RunGraphMutation.mutation_type: str → MutationType
    ~ RunGraphMutation.target_type / RunGraphAnnotation.target_type: str → Literal

ergon_core/ergon_core/core/persistence/shared/enums.py
    + TrainingStatus enum

# ── DTOs / event contracts ────────────────────────────────

ergon_core/ergon_core/core/runtime/services/inngest_function_results.py
    ~ WorkflowCompleteResult.status → Literal["completed"]
    ~ WorkflowFailedResult.status → Literal["failed"]
    ~ RunCleanupResult.status: str = "" → str | None = None

ergon_core/ergon_core/core/runtime/services/child_function_payloads.py
    ~ empty-string defaults → str | None = None

ergon_core/ergon_core/core/runtime/services/graph_dto.py
    ~ mutation_type / target_type tightened

ergon_core/ergon_core/core/dashboard/event_contracts.py
    ~ DashboardTaskEvaluationUpdatedEvent.task_id: not nullable
    + DashboardSandboxCommandEvent: add run_id

# ── Prompt fidelity (separate follow-up PR) ───────────────

ergon_core/ergon_core/core/rl/rollout_service.py
    ~ _extract_trajectories(): use persisted raw_request instead of hardcoded prompt

# ── Infrastructure ────────────────────────────────────────

(no docker-compose changes — no Redis)
(no new dependencies — no redis[hiredis])
```

### DELETE

```
ergon_core/ergon_core/api/results.py → WorkerResult class (replaced by WorkerOutput)
worker_execute.py → _persist_generation_turns() function
worker_execute.py → _emit_generation_turn_events() function
```
