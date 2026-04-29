# ReAct Worker Failure Context Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve partial PydanticAI ReAct transcript history when `agent.iter(...)` raises before `ReActWorker._run_agent()` reaches its normal post-run transcript extraction.

**Architecture:** Keep runtime persistence ownership in `worker_execute_fn()`: workers yield `GenerationTurn`, runtime persists `RunContextEvent`. Add an incremental/cursor-based extraction API to `PydanticAITranscriptAdapter` so `ReActWorker` can yield completed turns during normal iteration and flush any remaining partial turn in an exception path before re-raising. This keeps failure semantics intact while eliminating the current zero-context failure gap for failed ReAct/CLI child workers.

**Tech Stack:** Python, PydanticAI `Agent.iter`, `GenerationTurn`, `PydanticAITranscriptAdapter`, `ContextEventRepository`, pytest.

---

## Root Cause

Current `ReActWorker._run_agent()` only converts PydanticAI messages into `GenerationTurn`s after the `agent.iter(...)` context exits normally:

```python
async with agent.iter(...) as run:
    async for _node in run:
        ...

turns = PydanticAITranscriptAdapter().build_turns(run.ctx.state.message_history)
for turn in turns:
    yield turn
```

If PydanticAI raises inside `async for _node in run`, control jumps out of `_run_agent()` before `build_turns(...)` runs. Then `worker_execute_fn()` catches the exception before it has received any turns to persist. That explains executions with an error stack but `0` `RunContextEvent` rows.

The ResearchRubrics workflow CLI worker is affected because it subclasses `ReActWorker`:

```python
async for turn in super().execute(task, context=context):
    yield turn
```

Successful CLI runs use the shared adapter; failed CLI runs can still lose partial transcript history.

---

## Desired Behavior

- Successful ReAct runs keep capturing the same full transcript as today.
- Failed ReAct runs yield/persist every turn that can be reconstructed from `run.ctx.state.message_history` before re-raising the original exception.
- Runtime failure semantics do not change: `worker_execute_fn()` still returns the failure result and task status remains failed.
- Workers do not call `ContextEventRepository` directly.
- No duplicate context events are emitted when incremental extraction is called multiple times.
- Partial trailing responses can be flushed on final success or failure, but not emitted prematurely while a tool call may still receive a following `ToolReturnPart`.

---

## File Map

```text
ergon_builtins/
  ergon_builtins/
    common/
      llm_context/
        adapters/
          pydantic_ai.py                       # modify: replace post-run-only turn extraction with cursor API
    workers/
      baselines/
        react_worker.py                        # modify: yield incremental turns and flush on exception

tests/
  unit/
    builtins/
      common/
        test_transcript_adapters.py            # modify: cursor extraction + trailing flush tests
    workers/
      test_react_worker_contract.py            # modify or add tests for failure transcript yield/re-raise
```

Do not modify `worker_execute_fn()` for this fix unless tests prove it cannot persist turns yielded immediately before an async generator raises. The existing `async for turn in worker.execute(...)` loop already persists each yielded turn before requesting the next one.

---

## Closure And Removals

This is not an additive second serialization path. Close the old behavior explicitly:

- Remove `ReActWorker._run_agent()`'s post-run-only extraction pattern:

```python
turns = PydanticAITranscriptAdapter().build_turns(run.ctx.state.message_history)
for turn in turns:
    yield turn
```

Replace it with cursor extraction during the loop plus final/failure flush.

- Do not add a new repository or direct DB writer for failure capture. `ContextEventRepository` remains the only `GenerationTurn` -> `RunContextEvent` serializer, and it remains called by `worker_execute_fn()`.
- Do not restore the old core PydanticAI serializers removed in the previous refactor: `ergon_core/core/persistence/context/assembly.py` and `ergon_core/core/providers/generation/pydantic_ai_format.py`.
- Do not add any new `ergon_core` PydanticAI transcript code. All PydanticAI transcript extraction/replay stays in `ergon_builtins.common.llm_context.adapters.pydantic_ai`.
- Treat the cursor API as the runtime extraction surface. If a batch `build_turns(...)` helper remains for tests or protocol compatibility, implement it as a wrapper around the same cursor extraction logic, not as a second independent serializer.
- Update tests that assert the worker no longer owns parser helpers so they also assert `ReActWorker` does not call a post-run-only extraction helper directly.

There is no separate old "turn serialization repository" to delete after the previous refactor. The durable serialization repository is still `ContextEventRepository`, and that should stay. The old thing to remove here is the worker's post-run-only transcript extraction path, because it is the failure gap.

---

## Design

Use a small cursor object in the PydanticAI adapter:

```python
from pydantic import BaseModel


class TranscriptTurnCursor(BaseModel):
    model_config = {"validate_assignment": True}

    emitted_turn_count: int = 0
```

Make cursor extraction the runtime API:

```python
class PydanticAITranscriptAdapter(...):
    def build_new_turns(
        self,
        transcript: list[ModelMessage],
        cursor: TranscriptTurnCursor,
        *,
        flush_pending: bool = False,
    ) -> list[GenerationTurn]:
        turns = _build_turns_from_transcript(transcript, flush_pending=flush_pending)
        new_turns = turns[cursor.emitted_turn_count :]
        cursor.emitted_turn_count = len(turns)
        return new_turns
```

If `build_turns(...)` remains public because `TranscriptAdapter` currently declares it, it should delegate to the same internal implementation used by `build_new_turns(...)`. Do not keep two independent conversion implementations.

Change current trailing-response behavior in `build_turns()` so it is explicit:

```python
if pending_response is not None and flush_pending:
    turns.append(_to_turn(pending_request_in, pending_response, tool_result_request=None))
```

`flush_pending=False` is important during the live `agent.iter(...)` loop. It prevents emitting a tool-call response before the following `ModelRequest` has a chance to include the `ToolReturnPart`. On final success or failure, use `flush_pending=True` so partial model output is not lost.

Update `ReActWorker._run_agent()`:

```python
adapter = PydanticAITranscriptAdapter()
cursor = TranscriptTurnCursor()
run = None

try:
    async with agent.iter(...) as active_run:
        run = active_run
        async for _node in run:
            node_count += 1

            for turn in adapter.build_new_turns(
                run.ctx.state.message_history,
                cursor,
                flush_pending=False,
            ):
                yield turn

            if node_count >= self.max_iterations:
                logger.warning(...)
                break
except Exception:
    if run is not None:
        for turn in adapter.build_new_turns(
            run.ctx.state.message_history,
            cursor,
            flush_pending=True,
        ):
            yield turn
    raise

if run is not None:
    for turn in adapter.build_new_turns(
        run.ctx.state.message_history,
        cursor,
        flush_pending=True,
    ):
        yield turn
```

This is extraction-as-iterator in practice: the cursor marks what has already been yielded, and `build_new_turns(...)` can be called repeatedly as message history grows.

Do not swallow exceptions. The final `raise` is required so `worker_execute_fn()` still records failure.

---

## Task 1: Adapter Cursor API

**Files:**
- Modify: `ergon_builtins/ergon_builtins/common/llm_context/adapters/pydantic_ai.py`
- Modify: `tests/unit/builtins/common/test_transcript_adapters.py`

- [ ] **Step 1: Write failing test for no premature trailing response**

Add to `tests/unit/builtins/common/test_transcript_adapters.py`:

```python
from ergon_builtins.common.llm_context.adapters.pydantic_ai import TranscriptTurnCursor


def test_incremental_extraction_does_not_emit_pending_tool_call_response() -> None:
    adapter = PydanticAITranscriptAdapter()
    cursor = TranscriptTurnCursor()
    transcript = [
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
    ]

    assert adapter.build_new_turns(transcript, cursor, flush_pending=False) == []

    flushed = adapter.build_new_turns(transcript, cursor, flush_pending=True)
    assert len(flushed) == 1
    assert any(isinstance(part, ErgonToolCallPart) for part in flushed[0].response_parts)
```

- [ ] **Step 2: Write failing test for no duplicate new turns**

Add:

```python
def test_incremental_extraction_tracks_emitted_turns() -> None:
    adapter = PydanticAITranscriptAdapter()
    cursor = TranscriptTurnCursor()
    transcript = [
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

    first = adapter.build_new_turns(transcript, cursor, flush_pending=False)
    second = adapter.build_new_turns(transcript, cursor, flush_pending=False)

    assert len(first) == 1
    assert second == []
```

- [ ] **Step 3: Run red tests**

Run:

```bash
uv run pytest tests/unit/builtins/common/test_transcript_adapters.py -q
```

Expected: FAIL because `TranscriptTurnCursor` and `build_new_turns()` do not exist.

- [ ] **Step 4: Replace batch extraction internals with cursor-backed extraction**

In `pydantic_ai.py`, add:

```python
from pydantic import BaseModel


class TranscriptTurnCursor(BaseModel):
    model_config = {"validate_assignment": True}

    emitted_turn_count: int = 0
```

Move the existing `build_turns(...)` body into a private helper that takes `flush_pending`:

```python
def _build_turns_from_transcript(
    transcript: list[ModelMessage],
    *,
    flush_pending: bool,
) -> list[GenerationTurn]:
    ...
```

Keep `build_turns(...)` only as compatibility with the existing `TranscriptAdapter` protocol and any batch tests:

```python
def build_turns(
    self,
    transcript: list[ModelMessage],
    *,
    flush_pending: bool = True,
) -> list[GenerationTurn]:
    return _build_turns_from_transcript(transcript, flush_pending=flush_pending)
```

Do not call `build_turns(...)` from `ReActWorker`. Runtime extraction should use the cursor API only.

Change trailing append:

```python
if pending_response is not None:
    turns.append(_to_turn(pending_request_in, pending_response, tool_result_request=None))
```

to:

```python
if pending_response is not None and flush_pending:
    turns.append(_to_turn(pending_request_in, pending_response, tool_result_request=None))
```

Add:

```python
def build_new_turns(
    self,
    transcript: list[ModelMessage],
    cursor: TranscriptTurnCursor,
    *,
    flush_pending: bool = False,
) -> list[GenerationTurn]:
    turns = _build_turns_from_transcript(transcript, flush_pending=flush_pending)
    new_turns = turns[cursor.emitted_turn_count :]
    cursor.emitted_turn_count = len(turns)
    return new_turns
```

After this change, there is one conversion implementation: `_build_turns_from_transcript(...)`. `build_turns(...)` and `build_new_turns(...)` are wrappers with different calling semantics.

- [ ] **Step 5: Run green tests**

Run:

```bash
uv run pytest tests/unit/builtins/common/test_transcript_adapters.py -q
```

Expected: PASS.

---

## Task 2: ReActWorker Failure Flush

**Files:**
- Modify: `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`
- Modify: `tests/unit/workers/test_react_worker_contract.py`

- [ ] **Step 1: Write failing test for partial yield then re-raise**

Add a fake `Agent` to `tests/unit/workers/test_react_worker_contract.py`:

```python
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart


class _FakeRunState:
    def __init__(self):
        self.message_history = [
            ModelRequest(parts=[UserPromptPart(content="question")]),
            ModelResponse(parts=[TextPart(content="partial answer")]),
        ]


class _FakeRunContext:
    def __init__(self):
        self.state = _FakeRunState()


class _FailingAgentRun:
    def __init__(self):
        self.ctx = _FakeRunContext()

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise RuntimeError("tool validation failed")


class _FailingAgentIter:
    async def __aenter__(self):
        return _FailingAgentRun()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FailingAgent:
    def __init__(self, **kwargs):
        pass

    def iter(self, *args, **kwargs):
        return _FailingAgentIter()
```

Then add:

```python
@pytest.mark.asyncio
async def test_react_worker_yields_partial_turn_before_reraising_agent_iter_failure(monkeypatch) -> None:
    import ergon_builtins.workers.baselines.react_worker as react_worker

    monkeypatch.setattr(react_worker, "Agent", _FailingAgent)
    monkeypatch.setattr(
        react_worker,
        "resolve_model_target",
        lambda model: type(
            "Resolved",
            (),
            {"model": "stub:constant", "capture_model_settings": None},
        )(),
    )

    worker = ReActWorker(
        name="unit",
        model=None,
        task_id=UUID(int=1),
        sandbox_id="test-sandbox",
        tools=[],
        system_prompt=None,
        max_iterations=10,
    )
    task = _minimal_task()

    turns = []
    with pytest.raises(RuntimeError, match="tool validation failed"):
        async for turn in worker.execute(task, context=_minimal_context()):
            turns.append(turn)

    assert len(turns) == 1
    assert any(part.content == "partial answer" for part in turns[0].response_parts)
```

Add small local helpers if this test file does not already have task/context fixtures:

```python
from ergon_core.api.task_types import BenchmarkTask, EmptyTaskPayload
from ergon_core.api.worker_context import WorkerContext


def _minimal_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id=UUID(int=2),
        task_slug="unit-task",
        description="Unit task",
        task_payload=EmptyTaskPayload(),
    )


def _minimal_context() -> WorkerContext:
    return WorkerContext(
        run_id=UUID(int=3),
        definition_id=UUID(int=4),
        task_id=UUID(int=2),
        execution_id=UUID(int=5),
        sandbox_id="test-sandbox",
        node_id=UUID(int=6),
    )
```

- [ ] **Step 2: Run red test**

Run:

```bash
uv run pytest tests/unit/workers/test_react_worker_contract.py::test_react_worker_yields_partial_turn_before_reraising_agent_iter_failure -q
```

Expected: FAIL because `_run_agent()` currently re-raises before yielding the partial transcript.

- [ ] **Step 3: Implement failure flush in `_run_agent()`**

Modify `ReActWorker._run_agent()`:

```python
adapter = PydanticAITranscriptAdapter()
cursor = TranscriptTurnCursor()
run = None

try:
    async with agent.iter(
        task_prompt,
        model_settings=resolved.capture_model_settings,
        message_history=self._seed_messages,
    ) as active_run:
        run = active_run
        async for _node in run:
            node_count += 1
            for turn in adapter.build_new_turns(
                run.ctx.state.message_history,
                cursor,
                flush_pending=False,
            ):
                yield turn
            if node_count >= self.max_iterations:
                logger.warning(...)
                break
except Exception:
    if run is not None:
        for turn in adapter.build_new_turns(
            run.ctx.state.message_history,
            cursor,
            flush_pending=True,
        ):
            yield turn
    raise

if run is not None:
    for turn in adapter.build_new_turns(
        run.ctx.state.message_history,
        cursor,
        flush_pending=True,
    ):
        yield turn
```

Keep the existing warning text for `max_iterations`.

- [ ] **Step 4: Run worker test**

Run:

```bash
uv run pytest tests/unit/workers/test_react_worker_contract.py -q
```

Expected: PASS.

---

## Task 3: Runtime Persistence Regression

**Files:**
- Modify: `tests/unit/runtime/test_failure_error_json.py` or add `tests/unit/runtime/test_worker_execute_partial_failure_context.py`

- [ ] **Step 1: Add runtime-level regression if feasible**

Add a unit test around `worker_execute_fn()` with a fake registered worker whose `execute()` yields one `GenerationTurn` and then raises. Assert that `ContextEventRepository.persist_turn()` is called before the failure result is returned.

If existing `worker_execute_fn()` setup makes this too fixture-heavy, keep the worker-level test from Task 2 as the required regression and add a short comment in the test explaining why it is sufficient:

```python
# worker_execute_fn persists each yielded turn before requesting the next item
# from the async generator, so this test covers the failure-capture contract at
# the worker boundary without rebuilding Inngest context fixtures.
```

- [ ] **Step 2: Run focused runtime/worker tests**

Run:

```bash
uv run pytest tests/unit/workers/test_react_worker_contract.py tests/unit/persistence/test_context_event_repository.py -q
```

Expected: PASS.

---

## Task 4: Verification

**Files:**
- No production edits.

- [ ] **Step 1: Run affected capture suite**

Run:

```bash
uv run pytest \
  tests/unit/builtins/common/test_transcript_adapters.py \
  tests/unit/persistence/test_context_event_repository.py \
  tests/unit/workers/test_react_worker_contract.py \
  tests/unit/state/test_generation_turn_build.py \
  tests/unit/state/test_context_assembly.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run lint/compile**

Run:

```bash
uv run ruff check \
  ergon_builtins/ergon_builtins/common/llm_context/adapters/pydantic_ai.py \
  ergon_builtins/ergon_builtins/workers/baselines/react_worker.py \
  tests/unit/builtins/common/test_transcript_adapters.py \
  tests/unit/workers/test_react_worker_contract.py
uv run slopcop \
  ergon_builtins/ergon_builtins/common/llm_context/adapters/pydantic_ai.py \
  ergon_builtins/ergon_builtins/workers/baselines/react_worker.py
uv run python -m compileall -q \
  ergon_builtins/ergon_builtins/common/llm_context/adapters/pydantic_ai.py \
  ergon_builtins/ergon_builtins/workers/baselines/react_worker.py
```

Expected: PASS.

- [ ] **Step 3: Optional real-run validation**

Trigger a ReAct/CLI worker failure after the PydanticAI run has started, then inspect:

```bash
RUN_ID=<run-id> python - <<'PY'
from uuid import UUID
from sqlmodel import select
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.context.models import RunContextEvent

run_id = UUID(__import__("os").environ["RUN_ID"])
with get_session() as session:
    rows = session.exec(
        select(RunContextEvent)
        .where(RunContextEvent.run_id == run_id)
        .order_by(RunContextEvent.task_execution_id, RunContextEvent.sequence)
    ).all()
    for row in rows:
        print(row.task_execution_id, row.sequence, row.event_type)
PY
```

Expected: the failed child execution has at least the partial model request/response/tool-call events that existed before the exception.

---

## Self-Review

- Spec coverage: The plan addresses the observed gap where `agent.iter(...)` raises before post-run extraction, including CLI workers through `ReActWorker` inheritance.
- Iterator question: The plan proposes cursor-based incremental extraction from growing `message_history`, which is the appropriate iterator shape for PydanticAI histories.
- Persistence boundary: The plan keeps `ContextEventRepository` in the runtime path and does not make workers write directly to the DB.
- Failure semantics: The original exception is re-raised after partial turns are yielded.
- Known limitation: If `agent.iter(...)` fails during `__aenter__` before a `run` object exists, there is no PydanticAI `message_history` to flush. That case should still produce normal task failure metadata, but cannot produce transcript events.
