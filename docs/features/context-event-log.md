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
    policy_version TEXT
);

CREATE UNIQUE INDEX ON run_context_events (task_execution_id, sequence);
CREATE INDEX ON run_context_events (run_id);
CREATE INDEX ON run_context_events (task_execution_id);
CREATE INDEX ON run_context_events (event_type);
```

The `UNIQUE` constraint on `(task_execution_id, sequence)` enforces append-only ordering and makes the log idempotent under retry.

### 3.2 Event types

| `event_type` | Produced by | Has `turn_token_ids` / `turn_logprobs` |
|---|---|---|
| `system_prompt` | Worker / runtime at turn start | No |
| `user_message` | Worker or agent-to-agent delegation | No |
| `assistant_text` | Model | On first model-output event of the turn (vLLM only; `None` until provider support added) |
| `tool_call` | Model | On first model-output event of the turn (vLLM only; `None` until provider support added) |
| `tool_result` | Environment | No |
| `thinking` | Model (extended thinking only) | On first model-output event of the turn (vLLM only; `None` until provider support added) |

### 3.3 Payload shapes (Python discriminated union)

Each payload embeds `event_type` as a `Literal` field so Pydantic can discriminate on read — the same pattern as `GraphMutationValue` in `graph_dto.py`.

```python
# ergon_core/ergon_core/core/persistence/context/event_payloads.py

from typing import Annotated, Any, Literal
from pydantic import BaseModel, Field
from ergon_core.api.generation import TokenLogprob


# Exported type alias — use everywhere event_type is stored as a string field
ContextEventType = Literal[
    "system_prompt",
    "user_message",
    "assistant_text",
    "tool_call",
    "tool_result",
    "thinking",
]


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
    turn_id: str                                        # links events from the same generation call
    turn_token_ids: list[int] | None = None             # set on FIRST model-output event of the turn only
    turn_logprobs: list[TokenLogprob] | None = None     # set on FIRST model-output event of the turn only


class ToolCallPayload(BaseModel):
    event_type: Literal["tool_call"] = "tool_call"
    tool_call_id: str
    tool_name: str
    args: dict[str, Any]
    turn_id: str                                        # links events from the same generation call
    turn_token_ids: list[int] | None = None             # None if another event in this turn holds them
    turn_logprobs: list[TokenLogprob] | None = None     # None if another event in this turn holds them


class ToolResultPayload(BaseModel):
    event_type: Literal["tool_result"] = "tool_result"
    tool_call_id: str   # links back to the ToolCallPayload with the same id
    tool_name: str
    result: Any         # tool returns are intentionally open — any JSON-serialisable value
    is_error: bool = False


class ThinkingPayload(BaseModel):
    event_type: Literal["thinking"] = "thinking"
    text: str
    turn_id: str                                        # links events from the same generation call
    turn_token_ids: list[int] | None = None             # set on FIRST model-output event of the turn only
    turn_logprobs: list[TokenLogprob] | None = None     # set on FIRST model-output event of the turn only


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
from sqlalchemy.dialects.postgresql import JSONB
from ergon_core.core.persistence.context.event_payloads import (
    ContextEventPayload,
    ContextEventType,
)


class RunContextEvent(SQLModel, table=True):
    __tablename__ = "run_context_events"

    id: UUID = Field(default_factory=new_id, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    task_execution_id: UUID = Field(
        foreign_key="run_task_executions.id", index=True
    )
    worker_binding_key: str = Field(index=True)
    sequence: int
    event_type: ContextEventType = Field(index=True)
    payload: dict[str, Any] = Field(sa_column=Column(JSONB))
    # Note: SQLAlchemy maps JSONB to TEXT in SQLite (used in tests) — no fixture changes needed.
    started_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    completed_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    policy_version: str | None = None

    def parsed_payload(self) -> ContextEventPayload:
        return TypeAdapter(ContextEventPayload).validate_python(self.payload)
```

---

## 4. Changes to the Write Path

### 4.1 Enriching `GenerationTurn`

`GenerationTurn` (the public worker API in `ergon_core/ergon_core/api/generation.py`) must be updated to carry the full typed input message list and drop the old `prompt_text` field.

Define two discriminated unions alongside `GenerationTurn` — one for request parts (input to the model) and one for response parts (output from the model). Part kind names mirror PydanticAI's field names so construction from framework objects is direct, with no intermediate dict serialisation.

```python
# ergon_core/ergon_core/api/generation.py

from typing import Annotated, Literal
from pydantic import BaseModel, Field


# --- Request parts (ModelRequest input) ---

class SystemPromptPart(BaseModel):
    part_kind: Literal["system-prompt"] = "system-prompt"
    content: str


class UserPromptPart(BaseModel):
    part_kind: Literal["user-prompt"] = "user-prompt"
    content: str


class ToolReturnPart(BaseModel):
    part_kind: Literal["tool-return"] = "tool-return"
    tool_call_id: str
    tool_name: str
    content: str


ModelRequestPart = Annotated[
    SystemPromptPart | UserPromptPart | ToolReturnPart,
    Field(discriminator="part_kind"),
]


# --- Response parts (ModelResponse output) ---

class TextPart(BaseModel):
    part_kind: Literal["text"] = "text"
    content: str


class ToolCallPart(BaseModel):
    part_kind: Literal["tool-call"] = "tool-call"
    tool_name: str
    tool_call_id: str
    args: dict[str, Any]


class ThinkingPart(BaseModel):
    part_kind: Literal["thinking"] = "thinking"
    content: str


ModelResponsePart = Annotated[
    TextPart | ToolCallPart | ThinkingPart,
    Field(discriminator="part_kind"),
]


class GenerationTurn(BaseModel):
    # Set by the framework adapter (_build_turns in react_worker.py).
    # Workers do not set these directly.
    messages_in: list[ModelRequestPart] = Field(default_factory=list)
    response_parts: list[ModelResponsePart] = Field(default_factory=list)
    tool_results: list[ToolReturnPart] = Field(default_factory=list)

    # turn_token_ids and turn_logprobs are both turn-level: flat lists covering all
    # model-generated tokens in this generation call in generation order (text, thinking,
    # tool args — whichever vLLM exposes). Both stored on the FIRST model-output context
    # event only; group by turn_id to find them.
    # turn_token_ids: None until the vLLM provider is updated to extract token IDs from
    # provider_details (PydanticAI currently exposes logprobs but drops token IDs).
    turn_token_ids: list[int] | None = None
    turn_logprobs: list[TokenLogprob] | None = None
    policy_version: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
```

`prompt_text` and `raw_response` are removed entirely. The framework adapter (`_build_turns` in `react_worker.py`) is responsible for populating all three list fields; workers never set them directly.

### 4.2 Changes to `_build_turns` in `react_worker.py`

Currently `_build_turns` only extracts the `ModelResponse` into a `GenerationTurn` and pairs tool results from the subsequent `ModelRequest`. It must also carry the full `ModelRequest` parts for each turn so the runtime can emit `system_prompt`, `user_message`, and `tool_result` context events.

> **PydanticAI message utilities:**
> - The caller passes `result.all_messages()` (or `result.new_messages()`) from the `RunResult` into `_build_turns` — do not accumulate messages manually.
> - PydanticAI also provides a `history_processors` hook for modifying history before each model call (filtering, truncation, summarisation). This is a different concern — it runs in the hot path of agent execution, not as a post-processing step. Do not conflate the two.
> - `ModelMessagesTypeAdapter` (`pydantic_ai.messages`) handles full round-trip serialisation of `list[ModelMessage]` if you ever need to serialise the raw list for debugging. Do not use `dataclasses.asdict` on PydanticAI message objects.
> - The turn-grouping and part-extraction logic below is still hand-written: PydanticAI has no concept of "turns" as defined here.

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
    return GenerationTurn(
        messages_in=_extract_request_parts(request_in) if request_in else [],
        response_parts=_extract_response_parts(response),
        tool_results=_extract_tool_results(tool_result_request) if tool_result_request else [],
        logprobs=extract_logprobs(response),
    )


def _extract_request_parts(request: ModelRequest) -> list[ModelRequestPart]:
    parts: list[ModelRequestPart] = []
    for part in request.parts:
        if isinstance(part, PydanticSystemPromptPart):
            parts.append(SystemPromptPart(content=part.content))
        elif isinstance(part, PydanticUserPromptPart) and isinstance(part.content, str):
            parts.append(UserPromptPart(content=part.content))
        elif isinstance(part, PydanticToolReturnPart):
            parts.append(ToolReturnPart(
                tool_call_id=part.tool_call_id,
                tool_name=part.tool_name,
                content=part.content,
            ))
        # Other part kinds (e.g. image content) are not yet supported — skip.
    return parts


def _extract_response_parts(response: ModelResponse) -> list[ModelResponsePart]:
    parts: list[ModelResponsePart] = []
    for part in response.parts:
        if isinstance(part, PydanticTextPart):
            parts.append(TextPart(content=part.content))
        elif isinstance(part, PydanticToolCallPart):
            parts.append(ToolCallPart(
                tool_name=part.tool_name,
                tool_call_id=part.tool_call_id,
                args=part.args_as_dict(),
            ))
        elif isinstance(part, PydanticThinkingPart):
            parts.append(ThinkingPart(content=part.content))
        # Other part kinds are not yet supported — skip.
    return parts
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

    def _make_event(
        self,
        run_id: UUID,
        execution_id: UUID,
        worker_binding_key: str,
        sequence: int,
        payload: ContextEventPayload,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        policy_version: str | None = None,
    ) -> RunContextEvent:
        return RunContextEvent(
            run_id=run_id,
            task_execution_id=execution_id,
            worker_binding_key=worker_binding_key,
            sequence=sequence,
            event_type=payload.event_type,
            payload=payload.model_dump(mode="json"),
            started_at=started_at,
            completed_at=completed_at,
            policy_version=policy_version,
        )

    async def persist_turn(
        self,
        session: Session,
        *,
        run_id: UUID,
        execution_id: UUID,
        worker_binding_key: str,
        turn: GenerationTurn,
    ) -> list[RunContextEvent]:
        """Decompose one GenerationTurn into ordered context events and persist them.

        Emits events in this order:
          1. system_prompt (from messages_in SystemPromptPart, first turn only)
          2. user_message (from messages_in UserPromptPart, first turn only)
          3. thinking (from response_parts ThinkingPart, if present)
          4. assistant_text / tool_call (from response_parts TextPart / ToolCallPart)
          5. tool_result (from tool_results, one per ToolReturnPart)

        Returns the list of persisted events (in sequence order).
        """
        events: list[RunContextEvent] = []
        seq = self._next_sequence(execution_id)

        # Each generation call gets a unique turn_id so model-output events can be
        # grouped. turn_token_ids and turn_logprobs are both stored on the FIRST
        # model-output event only; subsequent events in the same turn have None.
        turn_id = str(uuid4())
        turn_token_ids_remaining = turn.turn_token_ids
        turn_logprobs_remaining = turn.turn_logprobs

        # 1–2. Context events from messages_in (first turn only — system + user)
        for part in turn.messages_in:
            if isinstance(part, SystemPromptPart):
                events.append(self._make_event(
                    run_id, execution_id, worker_binding_key, seq,
                    SystemPromptPayload(text=part.content),
                ))
                seq += 1
            elif isinstance(part, UserPromptPart):
                events.append(self._make_event(
                    run_id, execution_id, worker_binding_key, seq,
                    UserMessagePayload(text=part.content),
                ))
                seq += 1
            # ToolReturnPart entries are handled as tool_result events below

        # 3–4. Events from response_parts (model-generated)
        for part in turn.response_parts:
            if isinstance(part, ThinkingPart):
                events.append(self._make_event(
                    run_id, execution_id, worker_binding_key, seq,
                    ThinkingPayload(
                        text=part.content,
                        turn_id=turn_id,
                        turn_token_ids=turn_token_ids_remaining,
                        turn_logprobs=turn_logprobs_remaining,
                    ),
                    started_at=turn.started_at,
                    completed_at=turn.completed_at,
                    policy_version=turn.policy_version,
                ))
                turn_token_ids_remaining = None  # assigned to first event; clear for rest
                turn_logprobs_remaining = None
                seq += 1
            elif isinstance(part, TextPart):
                events.append(self._make_event(
                    run_id, execution_id, worker_binding_key, seq,
                    AssistantTextPayload(
                        text=part.content,
                        turn_id=turn_id,
                        turn_token_ids=turn_token_ids_remaining,
                        turn_logprobs=turn_logprobs_remaining,
                    ),
                    started_at=turn.started_at,
                    completed_at=turn.completed_at,
                    policy_version=turn.policy_version,
                ))
                turn_token_ids_remaining = None
                turn_logprobs_remaining = None
                seq += 1
            elif isinstance(part, ToolCallPart):
                events.append(self._make_event(
                    run_id, execution_id, worker_binding_key, seq,
                    ToolCallPayload(
                        tool_call_id=part.tool_call_id,
                        tool_name=part.tool_name,
                        args=part.args,
                        turn_id=turn_id,
                        turn_token_ids=turn_token_ids_remaining,
                        turn_logprobs=turn_logprobs_remaining,
                    ),
                    started_at=turn.started_at,
                    completed_at=turn.completed_at,
                    policy_version=turn.policy_version,
                ))
                turn_token_ids_remaining = None
                turn_logprobs_remaining = None
                seq += 1

        # 5. Tool results
        for tr in turn.tool_results:
            events.append(self._make_event(
                run_id, execution_id, worker_binding_key, seq,
                ToolResultPayload(
                    tool_call_id=tr.tool_call_id,
                    tool_name=tr.tool_name,
                    result=tr.content,
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
# Build turns from ALL messages — not an incremental slice.
result: RunResult = await agent.run(...)
turns = _build_turns(result.all_messages())
for turn in turns:
    # Register the execution→node mapping before emitting events so the
    # DashboardEmitter can resolve task_node_id in on_context_event.
    dashboard_emitter.register_execution(execution_id=execution_id, task_node_id=node_id)
    await context_event_repo.persist_turn(
        session, run_id=run_id, execution_id=execution_id,
        worker_binding_key=worker_binding_key, turn=turn,
    )
```

### 4.5 Listener Chain (Python → Inngest → Socket → Client)

The full event flow for every `RunContextEvent` row committed to Postgres:

```
persist_turn() commits row
  → calls on_context_event(event: RunContextEvent)
    → sends Inngest event "dashboard/context.event"
      → Inngest function runs in dashboard server
        → store.addContextEvent(runId, taskNodeId, event)
        → broadcastContextEvent(runId, taskNodeId, event)
          → socket.io "context:event" to run room
            → client updates local state
```

#### `DashboardContextEventEvent` contract

```python
# ergon_core/ergon_core/core/dashboard/event_contracts.py

class DashboardContextEventEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/context.event"

    id: UUID                        # RunContextEvent.id — used as dedup key on the frontend
    run_id: UUID
    task_execution_id: UUID
    task_node_id: UUID              # resolved from _execution_task_map at emit time
    worker_binding_key: str
    sequence: int
    event_type: ContextEventType    # imported from event_payloads
    payload: ContextEventPayload    # full typed discriminated union; serialised via model_dump(mode="json")
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
```

`task_node_id` is resolved by the emitter from the in-memory `execution_task_map` held by the run context. The frontend should not need to do this lookup — it receives the node ID it needs to index into the task graph directly.

#### `DashboardEmitter.on_context_event`

```python
# ergon_core/ergon_core/core/dashboard/emitter.py

async def on_context_event(self, event: RunContextEvent) -> None:
    """Called by ContextEventRepository after each event is committed.

    Resolves task_node_id from the execution map and emits a typed
    Inngest event. Non-blocking: errors are caught and logged.
    """
    if not self._enabled:
        return
    try:
        task_node_id = self._execution_task_map.get(event.task_execution_id)
        if task_node_id is None:
            logger.warning(
                "on_context_event: no task_node_id for execution %s", event.task_execution_id
            )
            return
        evt = DashboardContextEventEvent(
            run_id=event.run_id,
            task_execution_id=event.task_execution_id,
            task_node_id=task_node_id,
            worker_binding_key=event.worker_binding_key,
            sequence=event.sequence,
            event_type=event.event_type,
            payload=event.payload,
            created_at=event.created_at,
            started_at=event.started_at,
            completed_at=event.completed_at,
        )
        await inngest_client.send(
            inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
        )
    except Exception:
        logger.warning("Failed to emit dashboard/context.event", exc_info=True)
```

`_execution_task_map: dict[UUID, UUID]` must be added to `DashboardEmitter`. It is populated via a new `register_execution` method called from `worker_execute.py` before `persist_turn` (see §4.4):

```python
def register_execution(self, execution_id: UUID, task_node_id: UUID) -> None:
    """Register execution_id → task graph node_id mapping.
    Called from worker_execute.py before persist_turn so that on_context_event
    can resolve task_node_id without a DB lookup."""
    self._execution_task_map[execution_id] = task_node_id
```

#### Frontend Inngest function

`parseDashboardContextEventData` is a Zod parse helper that validates raw Inngest event data against the `DashboardContextEventEvent` Zod schema (defined in `ergon-dashboard/src/lib/contracts/events.ts`). It throws on validation failure. The `id` field on `ContextEventState` maps to `event.data.id` from the Inngest payload — it is used as the deduplication key in `addContextEvent` and the socket handler.

```typescript
// ergon-dashboard/src/inngest/functions/onContextEvent.ts

export const onContextEvent = inngest.createFunction(
  { id: "dashboard-context-event" },
  { event: "dashboard/context.event" },
  async ({ event }) => {
    const payload = parseDashboardContextEventData(event.data);

    const contextEvent: ContextEventState = {
      id: payload.id,
      taskExecutionId: payload.task_execution_id,
      taskNodeId: payload.task_node_id,
      workerBindingKey: payload.worker_binding_key,
      sequence: payload.sequence,
      eventType: payload.event_type as ContextEventType,
      payload: payload.payload as ContextEventPayload,
      createdAt: payload.created_at,
      startedAt: payload.started_at ?? null,
      completedAt: payload.completed_at ?? null,
    };

    store.addContextEvent(payload.run_id, payload.task_node_id, contextEvent);
    broadcastContextEvent(payload.run_id, payload.task_node_id, contextEvent);

    return { success: true };
  },
);
```

#### Socket event

```typescript
// ergon-dashboard/src/lib/socket/types.ts

export interface ServerToClientEvents {
  // existing events ...
  "context:event": (data: {
    runId: string;
    taskNodeId: string;
    event: ContextEventState;
  }) => void;
}
```

---

## 5. Read Paths

### 5.1 RL Extraction

`extraction.py` currently groups `RunGenerationTurn` rows by `worker_binding_key` and builds flat token sequences from `response_text` / `logprobs_json`. The `env_mask` is inferred heuristically from the presence of tool calls. With the new schema this becomes exact and explicit.

#### New function signature

The function signature is unchanged — callers pass pre-fetched rows; `extraction.py` does not query the DB directly.

```python
# ergon_core/ergon_core/core/rl/extraction.py

def extract_agent_trajectories(
    context_events: list[RunContextEvent],
    eval_scores: dict[str, float],        # task_execution_id (str) → score
    tokenizer: Tokenizer,
    *,
    reward_strategy: RewardStrategy | None = None,
) -> list[AgentTrajectory]:
    """Build TRL-compatible trajectories from context events.

    One AgentTrajectory is returned per unique worker_binding_key.
    Events must be pre-ordered by (task_execution_id, sequence) — the
    caller is responsible for this ordering (matches get_for_run output).
    """
```

`prompt_text` is removed from the signature — the prompt is now reconstructed from `system_prompt` + `user_message` events directly, so callers no longer need to pass it separately.

#### Extraction logic

```python
def extract_agent_trajectories(...) -> list[AgentTrajectory]:
    # Group events by worker_binding_key, preserving sequence order within each group
    by_worker: dict[str, list[RunContextEvent]] = defaultdict(list)
    for event in context_events:
        by_worker[event.worker_binding_key].append(event)

    trajectories: list[AgentTrajectory] = []
    strategy = reward_strategy or IndependentTaskReward()

    for worker_key, events in by_worker.items():
        prompt_text = _build_prompt_text(events)
        prompt_ids = tokenizer.encode(prompt_text) if prompt_text else []

        completion_ids: list[int] = []
        logprobs: list[float] = []
        env_mask: list[int] = []
        execution_ids: set[str] = set()

        for event in events:
            parsed = event.parsed_payload()
            event_type = event.event_type

            if event_type in ("system_prompt", "user_message"):
                # Prompt context — not part of the completion sequence
                execution_ids.add(str(event.task_execution_id))
                continue

            if event_type in ("assistant_text", "tool_call", "thinking"):
                # Model-generated tokens — env_mask = 1
                token_ids = _get_token_ids(parsed, tokenizer)
                token_logprobs = _get_logprobs(parsed, len(token_ids))
                completion_ids.extend(token_ids)
                logprobs.extend(token_logprobs)
                env_mask.extend([1] * len(token_ids))

            elif event_type == "tool_result":
                # Environment tokens — env_mask = 0
                assert isinstance(parsed, ToolResultPayload)
                result_tokens = tokenizer.encode(str(parsed.result))
                completion_ids.extend(result_tokens)
                logprobs.extend([0.0] * len(result_tokens))
                env_mask.extend([0] * len(result_tokens))

            execution_ids.add(str(event.task_execution_id))

        reward = strategy.compute(worker_key, execution_ids, eval_scores)

        trajectories.append(AgentTrajectory(
            agent_id=worker_key,
            prompt_ids=prompt_ids,
            completion_ids=completion_ids,
            logprobs=logprobs,
            env_mask=env_mask,
            reward=reward,
            turns=_count_turns(events),
        ))

    return trajectories


def _build_prompt_text(events: list[RunContextEvent]) -> str:
    """Concatenate system_prompt + user_message events for the first execution turn."""
    parts: list[str] = []
    for event in events:
        if event.event_type == "system_prompt":
            parsed = event.parsed_payload()
            assert isinstance(parsed, SystemPromptPayload)
            parts.append(parsed.text)
        elif event.event_type == "user_message":
            parsed = event.parsed_payload()
            assert isinstance(parsed, UserMessagePayload)
            parts.append(parsed.text)
        elif event.event_type in ("assistant_text", "tool_call", "thinking", "tool_result"):
            break  # Stop at first model output — prompt is everything before it
    return "\n\n".join(parts)


def _get_token_ids(parsed: ContextEventPayload, tokenizer: Tokenizer) -> list[int]:
    """Extract token IDs from a model-generated event payload.

    Uses turn_token_ids if present (vLLM path — turn-level flat list on the first
    event of each turn). Falls back to tokenising the text content (non-vLLM path).
    The fallback produces correct token counts but IDs won't match the model's
    original forward pass, which is acceptable for reward-only RL but not for
    importance sampling. See also the multi-event alignment note on _get_logprobs.
    """
    if isinstance(parsed, AssistantTextPayload):
        return parsed.turn_token_ids if parsed.turn_token_ids is not None else tokenizer.encode(parsed.text)
    if isinstance(parsed, ToolCallPayload):
        args_text = json.dumps(parsed.args)
        return parsed.turn_token_ids if parsed.turn_token_ids is not None else tokenizer.encode(args_text)
    if isinstance(parsed, ThinkingPayload):
        return parsed.turn_token_ids if parsed.turn_token_ids is not None else tokenizer.encode(parsed.text)
    raise ValueError(f"_get_token_ids called on non-model event: {type(parsed)}")


def _get_logprobs(parsed: ContextEventPayload, n_tokens: int) -> list[float]:
    """Extract per-token logprob scalars from turn_logprobs, padding with 0.0 if unavailable.

    NOTE: This slicing is only correct for single-event turns (text-only or tool-call-only).
    For multi-event turns (text + tool_call), the flat turn_logprobs list covers ALL tokens in
    generation order; slicing per-event misaligns the logprobs. The correct path for multi-event
    turns is to group by turn_id, collect all token_ids across the group, then align turn_logprobs
    once against the concatenated list. This is a Phase 1 implementation concern; the schema is
    correct. Until multi-event alignment is implemented, single-event turns are exact and
    multi-event turns fall back to partial logprob coverage or 0.0 padding.
    """
    lps: list[TokenLogprob] | None = getattr(parsed, "turn_logprobs", None)
    if lps is None:
        return [0.0] * n_tokens
    scalars = [lp.logprob for lp in lps]
    # Align length to n_tokens
    if len(scalars) < n_tokens:
        scalars.extend([0.0] * (n_tokens - len(scalars)))
    return scalars[:n_tokens]


def _count_turns(events: list[RunContextEvent]) -> int:
    """Count distinct generation turns (unique turn_ids across model-output events)."""
    seen: set[str] = set()
    for event in events:
        if event.event_type in ("assistant_text", "tool_call", "thinking"):
            parsed = event.parsed_payload()
            turn_id: str | None = getattr(parsed, "turn_id", None)
            if turn_id:
                seen.add(turn_id)
    return len(seen)
```

#### Key improvements over the old path

| | Old (`RunGenerationTurn`) | New (`RunContextEvent`) |
|---|---|---|
| `env_mask` | Inferred heuristically from tool call presence | Exact: derived from `event_type` |
| `token_ids` | Always re-tokenised from text (lossy) | Native from vLLM when available; text fallback otherwise |
| `logprobs` | From `logprobs_json` blob, manually aligned | Per-event typed field, aligned by `_get_logprobs` |
| Prompt | Passed in by caller as `prompt_text` | Reconstructed from `system_prompt` + `user_message` events |
| Thinking tokens | Dropped entirely | First-class `thinking` events, included in completion |

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

```python
# ergon_core/ergon_core/core/persistence/context/assembly.py

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart as PydanticSystemPromptPart,
    UserPromptPart as PydanticUserPromptPart,
    TextPart as PydanticTextPart,
    ToolCallPart as PydanticToolCallPart,
    ToolReturnPart as PydanticToolReturnPart,
    ThinkingPart as PydanticThinkingPart,
    ArgsDict,
    ModelMessage,
)
from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.persistence.context.event_payloads import (
    SystemPromptPayload,
    UserMessagePayload,
    AssistantTextPayload,
    ToolCallPayload,
    ToolResultPayload,
    ThinkingPayload,
)


def assemble_pydantic_ai_messages(events: list[RunContextEvent]) -> list[ModelMessage]:
    """Reconstruct the PydanticAI ModelRequest/ModelResponse sequence from stored events.

    Events must be pre-sorted by sequence (ascending) — matches get_for_execution output.

    Grouping rules:
    - system_prompt + user_message events → SystemPromptPart / UserPromptPart in the first ModelRequest
    - thinking / assistant_text / tool_call events → parts of the current ModelResponse
    - tool_result event → closes the current ModelResponse, opens a new ModelRequest with ToolReturnPart
    - trailing response (turn with no tool results) → flushed at end
    """
    messages: list[ModelMessage] = []
    current_request_parts: list = []
    current_response_parts: list = []

    for event in events:
        parsed = event.parsed_payload()

        if event.event_type == "system_prompt":
            assert isinstance(parsed, SystemPromptPayload)
            current_request_parts.append(PydanticSystemPromptPart(content=parsed.text))

        elif event.event_type == "user_message":
            assert isinstance(parsed, UserMessagePayload)
            current_request_parts.append(PydanticUserPromptPart(content=parsed.text))

        elif event.event_type in ("thinking", "assistant_text", "tool_call"):
            # First model-generated event of a turn: flush the pending request
            if current_request_parts and not current_response_parts:
                messages.append(ModelRequest(parts=current_request_parts))
                current_request_parts = []

            if event.event_type == "thinking":
                assert isinstance(parsed, ThinkingPayload)
                current_response_parts.append(PydanticThinkingPart(content=parsed.text))
            elif event.event_type == "assistant_text":
                assert isinstance(parsed, AssistantTextPayload)
                current_response_parts.append(PydanticTextPart(content=parsed.text))
            elif event.event_type == "tool_call":
                assert isinstance(parsed, ToolCallPayload)
                current_response_parts.append(PydanticToolCallPart(
                    tool_name=parsed.tool_name,
                    tool_call_id=parsed.tool_call_id,
                    args=ArgsDict(args_dict=parsed.args),
                ))

        elif event.event_type == "tool_result":
            assert isinstance(parsed, ToolResultPayload)
            # Close the current ModelResponse
            if current_response_parts:
                messages.append(ModelResponse(parts=current_response_parts))
                current_response_parts = []
            # Open a new ModelRequest with the tool return
            # str(parsed.result): worker JSON-serialises complex results before storage,
            # so the string representation is adequate for re-injection.
            current_request_parts.append(PydanticToolReturnPart(
                tool_call_id=parsed.tool_call_id,
                tool_name=parsed.tool_name,
                content=str(parsed.result),
            ))

    # Flush any trailing response (final turn produced no tool results)
    if current_response_parts:
        messages.append(ModelResponse(parts=current_response_parts))

    return messages
```

`ArgsDict` is `pydantic_ai.messages.ArgsDict`. Confirm exact import path during Phase 1 implementation — PydanticAI's internal message module paths can shift between minor versions.

### 5.3 Dashboard Streaming

The emitter and Inngest function are fully specced in §4.5. This section covers the frontend state model, live reducer, and UI components.

#### TypeScript types

```typescript
// ergon-dashboard/src/lib/contracts/contextEvents.ts

export type ContextEventType =
  | "system_prompt"
  | "user_message"
  | "assistant_text"
  | "tool_call"
  | "tool_result"
  | "thinking";

// Discriminated union — mirrors Python ContextEventPayload
export type ContextEventPayload =
  | { event_type: "system_prompt"; text: string }
  | { event_type: "user_message"; text: string; from_worker_key: string | null }
  | { event_type: "assistant_text"; text: string; turn_id: string; turn_logprobs: TokenLogprob[] | null }
  | { event_type: "tool_call"; tool_call_id: string; tool_name: string; args: Record<string, unknown>; turn_id: string; turn_logprobs: TokenLogprob[] | null }
  | { event_type: "tool_result"; tool_call_id: string; tool_name: string; result: unknown; is_error: boolean }
  | { event_type: "thinking"; text: string; turn_id: string; turn_logprobs: TokenLogprob[] | null };

export interface TokenLogprob {
  token: string;
  logprob: number;
}

export interface ContextEventState {
  id: string;
  taskExecutionId: string;
  taskNodeId: string;
  workerBindingKey: string;
  sequence: number;
  eventType: ContextEventType;
  payload: ContextEventPayload;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
}
```

Zod schema in `ergon-dashboard/src/lib/contracts/events.ts` must match the `DashboardContextEventEvent` Python contract field-for-field.

#### Store changes

`WorkflowRunState` replaces `generationTurns: GenerationTurnState[]` with a per-task map:

```typescript
// ergon-dashboard/src/lib/state/store.ts

export interface WorkflowRunState {
  // ... existing fields unchanged ...

  // Replaces: generationTurns: GenerationTurnState[]
  contextEventsByTask: Map<string, ContextEventState[]>;
  // keyed by task_node_id (string UUID); events are in sequence order within each key
}
```

New store method:

```typescript
addContextEvent(runId: string, taskNodeId: string, event: ContextEventState): void {
  const run = this.runs.get(runId);
  if (!run) return;
  const existing = run.contextEventsByTask.get(taskNodeId) ?? [];
  // Insert in sequence order — live events typically arrive in order,
  // but guard against redelivery by deduplicating on id
  if (existing.some(e => e.id === event.id)) return;
  run.contextEventsByTask.set(taskNodeId, [...existing, event].sort((a, b) => a.sequence - b.sequence));
}
```

#### Client socket handler

```typescript
socket.on("context:event", ({ runId, taskNodeId, event }) => {
  setRunState(prev => {
    const existing = prev.contextEventsByTask.get(taskNodeId) ?? [];
    if (existing.some(e => e.id === event.id)) return prev; // deduplicate
    const updated = new Map(prev.contextEventsByTask);
    updated.set(taskNodeId, [...existing, event].sort((a, b) => a.sequence - b.sequence));
    return { ...prev, contextEventsByTask: updated };
  });
});
```

#### Snapshot hydration

On initial load, `build_run_snapshot` returns `context_events_by_task` (see §5.4). The client hydrates `contextEventsByTask` from this field directly — the structure is identical.

#### UI components

```
ergon-dashboard/src/features/graph/components/
  ContextEventLog.tsx          — container: takes ContextEventState[], renders in order
  ContextEventEntry.tsx        — dispatcher: switches on eventType, renders child
  events/
    SystemPromptEvent.tsx      — grey collapsed header; expand to show full text
    UserMessageEvent.tsx       — indigo chat bubble; shows from_worker_key label if set
    ThinkingEvent.tsx          — purple italicised block; collapsed by default (can be long)
    AssistantTextEvent.tsx     — white assistant bubble; plain text render
    ToolCallEvent.tsx          — amber block; tool name as header, args as collapsible JSON
    ToolResultEvent.tsx        — green block (red if is_error); result as collapsible JSON
```

**`ContextEventLog`** — receives all `ContextEventState[]` for a task node. Renders events in `sequence` order. Each event is separated by a thin timeline connector.

**`ContextEventEntry`** — pure dispatcher:
```tsx
function ContextEventEntry({ event }: { event: ContextEventState }) {
  switch (event.eventType) {
    case "system_prompt":   return <SystemPromptEvent payload={event.payload} />;
    case "user_message":    return <UserMessageEvent payload={event.payload} />;
    case "thinking":        return <ThinkingEvent payload={event.payload} timestamps={event} />;
    case "assistant_text":  return <AssistantTextEvent payload={event.payload} timestamps={event} />;
    case "tool_call":       return <ToolCallEvent payload={event.payload} timestamps={event} />;
    case "tool_result":     return <ToolResultEvent payload={event.payload} />;
  }
}
```

**Event-type component contracts:**

| Component | Key props | Default collapsed? | Notes |
|---|---|---|---|
| `SystemPromptEvent` | `text` | Yes | Full text in expand |
| `UserMessageEvent` | `text`, `from_worker_key` | No | Show delegation source label when set |
| `ThinkingEvent` | `text`, `startedAt`, `completedAt` | Yes | Duration badge; italic text |
| `AssistantTextEvent` | `text`, `startedAt`, `completedAt` | No | Duration badge |
| `ToolCallEvent` | `tool_name`, `args`, `tool_call_id`, timing | Yes (args) | Header shows tool name; args as syntax-highlighted JSON |
| `ToolResultEvent` | `tool_name`, `result`, `is_error` | Yes (result) | Red border if `is_error`; result as JSON |

`ToolCallEvent` and `ToolResultEvent` should be visually linked by `tool_call_id` — when expanded, the tool result shows a back-reference to the call that produced it (and vice versa). Implementation can use a subtle connector line or matching colour stripe.

### 5.4 REST Snapshot

`GET /runs/{run_id}` (`build_run_snapshot`) currently loads `RunGenerationTurn` rows and groups by `execution_task_map` into `generation_turns_by_task`. This is replaced by loading `RunContextEvent` rows grouped by execution:

```python
context_events_stmt = (
    select(RunContextEvent)
    .where(RunContextEvent.run_id == run_id)
    .order_by(RunContextEvent.task_execution_id, RunContextEvent.sequence)
)
context_events = list(session.exec(context_events_stmt).all())

context_events_by_task: dict[str, list["RunContextEventDto"]] = defaultdict(list)
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

```python
# ergon_core/ergon_core/core/api/schemas.py

class RunContextEventDto(BaseModel):
    id: str
    task_execution_id: str
    sequence: int
    event_type: str             # ContextEventType — kept as plain str for forward compat
    payload: dict[str, Any]
    created_at: str             # ISO 8601
    started_at: str | None = None
    completed_at: str | None = None
```

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
    + ModelRequestPart union (SystemPromptPart | UserPromptPart | ToolReturnPart)
    + ModelResponsePart union (TextPart | ToolCallPart | ThinkingPart)
    ~ GenerationTurn: messages_in, response_parts, tool_results (typed); drop raw_response, prompt_text

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

ergon-dashboard/src/features/graph/components/
    + ContextEventLog.tsx
    + ContextEventEntry.tsx
    + events/SystemPromptEvent.tsx
    + events/UserMessageEvent.tsx
    + events/ThinkingEvent.tsx
    + events/AssistantTextEvent.tsx
    + events/ToolCallEvent.tsx
    + events/ToolResultEvent.tsx

ergon-dashboard/src/lib/contracts/
    + contextEvents.ts             — ContextEventState, ContextEventPayload, ContextEventType TS types
    ~ events.ts                    — + Zod schema for DashboardContextEventEvent

ergon-dashboard/src/lib/state/store.ts
    ~ WorkflowRunState: generationTurns → contextEventsByTask: Map<string, ContextEventState[]>
    + addContextEvent() store method

ergon-dashboard/src/lib/socket/types.ts
    + "context:event" to ServerToClientEvents

ergon-dashboard/src/inngest/functions/
    + onContextEvent.ts            — Inngest handler: parses event, calls store + broadcast
```

### Deleted as part of this work

These are removed in Phase 3 once all readers have been migrated. They are not deleted in Phase 1 or 2.

```
ergon_core/ergon_core/core/persistence/telemetry/models.py
    DELETE  class RunGenerationTurn  (all fields + parsed_tool_calls / parsed_tool_results /
                                      parsed_token_ids / parsed_logprobs / _parse_optional_list /
                                      _validate_json_columns methods)
    KEEP    ExecutionOutcome type alias  (still used by RunTaskExecution; no longer used by RunContextEvent)
    KEEP    all other model classes

ergon_core/ergon_core/core/persistence/telemetry/repositories.py
    DELETE  class GenerationTurnRepository  (entire class: __init__, add_listener,
                                             persist_single, persist_turns,
                                             get_for_execution, get_for_run,
                                             mark_execution_outcome)
    KEEP    TelemetryRepository  (remove only the GenerationTurnRepository call site inside it)

ergon_core/ergon_core/core/dashboard/emitter.py
    DELETE  on_turn_persisted() method
    DELETE  import of RunGenerationTurn
    KEEP    everything else

ergon_core/ergon_core/core/dashboard/event_contracts.py
    DELETE  DashboardGenerationTurnEvent class
    KEEP    all other contracts

ergon_core/ergon_core/core/api/runs.py
    DELETE  GET /runs/{run_id}/generations endpoint
    DELETE  generation_turns_by_task field from RunSnapshotDto
    KEEP    context_events_by_task (added in Phase 2)
```

The `run_generation_turns` table is **never dropped** — historical data lives there. The ORM model class is removed but the table is left in place.

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

**Token IDs from vLLM.** `turn_token_ids` (on the first model-output event of each turn, alongside `turn_logprobs`) will remain `None` until the vLLM provider is updated to extract token IDs from `provider_details`. PydanticAI currently exposes logprobs via `provider_details["logprobs"]` but does not surface the corresponding token ID integers. The schema and `GenerationTurn` DTO are ready; populating the field requires a provider-side improvement and does not block the schema migration.

**Logprobs for tool call argument tokens.** `turn_logprobs` stores the flat `choice.logprobs.content` list from vLLM, and is held on the first model-output event of each turn (grouped by `turn_id`). Whether vLLM includes tool call argument tokens in `logprobs.content` is empirically unknown — vLLM generates everything in one forward pass then splits, so it *may* include them. A spike (`scripts/spike_logprob_splitting.py`) has been written; run it with `VLLM_BASE_URL` set against a live vLLM instance to get a definitive answer. Until the spike runs, `turn_logprobs` is stored as `None`; populate once the live probe confirms coverage.

**RL logprob alignment for multi-event turns.** The current `_get_logprobs` helper slices `turn_logprobs` to `n_tokens` per event, which is correct only for single-event turns. For turns that produce multiple model-output events (e.g., ThinkingPart + TextPart + ToolCallPart), the correct approach is to group events by `turn_id`, accumulate all `token_ids` across the group, then align `turn_logprobs` once against the concatenated token sequence. This avoids misaligning text-token logprobs onto tool-call-token positions. Implement `turn_id`-grouped alignment in Phase 1; it is required for importance-sampling–based RL. Reward-only RL is unaffected (rewards depend on outcomes, not individual token logprobs).

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
