# Feature RFC: Context Event Log

**Status:** RFC  
**Replaces:** `run_generation_turns` table + `RunGenerationTurn` model  
**Affects:** RL extraction, worker resumption, dashboard streaming, REST snapshot

---

## 1. Problem

`RunGenerationTurn` was designed to store one row per model call. It has three fundamental gaps that make lossless RL training and context reconstruction impossible:

**Gap 1 — No full context capture.** `prompt_text` stores a single formatted string on the first turn only. For a multi-turn agentic trajectory, we have no record of what messages were actually sent to the model at turns 1+. You cannot reconstruct what the model saw without replaying the entire episode.

**Gap 2 — KV-cache alignment is not guaranteed.** Because prompt context is reconstructed from loose text at extraction time (applying the chat template in `rollout_service.py`), the `prompt_ids` fed to TRL may differ from what the model saw during generation. This breaks KL divergence estimation and importance sampling.

**Gap 3 — Events are conflated into opaque blobs.** Tool calls, tool results, thinking tokens, and assistant text are all packed into `raw_response` (a framework-native dict) plus a few extracted JSON columns. They cannot be streamed individually, do not have independent token IDs or logprobs, and cannot be queried by type. The frontend, RL pipeline, and context reconstruction code all re-parse the same blob differently and inconsistently.

The result: the current schema works for simple single-turn benchmarks with a text output but breaks down for multi-turn agentic runs, extended thinking, lossless RL, or replaying exactly what an agent saw.

---

## 2. Terminology

**Turn** — one task execution, bounded by a `task_execution_id`. Maps 1:1 to a worker invocation today. In future, a turn may be paused at a tool-approval boundary and resumed; the event log handles this naturally since it is append-only.

**Generation** — one output unit from the model within a turn: a text response, a tool call, or a thinking block. A generation has logprobs when the backend (vLLM) supports them.

**Context event** — any discrete entry in the conversation sequence. The full ordered sequence of context events for a `task_execution_id` is the exact reconstruction of what was live in the model's context window at any point during that turn.

**The invariant:** read all context events for a `task_execution_id` ordered by `sequence` → reconstruct the exact message list the model saw. No inference, no re-tokenisation, no parsing of framework blobs required.

---

## 3. Target Schema: `run_context_events`

### 3.1 Table

```sql
CREATE TABLE run_context_events (
    id          UUID        PRIMARY KEY,
    run_id      UUID        NOT NULL REFERENCES runs(id),
    task_execution_id UUID  NOT NULL REFERENCES run_task_executions(id),
    worker_binding_key TEXT NOT NULL,

    -- Ordering
    sequence    INTEGER     NOT NULL,  -- monotonically increasing within task_execution_id
    created_at  TIMESTAMPTZ NOT NULL,  -- wall clock when persisted

    -- Timing (model-generated events only; NULL for environment events)
    started_at  TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Discriminated payload
    event_type  TEXT        NOT NULL,  -- see §3.2
    payload     JSONB       NOT NULL,  -- typed by event_type; see §3.3

    -- RL metadata (on model-generated events only)
    policy_version TEXT,
    execution_outcome TEXT  -- "success" | "failure" | NULL
);

CREATE UNIQUE INDEX ON run_context_events (task_execution_id, sequence);
CREATE INDEX ON run_context_events (run_id);
CREATE INDEX ON run_context_events (task_execution_id);
CREATE INDEX ON run_context_events (event_type);
```

The `UNIQUE` constraint on `(task_execution_id, sequence)` enforces append-only ordering and makes the log idempotent under retry.

### 3.2 Event types

| `event_type` | Produced by | Has logprobs |
|---|---|---|
| `system_prompt` | Worker / runtime at turn start | No |
| `user_message` | Worker or agent-to-agent delegation | No |
| `assistant_text` | Model | Yes (vLLM only) |
| `tool_call` | Model | Yes (vLLM only) |
| `tool_result` | Environment | No |
| `thinking` | Model (extended thinking only) | Yes (vLLM only) |

### 3.3 Payload shapes (Python discriminated union)

Each payload embeds `event_type` as a `Literal` field so Pydantic can discriminate on read — the same pattern as `GraphMutationValue` in `graph_dto.py`.

```python
# ergon_core/ergon_core/core/persistence/context/event_payloads.py

from typing import Annotated, Literal
from pydantic import BaseModel, Field
from ergon_core.api.generation import TokenLogprob


class SystemPromptPayload(BaseModel):
    event_type: Literal["system_prompt"] = "system_prompt"
    text: str


class UserMessagePayload(BaseModel):
    event_type: Literal["user_message"] = "user_message"
    text: str
    from_worker_key: str | None = None  # set for agent-to-agent messages


class AssistantTextPayload(BaseModel):
    event_type: Literal["assistant_text"] = "assistant_text"
    text: str
    token_ids: list[int] | None = None
    logprobs: list[TokenLogprob] | None = None


class ToolCallPayload(BaseModel):
    event_type: Literal["tool_call"] = "tool_call"
    tool_call_id: str
    tool_name: str
    args: dict[str, object]
    token_ids: list[int] | None = None
    logprobs: list[TokenLogprob] | None = None


class ToolResultPayload(BaseModel):
    event_type: Literal["tool_result"] = "tool_result"
    tool_call_id: str   # links back to the ToolCallPayload with the same id
    tool_name: str
    result: object      # the value returned by the tool
    is_error: bool = False


class ThinkingPayload(BaseModel):
    event_type: Literal["thinking"] = "thinking"
    text: str
    token_ids: list[int] | None = None
    logprobs: list[TokenLogprob] | None = None


ContextEventPayload = Annotated[
    SystemPromptPayload
    | UserMessagePayload
    | AssistantTextPayload
    | ToolCallPayload
    | ToolResultPayload
    | ThinkingPayload,
    Field(discriminator="event_type"),
]
```

### 3.4 ORM model

```python
# ergon_core/ergon_core/core/persistence/context/models.py

from pydantic import TypeAdapter
from ergon_core.core.persistence.context.event_payloads import ContextEventPayload


class RunContextEvent(SQLModel, table=True):
    __tablename__ = "run_context_events"

    id: UUID = Field(default_factory=new_id, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    task_execution_id: UUID = Field(
        foreign_key="run_task_executions.id", index=True
    )
    worker_binding_key: str = Field(index=True)
    sequence: int
    event_type: str = Field(index=True)
    payload: dict = Field(sa_column=Column(JSON))
    started_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    completed_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    policy_version: str | None = None
    execution_outcome: str | None = Field(default=None, index=True)

    def parsed_payload(self) -> ContextEventPayload:
        return TypeAdapter(ContextEventPayload).validate_python(self.payload)
```

---

## 4. Changes to the Write Path

### 4.1 Enriching `GenerationTurn`

`GenerationTurn` (the public worker API in `ergon_core/ergon_core/api/generation.py`) currently carries only `prompt_text: str | None` for context. It must be extended to carry the full input message list for turns after the first.

```python
class GenerationTurn(BaseModel):
    # --- NEW: full input context for this turn ---
    # Serialised PydanticAI ModelRequest parts, in order.
    # Set by the framework adapter (_build_turns in react_worker.py).
    # Workers do not set this directly.
    messages_in: list[dict[str, object]] = Field(default_factory=list)

    # Kept for backward compatibility; ignored when messages_in is set.
    prompt_text: str | None = None

    # --- Unchanged ---
    raw_response: dict[str, object]
    tool_results: list[dict[str, object]] = Field(default_factory=list)
    logprobs: list[TokenLogprob] | None = None
    policy_version: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
```

`messages_in` is a list of serialised PydanticAI message parts — the same structure already stored in `raw_response` for responses. The framework adapter (`_build_turns` in `react_worker.py`) is responsible for populating this; workers never set it directly.

### 4.2 Changes to `_build_turns` in `react_worker.py`

Currently `_build_turns` only extracts the `ModelResponse` into a `GenerationTurn` and pairs tool results from the subsequent `ModelRequest`. It must also carry the full `ModelRequest` parts for each turn so the runtime can emit `system_prompt`, `user_message`, and `tool_result` context events.

```python
def _build_turns(messages: list[ModelMessage]) -> list[GenerationTurn]:
    """Build GenerationTurn objects from PydanticAI message history.
    
    Each turn pairs one ModelResponse (the model's output) with the
    ModelRequest that preceded it (the context sent in) and the
    subsequent ModelRequest that carried tool results back.
    """
    turns: list[GenerationTurn] = []
    pending_response: ModelResponse | None = None
    pending_request_in: ModelRequest | None = None

    for message in messages:
        if isinstance(message, ModelRequest):
            if pending_response is not None:
                # Close the pending turn: this request carries its tool results
                turns.append(_to_turn(
                    pending_request_in,
                    pending_response,
                    tool_result_request=message,
                ))
                pending_response = None
                pending_request_in = None
            # This request is the context for the NEXT model call
            pending_request_in = message
        elif isinstance(message, ModelResponse):
            pending_response = message

    if pending_response is not None:
        turns.append(_to_turn(pending_request_in, pending_response, tool_result_request=None))

    return turns


def _to_turn(
    request_in: ModelRequest | None,
    response: ModelResponse,
    tool_result_request: ModelRequest | None,
) -> GenerationTurn:
    raw_resp = _make_json_safe(dataclasses.asdict(response))
    messages_in = (
        [_make_json_safe(dataclasses.asdict(p)) for p in request_in.parts]
        if request_in else []
    )
    tool_results = (
        _extract_tool_results(tool_result_request)
        if tool_result_request else []
    )
    return GenerationTurn(
        messages_in=messages_in,
        raw_response=raw_resp,
        tool_results=tool_results,
        logprobs=extract_logprobs(raw_resp),
    )
```

### 4.3 New `ContextEventRepository`

```python
# ergon_core/ergon_core/core/persistence/context/repository.py

class ContextEventRepository:
    """Append-only write path for run_context_events."""

    def __init__(self) -> None:
        self._listeners: list[Callable[[RunContextEvent], Awaitable[None]]] = []
        self._sequence_counters: dict[UUID, int] = {}  # task_execution_id → next seq

    def add_listener(self, listener: Callable[[RunContextEvent], Awaitable[None]]) -> None:
        self._listeners.append(listener)

    async def persist_turn(
        self,
        session: Session,
        *,
        run_id: UUID,
        execution_id: UUID,
        worker_binding_key: str,
        turn: GenerationTurn,
        execution_outcome: ExecutionOutcome = "success",
    ) -> list[RunContextEvent]:
        """Decompose one GenerationTurn into ordered context events and persist them.

        Emits events in this order:
          1. system_prompt (from messages_in SystemPromptPart, first turn only)
          2. user_message (from messages_in UserPromptPart, first turn only)
          3. thinking (from raw_response, if present)
          4. assistant_text / tool_call (from raw_response parts)
          5. tool_result (from turn.tool_results, one per tool call)

        Returns the list of persisted events (in sequence order).
        """
        events: list[RunContextEvent] = []
        seq = self._next_sequence(execution_id)

        # 1–2. Context events from messages_in (first turn only — system + user)
        for part in turn.messages_in:
            part_kind = part.get("part_kind")
            if part_kind == "system-prompt":
                events.append(self._make_event(
                    run_id, execution_id, worker_binding_key, seq,
                    SystemPromptPayload(text=part.get("content", "")),
                ))
                seq += 1
            elif part_kind == "user-prompt":
                events.append(self._make_event(
                    run_id, execution_id, worker_binding_key, seq,
                    UserMessagePayload(text=part.get("content", "")),
                ))
                seq += 1
            # tool-return parts are handled as tool_result events below

        # 3–4. Events from raw_response (model-generated)
        response_parts = turn.raw_response.get("parts", [])
        for part in response_parts:
            part_kind = part.get("part_kind")
            if part_kind == "thinking":
                events.append(self._make_event(
                    run_id, execution_id, worker_binding_key, seq,
                    ThinkingPayload(
                        text=part.get("content", ""),
                        # token_ids populated once vLLM provides them natively
                    ),
                    started_at=turn.started_at,
                    completed_at=turn.completed_at,
                    policy_version=turn.policy_version,
                    execution_outcome=execution_outcome,
                ))
                seq += 1
            elif part_kind == "text":
                events.append(self._make_event(
                    run_id, execution_id, worker_binding_key, seq,
                    AssistantTextPayload(
                        text=part.get("content", ""),
                        logprobs=turn.logprobs,
                    ),
                    started_at=turn.started_at,
                    completed_at=turn.completed_at,
                    policy_version=turn.policy_version,
                    execution_outcome=execution_outcome,
                ))
                seq += 1
            elif part_kind == "tool-call":
                events.append(self._make_event(
                    run_id, execution_id, worker_binding_key, seq,
                    ToolCallPayload(
                        tool_call_id=part.get("tool_call_id", ""),
                        tool_name=part.get("tool_name", ""),
                        args=part.get("args") or {},
                        logprobs=turn.logprobs,
                    ),
                    started_at=turn.started_at,
                    completed_at=turn.completed_at,
                    policy_version=turn.policy_version,
                    execution_outcome=execution_outcome,
                ))
                seq += 1

        # 5. Tool results
        for tr in turn.tool_results:
            events.append(self._make_event(
                run_id, execution_id, worker_binding_key, seq,
                ToolResultPayload(
                    tool_call_id=tr.get("tool_call_id", ""),
                    tool_name=tr.get("tool_name", ""),
                    result=tr.get("result"),
                    is_error=bool(tr.get("is_error", False)),
                ),
            ))
            seq += 1

        self._sequence_counters[execution_id] = seq

        for event in events:
            session.add(event)
        session.commit()

        for event in events:
            for listener in self._listeners:
                try:
                    await listener(event)
                except Exception:
                    logger.warning("Context event listener failed", exc_info=True)

        return events

    def get_for_execution(
        self, session: Session, execution_id: UUID
    ) -> list[RunContextEvent]:
        stmt = (
            select(RunContextEvent)
            .where(RunContextEvent.task_execution_id == execution_id)
            .order_by(RunContextEvent.sequence)
        )
        return list(session.exec(stmt).all())

    def get_for_run(
        self, session: Session, run_id: UUID
    ) -> list[RunContextEvent]:
        stmt = (
            select(RunContextEvent)
            .where(RunContextEvent.run_id == run_id)
            .order_by(RunContextEvent.task_execution_id, RunContextEvent.sequence)
        )
        return list(session.exec(stmt).all())
```

### 4.4 Changes to `worker_execute.py`

Replace the call to `repo.persist_single()` with `context_event_repo.persist_turn()`:

```python
# Before (current)
repo = GenerationTurnRepository()
repo.add_listener(dashboard_emitter.on_turn_persisted)
...
await repo.persist_single(session, run_id=..., execution_id=..., turn=turn, ...)

# After
context_event_repo = ContextEventRepository()
context_event_repo.add_listener(dashboard_emitter.on_context_event)
...
await context_event_repo.persist_turn(session, run_id=..., execution_id=..., turn=turn, ...)
```

---

## 5. Read Paths

### 5.1 RL Extraction

`extraction.py` currently groups `RunGenerationTurn` rows by `worker_binding_key` and builds flat token sequences from `response_text` / `logprobs_json`. With the new schema, the same logic becomes explicit and correct:

```
agent_tokens  = events where event_type IN (assistant_text, tool_call, thinking)
env_tokens    = events where event_type = tool_result
env_mask      = 1 for agent_tokens, 0 for env_tokens
token_ids     = payload.token_ids (native, no re-tokenisation needed)
logprobs      = payload.logprobs (per-token, directly from payload)
```

The prompt context (`prompt_ids`) is reconstructed from the ordered system_prompt + user_message events for the execution, tokenised once.

Key improvement: token IDs from vLLM are stored natively per event (no re-tokenisation from token strings). The `token_ids_json` column on `RunGenerationTurn` was always NULL; these fields on `AssistantTextPayload`/`ToolCallPayload`/`ThinkingPayload` will be populated once the vLLM provider is updated to expose them through PydanticAI's `provider_details`.

### 5.2 Context Reconstruction / `from_buffer()`

`ReActWorker.from_buffer()` currently does:
```python
worker._seed_messages.append(ModelResponse(**turn.raw_response))
```

With the new schema, this becomes an assembly step that reconstructs PydanticAI `ModelRequest`/`ModelResponse` pairs from the event log:

```python
@classmethod
def from_buffer(cls, execution_id: UUID, session: Session, ...) -> Self | None:
    repo = ContextEventRepository()
    events = repo.get_for_execution(session, execution_id)
    seed_messages = assemble_pydantic_ai_messages(events)
    worker = cls(...)
    worker._seed_messages = seed_messages
    return worker
```

`assemble_pydantic_ai_messages(events)` reconstructs the alternating `ModelRequest`/`ModelResponse` sequence from the structured event fields only:

- `system_prompt` events → `SystemPromptPart` in the first `ModelRequest`
- `user_message` events → `UserPromptPart` in the first `ModelRequest`
- `thinking` events → `ThinkingPart` in the current `ModelResponse`
- `assistant_text` events → `TextPart` in the current `ModelResponse`
- `tool_call` events → `ToolCallPart` in the current `ModelResponse`
- `tool_result` events → `ToolReturnPart` in the next `ModelRequest`

Grouping rule: consecutive model-generated events (`thinking`, `assistant_text`, `tool_call`) with no intervening `tool_result` belong to the same `ModelResponse`. A `tool_result` event closes the current `ModelResponse` and opens a new `ModelRequest`. This means thinking tokens are always included in the reconstructed history — they are first-class `ThinkingPart` entries, not dropped.

This function lives in `ergon_core/ergon_core/core/persistence/context/assembly.py`.

### 5.3 Dashboard Streaming

`DashboardEmitter` gains a new listener method:

```python
async def on_context_event(self, event: RunContextEvent) -> None:
    """Emit one context event to the dashboard over Inngest."""
    await self._send(DashboardContextEventEvent(
        run_id=event.run_id,
        task_execution_id=event.task_execution_id,
        worker_binding_key=event.worker_binding_key,
        sequence=event.sequence,
        event_type=event.event_type,
        payload=event.payload,
        created_at=event.created_at,
    ))
```

The frontend receives one `dashboard/context.event` Inngest event per `RunContextEvent` row. The dashboard renders each event as a bubble in the generation panel — system prompts, user messages, thinking, tool calls, tool results, and assistant text are all first-class display types. No client-side parsing of `raw_response` blobs.

### 5.4 REST Snapshot

`GET /runs/{run_id}` (`build_run_snapshot`) currently loads `RunGenerationTurn` rows and groups by `execution_task_map` into `generation_turns_by_task`. This is replaced by loading `RunContextEvent` rows grouped by execution:

```python
context_events_stmt = (
    select(RunContextEvent)
    .where(RunContextEvent.run_id == run_id)
    .order_by(RunContextEvent.task_execution_id, RunContextEvent.sequence)
)
context_events = list(session.exec(context_events_stmt).all())

context_events_by_task: dict[str, list[RunContextEventDto]] = defaultdict(list)
for event in context_events:
    task_node_id = execution_task_map.get(event.task_execution_id)
    if task_node_id is None:
        continue
    context_events_by_task[str(task_node_id)].append(
        RunContextEventDto(
            id=str(event.id),
            task_execution_id=str(event.task_execution_id),
            sequence=event.sequence,
            event_type=event.event_type,
            payload=event.payload,
            created_at=event.created_at.isoformat(),
        )
    )
```

The `RunSnapshotDto` field `generation_turns_by_task` is renamed to `context_events_by_task` and typed accordingly.

---

## 6. File Map

### New files
```
ergon_core/ergon_core/core/persistence/context/
    __init__.py
    models.py                  — RunContextEvent ORM model
    event_payloads.py          — ContextEventPayload discriminated union (all 6 types)
    repository.py              — ContextEventRepository (persist_turn, get_for_execution, get_for_run)
    assembly.py                — assemble_pydantic_ai_messages() for from_buffer() reconstruction
ergon_core/migrations/versions/<hash>_add_run_context_events.py
```

### Changed files
```
ergon_core/ergon_core/api/generation.py
    + messages_in: list[dict[str, object]] on GenerationTurn

ergon_builtins/ergon_builtins/workers/baselines/react_worker.py
    ~ _build_turns(): populate messages_in from ModelRequest parts
    ~ _to_turn(): accepts request_in + response + tool_result_request
    ~ from_buffer(): use assemble_pydantic_ai_messages() instead of raw_response

ergon_core/ergon_core/core/runtime/inngest/worker_execute.py
    ~ replace GenerationTurnRepository + persist_single with ContextEventRepository + persist_turn

ergon_core/ergon_core/core/dashboard/emitter.py
    + on_context_event() listener
    + DashboardContextEventEvent contract

ergon_core/ergon_core/core/dashboard/event_contracts.py
    + DashboardContextEventEvent

ergon_core/ergon_core/core/api/runs.py
    ~ build_run_snapshot(): load RunContextEvent instead of RunGenerationTurn
    ~ RunSnapshotDto: generation_turns_by_task → context_events_by_task

ergon_core/ergon_core/core/api/schemas.py
    + RunContextEventDto
    ~ RunSnapshotDto: generation_turns_by_task → context_events_by_task

ergon_core/ergon_core/core/rl/extraction.py
    ~ extract_agent_trajectories(): read RunContextEvent instead of RunGenerationTurn

ergon-dashboard/src/features/graph/  (frontend)
    ~ generation turn display → context event display (system_prompt, thinking, tool_call etc.)
```

### Deprecated (stop writing, keep for historical reads)
```
ergon_core/ergon_core/core/persistence/telemetry/models.py — RunGenerationTurn
ergon_core/ergon_core/core/persistence/telemetry/repositories.py — GenerationTurnRepository
ergon_core/ergon_core/core/api/runs.py — GET /runs/{run_id}/generations endpoint (superseded by context_events_by_task in snapshot)
```

---

## 7. Migration Plan

The migration is additive. The old table is never dropped until every reader has been migrated. No data is backfilled — historical runs keep `RunGenerationTurn` rows; new runs write `RunContextEvent` rows only.

### Phase 0 — Schema (no behaviour change)

- Add Alembic migration: `run_context_events` table.
- Add ORM model, payload types, repository — no callers yet.
- Deploy. Verify table exists.

### Phase 1 — Dual write

- Update `_build_turns()` to populate `messages_in` on `GenerationTurn`.
- Update `worker_execute.py` to call **both** `GenerationTurnRepository.persist_single()` and `ContextEventRepository.persist_turn()` for every turn.
- Update `DashboardEmitter` to emit `DashboardContextEventEvent` alongside the existing `DashboardGenerationTurnEvent`.
- Deploy. Verify both tables are populated for new runs. Existing reads are unchanged.

### Phase 2 — Migrate reads

In any order (each is independently deployable):

- **RL extraction** (`extraction.py`): read from `RunContextEvent`. Gate on `len(context_events) > 0`; fall back to `RunGenerationTurn` if no events exist (historical run).
- **REST snapshot** (`runs.py`): load `RunContextEvent` into `context_events_by_task`. Keep `generation_turns_by_task` populated from `RunGenerationTurn` until the frontend is updated.
- **Worker resumption** (`react_worker.py` `from_buffer()`): use `assemble_pydantic_ai_messages()`. If no context events exist for the execution (historical run), `from_buffer()` returns `None` (same as today's "execution not found" path) — do not fall back to `raw_response` blob reconstruction.
- **Frontend**: update generation panel to consume `context_events_by_task` from the snapshot and `dashboard/context.event` from the socket. Remove `generation_turns_by_task` consumption.
- **`GET /runs/{run_id}/generations` endpoint**: mark deprecated in OpenAPI docs.

Deploy and verify each migration independently before proceeding.

### Phase 3 — Decommission

Once all readers have been migrated and no new `RunGenerationTurn` rows are being written:

- Remove the dual-write call to `GenerationTurnRepository.persist_single()` from `worker_execute.py`.
- Remove the `DashboardGenerationTurnEvent` emit from `DashboardEmitter`.
- Remove `GET /runs/{run_id}/generations` endpoint.
- Remove `generation_turns_by_task` from `RunSnapshotDto`.
- Archive `RunGenerationTurn` model and `GenerationTurnRepository` (keep the table; do not drop it — historical data lives there).

### Migration go/no-go criteria

| Gate | Check |
|---|---|
| Phase 0 → 1 | `run_context_events` table exists in prod, migration clean |
| Phase 1 → 2 | Both tables populate correctly for 10+ live runs, event counts match turn counts |
| Phase 2 → 3 | All readers verified, frontend uses context_events_by_task, RL extraction reads from new table |
| Phase 3 | Zero active callers of `GenerationTurnRepository.persist_single()` |

---

## 8. Known Gaps Deferred to Later Work

**Token IDs from vLLM.** `AssistantTextPayload.token_ids` and `ToolCallPayload.token_ids` are defined but will remain `None` until the vLLM provider is updated to extract token IDs from `provider_details` (PydanticAI currently exposes logprobs but drops token IDs). This does not block the schema migration; it is tracked as a separate provider improvement.

**Extended thinking extraction.** `ThinkingPayload` is defined. Extraction from PydanticAI's `ModelResponse` (`part_kind == "thinking"`) requires verifying the actual field name in the PydanticAI dataclass for the Claude backend. This should be confirmed during Phase 1 implementation.

**Agent-to-agent messages.** `UserMessagePayload.from_worker_key` is defined for delegation messages (where one agent sends a message to another). Populating this requires the task management toolkit to emit a `user_message` context event when a delegation result is returned. Not required for Phase 1; add in a follow-on when agent-to-agent communication logging is needed.

**System prompt deduplication.** In a multi-turn execution the system prompt is constant but currently emitted once (on the first turn's `messages_in`). The assembly function must handle this correctly — reconstruct it as a single leading `SystemPromptPart` regardless of how many turns exist. This is a `assembly.py` implementation concern, not a schema concern.

---

## 9. What This Doesn't Change

- Worker `execute()` signature — still `async def execute(...) -> AsyncGenerator[GenerationTurn, None]`
- `WorkerContext` — unchanged
- Graph WAL (`run_graph_mutations`) — separate concern
- Task execution records (`RunTaskExecution`) — unchanged
- Evaluation records (`RunTaskEvaluation`) — unchanged
- All existing `graph:mutation`, `task:status` socket events — unchanged
