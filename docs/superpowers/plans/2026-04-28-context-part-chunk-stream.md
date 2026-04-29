# Context Part Chunk Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the parallel `GenerationTurn` and context-event payload model with one canonical context-part stream emitted by workers and enriched by core before persistence.

**Architecture:** Define a single discriminated `ContextPart` union for things that appear in an LLM context/action stream: system prompts, user messages, assistant text, tool calls, tool results, and thinking. Workers yield `ContextPartChunk` values containing a `part` plus optional token metadata; core normalizes and enriches those chunks into persisted `RunContextEvent` rows with sequence, turn id, timestamps, worker key, and run/execution ids. Keep database rows flat enough for SQLModel/JSONB, but make API, dashboard, replay, and RL consumers use typed chunk/log schemas instead of duplicate payload unions. This is a clean-break migration: old `*Payload`, `GenerationTurn`, request/response part aliases, and old discriminator names must be gone by the final task.

**Tech Stack:** Python 3.13, Pydantic v2 discriminated unions, SQLModel JSON columns, pytest, existing Ergon worker/runtime/persistence packages.

---

## Source Of Truth

The canonical worker-facing stream type should live in `ergon_core.core.generation` or a renamed module such as `ergon_core.core.context_stream`. To avoid a large import churn in the first slice, start in `ergon_core.core.generation`.

Use these names:

```python
ContextPart
ContextPartChunk
ContextPartChunkLog
WorkerYield
```

`ContextPart` is the only union for LLM context/action parts.

`ContextPartChunk` is the de facto worker generator type.

`ContextPartChunkLog` is the core-enriched durable event shape. It is not the database ORM model; it is the typed payload/envelope used when projecting a stored `RunContextEvent`.

`RunContextEvent` remains the SQLModel row with JSON storage and relational ids.

---

## Change Tree

```text
ergon/
  ergon_core/
    ergon_core/
      core/
        generation.py                                      # modify: canonical ContextPart/ContextPartChunk/ContextPartChunkLog
        api/
          schemas.py                                      # modify: typed REST context event payloads
          runs.py                                         # modify: project parsed chunk logs
        dashboard/
          event_contracts.py                              # modify: dashboard context event payload uses chunk log
          emitter.py                                      # modify: emit parsed chunk logs
        persistence/
          context/
            event_payloads.py                             # modify/delete duplicate payload union; no final old aliases
            models.py                                     # modify: validate JSON as ContextPartChunkLog
            repository.py                                 # modify: add persist_chunk enrichment; later delete persist_turn
        rl/
          extraction.py                                   # modify: consume chunk-log parts
        runtime/
          services/
            task_execution_service.py                     # modify: persist worker chunks instead of turns
      test_support/
        smoke_fixtures/
          smoke_base/
            leaf_base.py                                  # modify: yield ContextPartChunk
            recursive.py                                  # modify: yield ContextPartChunk
            worker_base.py                                # modify: yield ContextPartChunk
    tests/
      unit/
        architecture/
          test_core_schema_sources.py                     # modify: guard single context part union
          test_model_field_descriptions.py                # modify: check chunk-log field descriptions
        builtins/
          common/
            test_transcript_adapters.py                   # modify: assert chunk extraction/replay
        dashboard/
          test_event_contract_types.py                    # modify: assert typed chunk-log dashboard payload
        persistence/
          test_context_event_repository.py                # modify: persist_chunk tests
        state/
          test_context_part_stream.py                     # add: canonical part/chunk serialization tests
          test_context_assembly.py                        # modify: replay from ContextPartChunkLog
          test_generation_turn_build.py                   # modify/delete after GenerationTurn compatibility removal
        workers/
          test_react_worker_contract.py                   # modify: worker yields chunks
  ergon_builtins/
    ergon_builtins/
      common/
        llm_context/
          adapters/
            pydantic_ai.py                                # modify: build_chunks/build_new_chunks and replay chunk logs
      workers/
        baselines/
          react_worker.py                                 # modify: inspect ContextPartChunkLog.part
          training_stub_worker.py                         # modify: yield ContextPartChunk
        research_rubrics/
          researcher_worker.py                            # modify if still yielding GenerationTurn
          workflow_cli_react_worker.py                    # modify if still yielding GenerationTurn
```

---

## File Structure

**Modify:**
- `ergon_core/ergon_core/core/generation.py` — replace request/response-specific part model as the canonical context stream model while preserving temporary aliases during migration.
- `ergon_core/ergon_core/core/persistence/context/event_payloads.py` — replace the duplicate payload union with canonical context-event type exports only; do not keep old payload aliases in the final state.
- `ergon_core/ergon_core/core/persistence/context/models.py` — validate stored JSON as `ContextPartChunkLog` or the log payload shape.
- `ergon_core/ergon_core/core/persistence/context/repository.py` — replace `persist_turn()` decomposition with `persist_chunk()` enrichment; keep a temporary `persist_turn()` adapter if needed for staged migration.
- `ergon_core/ergon_core/core/api/schemas.py` — type REST context-event DTOs with `ContextPartChunkLog` instead of `dict[str, Any]`.
- `ergon_core/ergon_core/core/api/runs.py` — project stored context events through typed log validation.
- `ergon_core/ergon_core/core/dashboard/event_contracts.py` — use the same typed log schema as REST for context events.
- `ergon_core/ergon_core/core/dashboard/emitter.py` — emit typed enriched context logs.
- `ergon_core/ergon_core/core/rl/extraction.py` — read `event.part` instead of payload-specific classes.
- `ergon_builtins/ergon_builtins/common/llm_context/adapters/pydantic_ai.py` — convert PydanticAI messages into `ContextPartChunk` streams and replay logs back into PydanticAI messages.
- `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py` — consume the new typed context stream.
- `ergon_builtins/ergon_builtins/workers/baselines/training_stub_worker.py` — yield chunks instead of `GenerationTurn`.
- `ergon_core/ergon_core/test_support/smoke_fixtures/smoke_base/*.py` — yield chunks in smoke workers.

**Tests:**
- `tests/unit/state/test_context_part_stream.py` — new focused tests for canonical union and chunk serialization.
- `tests/unit/persistence/test_context_event_repository.py` — rewrite around `persist_chunk()`.
- `tests/unit/builtins/common/test_transcript_adapters.py` — update PydanticAI adapter tests to assert chunk/log behavior.
- `tests/unit/state/test_context_assembly.py` — update replay tests around `ContextPartChunkLog`.
- `tests/unit/architecture/test_core_schema_sources.py` — add architecture guard against reintroducing duplicate context payload unions.
- Existing focused tests: `tests/unit/state/test_generation_turn_build.py`, `tests/unit/workers/test_react_worker_contract.py`, `tests/unit/dashboard/test_event_contract_types.py`, `tests/unit/architecture/test_model_field_descriptions.py`.

---

### Task 1: Introduce Canonical Context Parts

**Files:**
- Modify: `ergon_core/ergon_core/core/generation.py`
- Create: `tests/unit/state/test_context_part_stream.py`

- [ ] **Step 1: Write failing tests for the canonical part union**

Create `tests/unit/state/test_context_part_stream.py` with:

```python
from pydantic import TypeAdapter

from ergon_core.core.generation import (
    AssistantTextPart,
    ContextPart,
    ContextPartChunk,
    ContextPartChunkLog,
    SystemPromptPart,
    ThinkingPart,
    TokenLogprob,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)


def test_context_part_discriminates_all_part_kinds() -> None:
    adapter = TypeAdapter(ContextPart)

    cases = [
        SystemPromptPart(content="sys"),
        UserMessagePart(content="hi"),
        AssistantTextPart(content="hello"),
        ToolCallPart(tool_call_id="call-1", tool_name="search", args={"q": "x"}),
        ToolResultPart(tool_call_id="call-1", tool_name="search", content="ok"),
        ThinkingPart(content="reasoning"),
    ]

    for part in cases:
        dumped = part.model_dump(mode="json")
        parsed = adapter.validate_python(dumped)
        assert parsed == part


def test_context_part_chunk_wraps_part_with_optional_token_metadata() -> None:
    chunk = ContextPartChunk(
        part=AssistantTextPart(content="answer"),
        token_ids=[1, 2],
        logprobs=[TokenLogprob(token="answer", logprob=-0.1)],
    )

    dumped = chunk.model_dump(mode="json")

    assert dumped["part"]["part_kind"] == "assistant_text"
    assert dumped["token_ids"] == [1, 2]
    assert dumped["logprobs"][0]["token"] == "answer"


def test_context_part_chunk_log_adds_core_enrichment() -> None:
    log = ContextPartChunkLog(
        part=ThinkingPart(content="hmm"),
        sequence=7,
        worker_binding_key="researcher",
        turn_id="turn-1",
        token_ids=None,
        logprobs=None,
    )

    dumped = log.model_dump(mode="json")

    assert dumped["part"]["part_kind"] == "thinking"
    assert dumped["sequence"] == 7
    assert dumped["worker_binding_key"] == "researcher"
    assert dumped["turn_id"] == "turn-1"
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
pytest tests/unit/state/test_context_part_stream.py -v
```

Expected: FAIL because `AssistantTextPart`, `UserMessagePart`, `ToolResultPart`, `ContextPartChunk`, and `ContextPartChunkLog` do not exist yet.

- [ ] **Step 3: Implement canonical context stream types**

Modify `ergon_core/ergon_core/core/generation.py` to define the canonical names. This task may keep request/response subset aliases only if needed to keep the next migration task small; those aliases must be deleted in Task 7 before the plan is complete.

```python
"""Core model context-stream types.

These types are used by worker APIs, transcript adapters, persistence, replay,
and RL extraction. Keep them in core so persistence can import them without
loading ``ergon_core.api``.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from ergon_core.core.json_types import JsonObject
from pydantic import BaseModel, Field


class TokenLogprob(BaseModel):
    """Per-token log probability from the serving backend."""

    model_config = {"frozen": True}

    token: str
    logprob: float
    top_logprobs: list[JsonObject] = Field(default_factory=list)


class SystemPromptPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["system_prompt"] = "system_prompt"
    content: str


class UserMessagePart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["user_message"] = "user_message"
    content: str


class AssistantTextPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["assistant_text"] = "assistant_text"
    content: str


class ToolCallPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["tool_call"] = "tool_call"
    tool_name: str
    tool_call_id: str
    args: dict[str, Any]  # slopcop: ignore[no-typing-any]


class ToolResultPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False


class ThinkingPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["thinking"] = "thinking"
    content: str


ContextPart = Annotated[
    SystemPromptPart
    | UserMessagePart
    | AssistantTextPart
    | ToolCallPart
    | ToolResultPart
    | ThinkingPart,
    Field(discriminator="part_kind"),
]


class ContextPartChunk(BaseModel):
    """One worker-emitted context/action stream item.

    Core adds run/execution/sequence/timing metadata before persistence.
    """

    model_config = {"frozen": True}

    part: ContextPart
    token_ids: list[int] | None = None
    logprobs: list[TokenLogprob] | None = None


class ContextPartChunkLog(ContextPartChunk):
    """Core-enriched context stream item suitable for API/dashboard projection."""

    sequence: int
    worker_binding_key: str
    turn_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    policy_version: str | None = None


WorkerYield = ContextPartChunk

# Temporary migration-only aliases. Task 7 must remove these before completion.
UserPromptPart = UserMessagePart
TextPart = AssistantTextPart
ToolReturnPart = ToolResultPart

ModelRequestPart = Annotated[
    SystemPromptPart | UserMessagePart | ToolResultPart,
    Field(discriminator="part_kind"),
]
ModelResponsePart = Annotated[
    AssistantTextPart | ToolCallPart | ThinkingPart,
    Field(discriminator="part_kind"),
]


class GenerationTurn(BaseModel):
    """Deprecated: use ContextPartChunk streams instead."""

    model_config = {"frozen": True}

    messages_in: list[ModelRequestPart] = Field(default_factory=list)
    response_parts: list[ModelResponsePart] = Field(default_factory=list)
    tool_results: list[ToolResultPart] = Field(default_factory=list)
    turn_token_ids: list[int] | None = None
    turn_logprobs: list[TokenLogprob] | None = None
    policy_version: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
pytest tests/unit/state/test_context_part_stream.py -v
```

Expected: PASS.

- [ ] **Step 5: Run generation-related tests to expose compatibility fallout**

Run:

```bash
pytest tests/unit/state/test_generation_turn_build.py tests/unit/builtins/common/test_transcript_adapters.py -v
```

Expected: likely FAIL because existing tests assert old discriminator values such as `tool-call` and old constructor names such as `ToolReturnPart`.

---

### Task 2: Replace Payload Union With Enriched Chunk Log

**Files:**
- Modify: `ergon_core/ergon_core/core/persistence/context/event_payloads.py`
- Modify: `ergon_core/ergon_core/core/persistence/context/models.py`
- Modify: `tests/unit/architecture/test_model_field_descriptions.py`

- [ ] **Step 1: Write failing compatibility tests for typed log payload validation**

Update or add tests that assert the context event row validates its JSON as `ContextPartChunkLog`:

```python
from ergon_core.core.generation import AssistantTextPart, ContextPartChunkLog
from ergon_core.core.persistence.context.models import RunContextEvent


def test_run_context_event_parsed_payload_is_context_part_chunk_log() -> None:
    log = ContextPartChunkLog(
        part=AssistantTextPart(content="hello"),
        sequence=3,
        worker_binding_key="worker-a",
        turn_id="turn-1",
    )
    event = RunContextEvent(
        run_id="00000000-0000-0000-0000-000000000001",
        task_execution_id="00000000-0000-0000-0000-000000000002",
        worker_binding_key="worker-a",
        sequence=3,
        event_type="assistant_text",
        payload=log.model_dump(mode="json"),
    )

    parsed = event.parsed_payload()

    assert isinstance(parsed, ContextPartChunkLog)
    assert parsed.part == AssistantTextPart(content="hello")
```

If UUID strings are not accepted by SQLModel in this test, use `uuid.UUID(...)` values instead.

- [ ] **Step 2: Run the failing test**

Run:

```bash
pytest tests/unit/persistence/test_context_event_repository.py::test_run_context_event_parsed_payload_is_context_part_chunk_log -v
```

Expected: FAIL until `RunContextEvent.parsed_payload()` validates the new log shape.

- [ ] **Step 3: Collapse `event_payloads.py` into canonical exports**

Modify `ergon_core/ergon_core/core/persistence/context/event_payloads.py` so the canonical payload is `ContextPartChunkLog`. Do not define `SystemPromptPayload`, `UserMessagePayload`, `AssistantTextPayload`, `ToolCallPayload`, `ToolResultPayload`, or `ThinkingPayload`; callers must migrate to `ContextPartChunkLog.part` and the canonical part classes.

```python
"""Typed context event payload exports.

The canonical context payload is an enriched ContextPartChunkLog. Event-specific
payload classes were removed in favor of ContextPartChunkLog.part.
"""

from typing import Literal

from ergon_core.core.generation import (
    ContextPart,
    ContextPartChunk,
    ContextPartChunkLog,
)

ContextEventType = Literal[
    "system_prompt",
    "user_message",
    "assistant_text",
    "tool_call",
    "tool_result",
    "thinking",
]

ContextEventPayload = ContextPartChunkLog
```

- [ ] **Step 4: Update `RunContextEvent` validation**

Modify `ergon_core/ergon_core/core/persistence/context/models.py`:

```python
from ergon_core.core.generation import ContextPartChunkLog
from pydantic import TypeAdapter

_PAYLOAD_ADAPTER: TypeAdapter[ContextPartChunkLog] = TypeAdapter(ContextPartChunkLog)


class RunContextEvent(SQLModel, table=True):
    ...

    def parsed_payload(self) -> ContextPartChunkLog:
        return _PAYLOAD_ADAPTER.validate_python(self.payload)
```

Keep `event_type: str` and `payload: dict[str, Any]` on the SQLModel row because the database stores JSON and indexes `event_type`.

- [ ] **Step 5: Replace field-description architecture tests**

Update `tests/unit/architecture/test_model_field_descriptions.py` to check descriptions on `ContextPartChunkLog` if the project requires descriptions for public fields. Do not keep tests against the old payload classes once they are aliases.

- [ ] **Step 6: Run focused tests**

Run:

```bash
pytest tests/unit/persistence/test_context_event_repository.py tests/unit/architecture/test_model_field_descriptions.py -v
```

Expected: repository tests still fail until Task 3 replaces `persist_turn()` behavior.

---

### Task 3: Persist Worker Chunks With Core Enrichment

**Files:**
- Modify: `ergon_core/ergon_core/core/persistence/context/repository.py`
- Modify: `tests/unit/persistence/test_context_event_repository.py`

- [ ] **Step 1: Write repository tests for `persist_chunk()`**

Replace turn-oriented tests with chunk-oriented tests:

```python
from uuid import uuid4

from ergon_core.core.generation import (
    AssistantTextPart,
    ContextPartChunk,
    ThinkingPart,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)


async def test_persist_chunk_records_prompt_and_model_output_in_order(session):
    repo = ContextEventRepository()
    run_id = uuid4()
    execution_id = uuid4()

    await repo.persist_chunk(
        session,
        run_id=run_id,
        execution_id=execution_id,
        worker_binding_key="worker-a",
        chunk=ContextPartChunk(part=UserMessagePart(content="question")),
    )
    await repo.persist_chunk(
        session,
        run_id=run_id,
        execution_id=execution_id,
        worker_binding_key="worker-a",
        chunk=ContextPartChunk(part=ThinkingPart(content="think")),
    )
    await repo.persist_chunk(
        session,
        run_id=run_id,
        execution_id=execution_id,
        worker_binding_key="worker-a",
        chunk=ContextPartChunk(part=AssistantTextPart(content="answer")),
    )

    events = repo.get_for_execution(session, execution_id)

    assert [event.sequence for event in events] == [0, 1, 2]
    assert [event.event_type for event in events] == [
        "user_message",
        "thinking",
        "assistant_text",
    ]
    assert events[1].parsed_payload().turn_id == events[2].parsed_payload().turn_id


async def test_persist_chunk_tool_result_closes_current_turn(session):
    repo = ContextEventRepository()
    run_id = uuid4()
    execution_id = uuid4()

    await repo.persist_chunk(
        session,
        run_id=run_id,
        execution_id=execution_id,
        worker_binding_key="worker-a",
        chunk=ContextPartChunk(
            part=ToolCallPart(tool_call_id="call-1", tool_name="search", args={"q": "x"})
        ),
    )
    await repo.persist_chunk(
        session,
        run_id=run_id,
        execution_id=execution_id,
        worker_binding_key="worker-a",
        chunk=ContextPartChunk(
            part=ToolResultPart(tool_call_id="call-1", tool_name="search", content="ok")
        ),
    )

    events = repo.get_for_execution(session, execution_id)

    assert [event.event_type for event in events] == ["tool_call", "tool_result"]
    assert events[0].parsed_payload().turn_id is not None
    assert events[1].parsed_payload().turn_id is None
```

Adjust fixture names to match the existing `test_context_event_repository.py` session fixture.

- [ ] **Step 2: Run repository tests to verify failure**

Run:

```bash
pytest tests/unit/persistence/test_context_event_repository.py -v
```

Expected: FAIL because `persist_chunk()` does not exist.

- [ ] **Step 3: Implement event type derivation**

In `ergon_core/ergon_core/core/persistence/context/repository.py`, add:

```python
from ergon_core.core.generation import (
    AssistantTextPart,
    ContextPartChunk,
    ContextPartChunkLog,
    SystemPromptPart,
    ThinkingPart,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)


def _event_type_for_part(part: ContextPart) -> str:
    return part.part_kind
```

If type checkers object to `ContextPart` as an `Annotated` alias in the helper signature, use the explicit union type or accept `object` and narrow via `isinstance`.

- [ ] **Step 4: Implement turn-id state machine**

Add private state to the repository:

```python
def __init__(self) -> None:
    self._listeners: list[Callable[[RunContextEvent], Awaitable[None]]] = []
    self._sequence_counters: dict[UUID, int] = {}
    self._active_turn_ids: dict[UUID, str] = {}
```

Add helpers:

```python
def _turn_id_for_chunk(self, execution_id: UUID, chunk: ContextPartChunk) -> str | None:
    part = chunk.part
    if isinstance(part, (AssistantTextPart, ThinkingPart, ToolCallPart)):
        turn_id = self._active_turn_ids.get(execution_id)
        if turn_id is None:
            turn_id = str(uuid4())
            self._active_turn_ids[execution_id] = turn_id
        return turn_id
    if isinstance(part, ToolResultPart):
        self._active_turn_ids.pop(execution_id, None)
        return None
    if isinstance(part, (SystemPromptPart, UserMessagePart)):
        return None
    return None
```

This deliberately associates `thinking`, `assistant_text`, and `tool_call` chunks emitted contiguously with the same model-output turn. A following `tool_result` closes the active turn.

- [ ] **Step 5: Implement `persist_chunk()`**

Add:

```python
async def persist_chunk(
    self,
    session: Session,
    *,
    run_id: UUID,
    execution_id: UUID,
    worker_binding_key: str,
    chunk: ContextPartChunk,
) -> RunContextEvent:
    seq = self._next_sequence(execution_id)
    turn_id = self._turn_id_for_chunk(execution_id, chunk)
    event_type = chunk.part.part_kind
    now = datetime.now(UTC)
    payload = ContextPartChunkLog(
        part=chunk.part,
        token_ids=chunk.token_ids,
        logprobs=chunk.logprobs,
        sequence=seq,
        worker_binding_key=worker_binding_key,
        turn_id=turn_id,
        started_at=now,
        completed_at=now,
    )
    event = self._make_event(
        run_id,
        execution_id,
        worker_binding_key,
        seq,
        payload,
        started_at=payload.started_at,
        completed_at=payload.completed_at,
        policy_version=payload.policy_version,
    )
    self._sequence_counters[execution_id] = seq + 1

    session.add(event)
    session.commit()

    for listener in self._listeners:
        try:
            await listener(event)
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Context event listener failed", exc_info=True)

    return event
```

Update `_make_event()` to accept `payload: ContextPartChunkLog` and store `payload.model_dump(mode="json")`.

- [ ] **Step 6: Keep a temporary `persist_turn()` adapter**

During migration only, keep `persist_turn()` by decomposing old `GenerationTurn` into chunks:

```python
async def persist_turn(..., turn: GenerationTurn) -> list[RunContextEvent]:
    events: list[RunContextEvent] = []
    for part in turn.messages_in:
        events.append(await self.persist_chunk(..., chunk=ContextPartChunk(part=part)))
    for part in turn.response_parts:
        events.append(
            await self.persist_chunk(
                ...,
                chunk=ContextPartChunk(
                    part=part,
                    token_ids=turn.turn_token_ids,
                    logprobs=turn.turn_logprobs,
                ),
            )
        )
    for part in turn.tool_results:
        events.append(await self.persist_chunk(..., chunk=ContextPartChunk(part=part)))
    return events
```

This keeps old workers running while the execution service migrates to chunks.

- [ ] **Step 7: Run persistence tests**

Run:

```bash
pytest tests/unit/persistence/test_context_event_repository.py -v
```

Expected: PASS after updating any old assertions to inspect `event.parsed_payload().part`.

---

### Task 4: Migrate PydanticAI Adapter To Chunk Streams

**Files:**
- Modify: `ergon_builtins/ergon_builtins/common/llm_context/adapters/pydantic_ai.py`
- Modify: `tests/unit/builtins/common/test_transcript_adapters.py`
- Modify: `tests/unit/state/test_generation_turn_build.py`
- Modify: `tests/unit/state/test_context_assembly.py`

- [ ] **Step 1: Write adapter tests for chunk extraction**

Update `tests/unit/builtins/common/test_transcript_adapters.py` so PydanticAI transcript extraction returns chunks:

```python
def test_text_and_thinking_are_context_part_chunks() -> None:
    adapter = PydanticAITranscriptAdapter()

    chunks = adapter.build_chunks(
        [
            ModelRequest(parts=[UserPromptPart(content="hard question")]),
            ModelResponse(
                parts=[
                    ThinkingPart(content="let me reason"),
                    TextPart(content="answer"),
                ]
            ),
        ]
    )

    assert [chunk.part.part_kind for chunk in chunks] == [
        "user_message",
        "thinking",
        "assistant_text",
    ]
```

Add a tool-call/tool-result test:

```python
def test_tool_call_and_return_become_context_part_chunks() -> None:
    adapter = PydanticAITranscriptAdapter()

    chunks = adapter.build_chunks(
        [
            ModelRequest(parts=[UserPromptPart(content="search")]),
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="search",
                        tool_call_id="call-1",
                        args={"query": "ergon"},
                    )
                ]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="search",
                        tool_call_id="call-1",
                        content={"result": "found"},
                    )
                ]
            ),
        ]
    )

    assert [chunk.part.part_kind for chunk in chunks] == [
        "user_message",
        "tool_call",
        "tool_result",
    ]
```

- [ ] **Step 2: Run adapter tests to verify failure**

Run:

```bash
pytest tests/unit/builtins/common/test_transcript_adapters.py -v
```

Expected: FAIL because `build_chunks()` does not exist.

- [ ] **Step 3: Implement `build_chunks()` and `build_new_chunks()`**

In `ergon_builtins/ergon_builtins/common/llm_context/adapters/pydantic_ai.py`, add methods parallel to the existing turn methods:

```python
def build_chunks(
    self,
    transcript: list[ModelMessage],
    *,
    flush_pending: bool = True,
) -> list[ContextPartChunk]:
    return _build_chunks_from_transcript(transcript, flush_pending=flush_pending)


def build_new_chunks(
    self,
    transcript: list[ModelMessage],
    cursor: TranscriptTurnCursor,
    *,
    flush_pending: bool = False,
) -> list[ContextPartChunk]:
    chunks = _build_chunks_from_transcript(transcript, flush_pending=flush_pending)
    new_chunks = chunks[cursor.emitted_turn_count :]
    cursor.emitted_turn_count = len(chunks)
    return new_chunks
```

Rename `TranscriptTurnCursor.emitted_turn_count` to `emitted_chunk_count` only if the migration can update all callers in one task. Otherwise leave the field name temporarily and add a follow-up cleanup task.

- [ ] **Step 4: Implement PydanticAI part conversion**

Replace old `_extract_request_parts`, `_extract_response_parts`, and `_extract_tool_results` internals with chunk builders:

```python
def _chunks_from_request(request: ModelRequest) -> list[ContextPartChunk]:
    chunks: list[ContextPartChunk] = []
    for part in request.parts:
        if isinstance(part, PydanticSystemPromptPart):
            chunks.append(ContextPartChunk(part=SystemPromptPart(content=part.content)))
        elif isinstance(part, PydanticUserPromptPart) and isinstance(part.content, str):
            chunks.append(ContextPartChunk(part=UserMessagePart(content=part.content)))
        elif isinstance(part, PydanticToolReturnPart):
            chunks.append(
                ContextPartChunk(
                    part=ToolResultPart(
                        tool_call_id=part.tool_call_id,
                        tool_name=part.tool_name,
                        content=_serialize_tool_content(part.content),
                    )
                )
            )
    return chunks


def _chunks_from_response(response: ModelResponse) -> list[ContextPartChunk]:
    logprobs = extract_logprobs(response)
    chunks: list[ContextPartChunk] = []
    for part in response.parts:
        if isinstance(part, PydanticTextPart):
            chunks.append(
                ContextPartChunk(part=AssistantTextPart(content=part.content), logprobs=logprobs)
            )
            logprobs = None
        elif isinstance(part, PydanticToolCallPart):
            chunks.append(
                ContextPartChunk(
                    part=ToolCallPart(
                        tool_name=part.tool_name,
                        tool_call_id=part.tool_call_id,
                        args=part.args_as_dict(),
                    ),
                    logprobs=logprobs,
                )
            )
            logprobs = None
        elif isinstance(part, PydanticThinkingPart):
            chunks.append(
                ContextPartChunk(part=ThinkingPart(content=part.content), logprobs=logprobs)
            )
            logprobs = None
    return chunks
```

Only attach turn-level logprobs to the first model-output chunk. This matches the current persisted behavior where sibling events omit the shared token stream after the first model-output event.

- [ ] **Step 5: Implement replay from chunk logs**

Update `assemble_replay()` to consume `RunContextEvent.parsed_payload()` as `ContextPartChunkLog`, then switch on `log.part`.

```python
payload = event.parsed_payload()
part = payload.part
```

Map:
- `SystemPromptPart` -> `PydanticSystemPromptPart`
- `UserMessagePart` -> `PydanticUserPromptPart`
- `ToolResultPart` -> `PydanticToolReturnPart`
- `ThinkingPart` -> `PydanticThinkingPart`
- `AssistantTextPart` -> `PydanticTextPart`
- `ToolCallPart` -> `PydanticToolCallPart`

- [ ] **Step 6: Keep old adapter methods as wrappers**

Keep `build_turns()` and `build_new_turns()` temporarily by grouping chunks into a deprecated `GenerationTurn` only if old callers still exist at this point. Add comments marking them as migration-only. Task 7 must delete these wrappers; the final codebase must not expose the old turn API.

- [ ] **Step 7: Run adapter and replay tests**

Run:

```bash
pytest tests/unit/builtins/common/test_transcript_adapters.py tests/unit/state/test_context_assembly.py tests/unit/state/test_generation_turn_build.py -v
```

Expected: PASS after old tests are rewritten or any migration-only wrappers are correct. These wrappers are not allowed to remain after Task 7.

---

### Task 5: Migrate Worker Interface And Execution Persistence

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/services/task_execution_service.py`
- Modify: `ergon_core/ergon_core/api/results.py`
- Modify: worker base API files that type `execute()` return values.
- Modify: `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`
- Modify: `ergon_builtins/ergon_builtins/workers/baselines/training_stub_worker.py`
- Modify: smoke fixture workers under `ergon_core/ergon_core/test_support/smoke_fixtures/smoke_base/`
- Modify: `tests/unit/workers/test_react_worker_contract.py`
- Modify: `tests/unit/state/test_research_rubrics_workers.py`

- [ ] **Step 1: Find all `AsyncGenerator[GenerationTurn` callers**

Run:

```bash
rg "AsyncGenerator\\[GenerationTurn|GenerationTurn" ergon_core ergon_builtins tests -n
```

Expected: a finite list including builtins workers, smoke fixtures, test support, and execution persistence.

- [ ] **Step 2: Update worker API type hints**

Replace worker `execute()` signatures from:

```python
) -> AsyncGenerator[GenerationTurn, None]:
```

to:

```python
) -> AsyncGenerator[ContextPartChunk, None]:
```

Import `ContextPartChunk` from `ergon_core.core.generation`.

- [ ] **Step 3: Update task execution persistence loop**

In `task_execution_service.py`, replace the turn persistence call:

```python
async for turn in worker.execute(task, context=context):
    await context_event_repository.persist_turn(
        session,
        run_id=run_id,
        execution_id=execution.id,
        worker_binding_key=worker_binding_key,
        turn=turn,
    )
```

with:

```python
async for chunk in worker.execute(task, context=context):
    await context_event_repository.persist_chunk(
        session,
        run_id=run_id,
        execution_id=execution.id,
        worker_binding_key=worker_binding_key,
        chunk=chunk,
    )
```

Keep exact local variable names consistent with the existing file.

- [ ] **Step 4: Update simple text-yielding workers**

For smoke workers that currently yield:

```python
yield GenerationTurn(response_parts=[TextPart(content="...")])
```

replace with:

```python
yield ContextPartChunk(part=AssistantTextPart(content="..."))
```

For user prompt setup chunks, emit:

```python
yield ContextPartChunk(part=UserMessagePart(content="..."))
```

Only emit prompt chunks if the worker previously included them in `messages_in`; do not invent additional prompt events.

- [ ] **Step 5: Update `training_stub_worker.py`**

Replace synthetic `GenerationTurn` creation with chunk lists:

```python
chunks: list[ContextPartChunk] = []
chunks.append(ContextPartChunk(part=UserMessagePart(content=f"Task: Synthetic task {task_slug}")))
chunks.append(
    ContextPartChunk(
        part=ToolCallPart(
            tool_name="stub_tool",
            tool_call_id=f"call_{i}",
            args={"turn": i, "task": task_slug},
        ),
        logprobs=logprobs,
    )
)
chunks.append(
    ContextPartChunk(
        part=ToolResultPart(
            tool_call_id=f"call_{i}",
            tool_name="stub_tool",
            content=f"Tool result for turn {i} of {task_slug}",
        )
    )
)
```

For final assistant output:

```python
ContextPartChunk(
    part=AssistantTextPart(content=f"Synthetic response turn {i}"),
    logprobs=logprobs,
)
```

- [ ] **Step 6: Update `react_worker.py`**

Where the worker previously handled `GenerationTurn` outputs or inspected payload classes, switch to chunk/log parts:

```python
payload = event.parsed_payload()
part = payload.part
if isinstance(part, AssistantTextPart):
    ...
```

For final assistant message extraction, replace `AssistantTextPayload` checks with `AssistantTextPart`.

- [ ] **Step 7: Run worker contract tests**

Run:

```bash
pytest tests/unit/workers/test_react_worker_contract.py tests/unit/state/test_research_rubrics_workers.py -v
```

Expected: PASS after signatures and assertions are migrated.

---

### Task 6: Update REST, Dashboard, And RL Consumers

**Files:**
- Modify: `ergon_core/ergon_core/core/api/schemas.py`
- Modify: `ergon_core/ergon_core/core/api/runs.py`
- Modify: `ergon_core/ergon_core/core/dashboard/event_contracts.py`
- Modify: `ergon_core/ergon_core/core/dashboard/emitter.py`
- Modify: `ergon_core/ergon_core/core/rl/extraction.py`
- Modify: dashboard generated contracts if this repo checks them in.
- Modify: `tests/unit/dashboard/test_event_contract_types.py`

- [ ] **Step 1: Type REST context event DTOs with chunk logs**

Modify `RunContextEventDto`:

```python
from ergon_core.core.generation import ContextPartChunkLog
from ergon_core.core.persistence.context.event_payloads import ContextEventType


class RunContextEventDto(CamelModel):
    id: str
    task_execution_id: str
    task_node_id: str
    worker_binding_key: str
    sequence: int
    event_type: ContextEventType
    payload: ContextPartChunkLog
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
```

- [ ] **Step 2: Project typed payloads in REST snapshots**

In `_context_events_by_task()`, change:

```python
payload=event.payload,
```

to:

```python
payload=event.parsed_payload(),
```

Keep `event_type=cast(ContextEventType, event.event_type)` if type checking requires it.

- [ ] **Step 3: Type dashboard event contracts with the same payload**

In `event_contracts.py`, ensure:

```python
payload: ContextPartChunkLog
```

instead of the old `ContextEventPayload` union alias if that alias is still confusing.

- [ ] **Step 4: Update dashboard emitter payload validation**

In `emitter.py`, validate as:

```python
payload=event.parsed_payload()
```

instead of constructing a separate TypeAdapter in the emitter.

- [ ] **Step 5: Update RL extraction**

Change event handling from payload-class checks to part-class checks:

```python
payload = event.parsed_payload()
part = payload.part

if isinstance(part, (SystemPromptPart, UserMessagePart)):
    ...
elif isinstance(part, (AssistantTextPart, ToolCallPart, ThinkingPart)):
    token_ids = _get_token_ids(payload, tokenizer)
elif isinstance(part, ToolResultPart):
    result_tokens = tokenizer.encode(str(part.content))
```

Update `_get_token_ids()` to accept `ContextPartChunkLog` and inspect `payload.part`.

- [ ] **Step 6: Run REST/dashboard/RL tests**

Run:

```bash
pytest tests/unit/dashboard/test_event_contract_types.py tests/unit/state/test_context_assembly.py tests/unit/persistence/test_context_event_repository.py -v
```

Expected: PASS after DTOs and consumers use `ContextPartChunkLog`.

---

### Task 7: Add Architecture Guards And Remove Deprecated Turn API

**Files:**
- Modify: `tests/unit/architecture/test_core_schema_sources.py`
- Modify: `ergon_core/ergon_core/core/generation.py`
- Modify: any remaining files found by `rg`.

- [ ] **Step 1: Add architecture guard against duplicate context payload unions**

Add to `tests/unit/architecture/test_core_schema_sources.py`:

```python
from pathlib import Path


def test_context_stream_has_single_discriminated_part_union() -> None:
    root = Path(__file__).resolve().parents[3]
    generation = root / "ergon_core" / "ergon_core" / "core" / "generation.py"
    event_payloads = (
        root
        / "ergon_core"
        / "ergon_core"
        / "core"
        / "persistence"
        / "context"
        / "event_payloads.py"
    )

    generation_text = generation.read_text()
    event_payloads_text = event_payloads.read_text()

    assert "ContextPart = Annotated[" in generation_text
    assert "SystemPromptPayload |" not in event_payloads_text
    assert "AssistantTextPayload |" not in event_payloads_text
    assert "ToolCallPayload |" not in event_payloads_text
```

- [ ] **Step 2: Run the architecture test**

Run:

```bash
pytest tests/unit/architecture/test_core_schema_sources.py -v
```

Expected: PASS only after `event_payloads.py` no longer owns a duplicate payload union.

- [ ] **Step 3: Remove deprecated `GenerationTurn` compatibility**

Run:

```bash
rg "GenerationTurn|ModelRequestPart|ModelResponsePart|ToolReturnPart|TextPart|UserPromptPart" ergon_core ergon_builtins tests -n
```

Remove remaining old names where possible. Keep `TextPart` only when it refers to `pydantic_ai.messages.TextPart`, and alias it as `PydanticTextPart` in imports to avoid confusion.

- [ ] **Step 4: Delete compatibility aliases**

From `generation.py`, remove:

```python
UserPromptPart = UserMessagePart
TextPart = AssistantTextPart
ToolReturnPart = ToolResultPart
ModelRequestPart = ...
ModelResponsePart = ...
class GenerationTurn(...)
```

Only do this once `rg` confirms no production caller depends on those names.

- [ ] **Step 5: Verify no old payload classes or aliases exist in `event_payloads.py`**

Run:

```bash
rg "SystemPromptPayload|UserMessagePayload|AssistantTextPayload|ToolCallPayload|ToolResultPayload|ThinkingPayload" ergon_core ergon_builtins tests -n
```

Expected: no production matches. Test matches should be migrated to `ContextPartChunkLog` and canonical part classes.

Confirm `event_payloads.py` does not define or export:

```python
SystemPromptPayload
UserMessagePayload
AssistantTextPayload
ToolCallPayload
ToolResultPayload
ThinkingPayload
```

Keep:

```python
ContextEventType
ContextEventPayload = ContextPartChunkLog
```

or rename `ContextEventPayload` to `ContextPartChunkLog` everywhere if the alias is no longer useful.

- [ ] **Step 6: Run full focused suite**

Run:

```bash
pytest \
  tests/unit/state/test_context_part_stream.py \
  tests/unit/persistence/test_context_event_repository.py \
  tests/unit/builtins/common/test_transcript_adapters.py \
  tests/unit/state/test_context_assembly.py \
  tests/unit/workers/test_react_worker_contract.py \
  tests/unit/dashboard/test_event_contract_types.py \
  tests/unit/architecture/test_core_schema_sources.py \
  -v
```

Expected: PASS.

- [ ] **Step 7: Run broader unit smoke**

Run:

```bash
pytest tests/unit -q
```

Expected: PASS, or only unrelated pre-existing failures. Investigate any failures mentioning context events, generation turns, workers, dashboard contracts, replay, or RL extraction.

---

## Migration Notes

This is a schema/API clean break. Do not preserve backwards compatibility with the old schemas in the final state.

Temporary adapters are allowed only inside intermediate tasks to make the migration reviewable:
- `GenerationTurn` can exist only until worker execution is moved to chunks.
- request/response subset aliases can exist only until all worker and adapter callers move to `ContextPartChunk`.
- old `*Payload` event classes should not be reintroduced as aliases; migrate those callers directly to `ContextPartChunkLog.part`.

After Task 7, the only canonical stream type should be `ContextPart`, the worker generator type should be `ContextPartChunk`, and the enriched log type should be `ContextPartChunkLog`.

Do not add a second new union in `event_payloads.py`. Do not leave compatibility exports for the old payload classes. Either outcome recreates the drift this plan is removing.

---

## Self-Review

**Spec coverage:** The plan implements the requested model: `ContextPart` as the single discriminated union, `ContextPartChunk` as the worker generator type, and `ContextPartChunkLog` as the core-enriched persistence/API shape.

**Placeholder scan:** No steps rely on `TBD`, unspecified tests, or unnamed files. Commands and expected outcomes are included for each task.

**Type consistency:** The plan consistently uses `content` for text-bearing parts, `part_kind` for the part discriminator, `token_ids`/`logprobs` for worker-provided token metadata, and `sequence`/`worker_binding_key`/`turn_id` for core-enriched log metadata.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-28-context-part-chunk-stream.md`. Two execution options:

**1. Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
