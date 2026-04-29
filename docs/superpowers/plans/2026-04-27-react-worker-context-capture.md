# ReAct Worker Context Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make real LLM ReAct workers persist the full model-context transcript, including thinking blocks and tool observations, into `run_context_events`.

**Architecture:** Keep `RunContextEvent` as the canonical durable context log. Move PydanticAI-specific transcript parsing out of `ReActWorker` into `ergon_builtins.common.llm_context`, add a small capture-settings helper there for provider-specific thinking/logprob settings, and keep runtime persistence framework-neutral by consuming `GenerationTurn`.

**Tech Stack:** Python, PydanticAI, SQLModel, `GenerationTurn`, `ContextEventRepository`, pytest.

---

## Scope

This plan covers backend capture only:

- Turn on reasoning/thinking capture for real ReAct workers where PydanticAI/provider support exists.
- Extract PydanticAI message history into `GenerationTurn` via a reusable utility.
- Persist `GenerationTurn.tool_results` as `tool_result` rows.
- Add unit tests around transcript extraction, model settings, and context event persistence.

This plan does not redesign the workspace Actions UI. After this lands, the existing Actions tab should automatically receive richer `contextEventsByTask` data for new runs.

---

## File Map

The extraction and capture-settings code belongs in `ergon_builtins`, not `ergon_core`, because it depends on concrete worker/framework behavior. `ergon_core` should keep only stable contracts and persistence: `GenerationTurn` in, `RunContextEvent` out.

Within `ergon_builtins`, this should live in `common/llm_context/`: shared code for built-in LLM workers that is not specific to MiniF2F, SWE-Bench, ResearchRubrics, or any one benchmark. Keep this domain narrow:

- `capture_settings.py` decides what provider settings to pass when we want transcript capture.
- `adapters/base.py` defines the common transcript adapter interface in both directions.
- `adapters/pydantic_ai.py` adapts PydanticAI message history into Ergon's framework-neutral `GenerationTurn`, reconstructs PydanticAI messages from `RunContextEvent` rows, and owns PydanticAI response-metadata parsing such as logprobs.
- Benchmark toolkits, prompts, sandbox code, and worker output policy stay where they are.

If this refactor also consolidates model resolution out of core, keep that under `ergon_builtins.models`, not under `llm_context`. Model resolution is about selecting a concrete model backend; `llm_context` is about transcript capture/replay.

```text
ergon_builtins/
  ergon_builtins/
    common/                                    # add: shared builtins utility package
      __init__.py                              # add
      llm/
        structured_judge.py                    # optional move: core structured_judge helper if moving model resolution
      llm_context/                             # add: shared LLM context-capture domain for built-in workers
        __init__.py                            # add
        capture_settings.py                    # add: provider-specific thinking/logprob model_settings
        adapters/                              # add: framework transcript adapters
          __init__.py                          # add
          base.py                              # add: TranscriptAdapter protocol/base interface
          pydantic_ai.py                       # add: PydanticAI <-> GenerationTurn/RunContextEvent adapter
          langgraph.py                         # do not add yet: reserved for future framework adapter
          openai_sdk.py                        # do not add yet: reserved for future direct-SDK adapter
        prompts.py                             # do not add: benchmark prompts stay under workers/benchmarks
        tools.py                               # do not add: benchmark toolkits stay under tools/ or benchmarks/
    workers/
      baselines/
        react_worker.py                        # modify: call shared capture/extraction helpers
                                                # remove: _build_turns
                                                # remove: _to_turn
                                                # remove: _extract_request_parts
                                                # remove: _extract_response_parts
                                                # remove: _extract_tool_results
                                                # remove: _make_json_safe
                                                # remove: transcript-only imports for dataclasses,
                                                #         PydanticAI request/response parts,
                                                #         Ergon part classes, extract_logprobs,
                                                #         and LOGPROB_SETTINGS
        react_prompts.py                       # leave alone: benchmark/system prompt definitions
      research_rubrics/
        researcher_worker.py                   # leave alone unless it later adopts PydanticAI transcript capture
        workflow_cli_react_worker.py           # leave alone unless it later adopts PydanticAI transcript capture
    models/
      resolution.py                            # optional move: ResolvedModel/register/resolve from core
      openrouter_backend.py                    # leave alone: model resolution backend already exists
      vllm_backend.py                          # leave alone: model resolution backend already exists
      cloud_passthrough.py                     # leave alone: passthrough backend behavior unchanged
    tools/                                     # leave alone: tool definitions are not transcript extraction

ergon_core/
  ergon_core/
    api/
      generation.py                            # existing contract: GenerationTurn stays framework-neutral
    core/
      rl/
        __init__.py                             # modify: remove PydanticAI-specific LOGPROB_SETTINGS if unused
      providers/
        generation/
          model_resolution.py                  # optional remove: move to ergon_builtins.models.resolution
          structured_judge.py                  # optional remove: move to ergon_builtins.common.llm.structured_judge
          capture_settings.py                  # do not add here
          adapters/                            # do not add framework adapters here
          pydantic_ai_format.py                # remove or stop using: behavior moves to PydanticAI adapter
      persistence/
        context/
          repository.py                        # modify: persist tool_result events from turn.tool_results
          models.py                            # existing table model: RunContextEvent
          event_payloads.py                    # existing payload union: tool_result/thinking/etc.
          assembly.py                          # remove: PydanticAI-specific resume assembly moves to adapter

tests/
  unit/
    builtins/
      common/
        test_capture_settings.py               # add: provider settings contract
        test_transcript_adapters.py            # add: base interface + PydanticAI adapter contract
    providers/
      test_capture_settings.py                 # do not add here
      test_transcript_adapters.py              # do not add here
    persistence/
      test_context_event_repository.py         # add: tool_results -> tool_result rows
    state/
      test_generation_turn_build.py            # modify: import new transcript adapter
      test_context_assembly.py                 # remove or move assertions into test_transcript_adapters.py
    workers/
      test_react_worker_contract.py            # modify: ReActWorker no longer owns parser helpers
```

Import direction:

- `ergon_builtins.common.llm_context.*` may import `ergon_core.api.generation` and, if moved, `ergon_builtins.models.resolution.ResolvedModel`.
- `ergon_builtins.workers.baselines.react_worker` may import `ergon_builtins.common.llm_context.*`.
- `ergon_core` must not import `ergon_builtins`.

Additional core consolidation in scope:

- Move `ergon_core/ergon_core/core/persistence/context/assembly.py` into `PydanticAITranscriptAdapter` because it imports `pydantic_ai.messages` directly.
- Move `ergon_core/ergon_core/core/providers/generation/pydantic_ai_format.py` behavior into `adapters/pydantic_ai.py` or a private sibling under `ergon_builtins.common.llm_context.adapters`; it is only useful for PydanticAI response dumps.
- Move `LOGPROB_SETTINGS` out of `ergon_core.core.rl.__init__` if no RL code imports it after this refactor; it is currently a PydanticAI model-settings constant, not an RL-domain primitive.
- Optional but coherent: move `ergon_core/ergon_core/core/providers/generation/model_resolution.py` to `ergon_builtins/ergon_builtins/models/resolution.py`. It imports PydanticAI and is populated by builtins model backends.
- Optional but coherent: move `ergon_core/ergon_core/core/providers/generation/structured_judge.py` to `ergon_builtins/ergon_builtins/common/llm/structured_judge.py`. It constructs a PydanticAI `Agent` and is currently used by builtins evaluator/benchmark code.
- Do not move `ergon_core/api/generation.py`, `event_payloads.py`, `models.py`, or `repository.py`; those are the framework-neutral core domain.
- Do not move model backends (`openrouter_backend.py`, `vllm_backend.py`, `cloud_passthrough.py`) in this refactor; they already live in `ergon_builtins.models`.

---

## Provider Settings Contract

Use one settings helper instead of scattering provider checks through workers.

Expected behavior:

- `vllm:*` keeps existing logprob settings:

```python
{"openai_logprobs": True, "openai_top_logprobs": 1}
```

- `anthropic:*` asks Anthropic for thinking blocks:

```python
{"anthropic_thinking": {"type": "enabled", "budget_tokens": 1024}}
```

- `openrouter:*` asks OpenRouter to include reasoning:

```python
{"openrouter_reasoning": {"enabled": True, "exclude": False}}
```

- `google:*` asks Gemini to include thoughts:

```python
{"gemini_thinking_config": {"include_thoughts": True}}
```

- Unknown providers return `None`; provider-specific capture behavior must be added explicitly with tests.

If provider settings conflict with a model/output mode at runtime, the implementation should fail loudly in tests first. Do not silently suppress thinking capture unless a targeted fallback is added with a test.

---

## Task 1: Add Capture Settings Helper

**Files:**

- Create: `ergon_builtins/ergon_builtins/common/__init__.py`
- Create: `ergon_builtins/ergon_builtins/common/llm_context/__init__.py`
- Create: `ergon_builtins/ergon_builtins/common/llm_context/capture_settings.py`
- Create: `ergon_builtins/ergon_builtins/common/llm_context/adapters/__init__.py`
- Create: `ergon_builtins/ergon_builtins/common/llm_context/adapters/base.py`
- Test: `tests/unit/builtins/common/test_capture_settings.py`

- [ ] **Step 1: Write tests for provider-specific model settings**

Create `tests/unit/builtins/common/test_capture_settings.py`:

```python
from ergon_builtins.common.llm_context.capture_settings import build_capture_model_settings
from ergon_core.core.providers.generation.model_resolution import ResolvedModel


def _resolved(*, supports_logprobs: bool = False) -> ResolvedModel:
    return ResolvedModel(model="dummy", supports_logprobs=supports_logprobs)


def test_vllm_enables_logprobs() -> None:
    assert build_capture_model_settings("vllm:http://localhost:8000", _resolved(supports_logprobs=True)) == {
        "openai_logprobs": True,
        "openai_top_logprobs": 1,
    }


def test_anthropic_enables_thinking() -> None:
    assert build_capture_model_settings("anthropic:claude-sonnet-4", _resolved()) == {
        "anthropic_thinking": {"type": "enabled", "budget_tokens": 1024},
    }


def test_openrouter_includes_reasoning() -> None:
    assert build_capture_model_settings("openrouter:anthropic/claude-sonnet-4.6", _resolved()) == {
        "openrouter_reasoning": {"enabled": True, "exclude": False},
    }


def test_google_includes_thoughts() -> None:
    assert build_capture_model_settings("google:gemini-2.5-pro", _resolved()) == {
        "gemini_thinking_config": {"include_thoughts": True},
    }


def test_unknown_provider_without_capture_returns_none() -> None:
    assert build_capture_model_settings("openai:gpt-4o", _resolved()) is None
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
pytest tests/unit/builtins/common/test_capture_settings.py -q
```

Expected: FAIL because `capture_settings.py` does not exist.

- [ ] **Step 3: Implement `capture_settings.py`**

Create `ergon_builtins/ergon_builtins/common/__init__.py`:

```python
"""Shared utilities for built-in Ergon workers."""
```

Create `ergon_builtins/ergon_builtins/common/llm_context/__init__.py`:

```python
"""Helpers for capturing LLM context from built-in worker frameworks."""
```

Create `ergon_builtins/ergon_builtins/common/llm_context/adapters/__init__.py`:

```python
"""Framework adapters for LLM transcript extraction and replay assembly."""
```

Create `ergon_builtins/ergon_builtins/common/llm_context/adapters/base.py`:

```python
"""Base interface for framework transcript adapters."""

from typing import Protocol, TypeVar

from ergon_core.api.generation import GenerationTurn
from ergon_core.core.persistence.context.models import RunContextEvent

TranscriptT = TypeVar("TranscriptT")
ReplayT = TypeVar("ReplayT")


class TranscriptAdapter(Protocol[TranscriptT, ReplayT]):
    """Convert between framework-native transcripts and Ergon context events."""

    def build_turns(self, transcript: TranscriptT) -> list[GenerationTurn]:
        """Return ordered turns extracted from a complete transcript."""
        ...

    def assemble_replay(self, events: list[RunContextEvent]) -> ReplayT:
        """Return framework-native replay context from ordered context events."""
        ...
```

Create `ergon_builtins/ergon_builtins/common/llm_context/capture_settings.py`:

```python
"""Provider-specific settings for capturing model context events.

Workers call this once before running an agent. The returned dictionary is
passed to PydanticAI as model_settings.
"""

from ergon_core.api.json_types import JsonObject
from ergon_core.core.providers.generation.model_resolution import ResolvedModel
_ANTHROPIC_THINKING_BUDGET_TOKENS = 1024
_OPENAI_COMPAT_LOGPROB_SETTINGS: JsonObject = {
    "openai_logprobs": True,
    "openai_top_logprobs": 1,
}


def _prefix(model_target: str | None) -> str:
    target = model_target or ""
    return target.split(":", 1)[0] if ":" in target else ""


def build_capture_model_settings(
    model_target: str | None,
    resolved_model: ResolvedModel,
) -> JsonObject | None:
    """Return PydanticAI model_settings for transcript capture."""
    prefix = _prefix(model_target)

    if prefix == "vllm" and resolved_model.supports_logprobs:
        return dict(_OPENAI_COMPAT_LOGPROB_SETTINGS)

    if prefix == "anthropic":
        return {
            "anthropic_thinking": {
                "type": "enabled",
                "budget_tokens": _ANTHROPIC_THINKING_BUDGET_TOKENS,
            }
        }

    if prefix == "openrouter":
        return {
            "openrouter_reasoning": {
                "enabled": True,
                "exclude": False,
            }
        }

    if prefix == "google":
        return {
            "gemini_thinking_config": {
                "include_thoughts": True,
            }
        }

    return None
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```bash
pytest tests/unit/builtins/common/test_capture_settings.py -q
```

Expected: PASS.

---

## Task 2: Extract PydanticAI Transcript Conversion

**Files:**

- Create: `ergon_builtins/ergon_builtins/common/llm_context/adapters/pydantic_ai.py`
- Test: `tests/unit/builtins/common/test_transcript_adapters.py`
- Modify: `tests/unit/state/test_generation_turn_build.py`

- [ ] **Step 1: Write tests for transcript extraction**

Create `tests/unit/builtins/common/test_transcript_adapters.py`:

```python
from ergon_core.api.generation import (
    GenerationTurn,
    TextPart as ErgonTextPart,
    ThinkingPart as ErgonThinkingPart,
    ToolCallPart as ErgonToolCallPart,
    ToolReturnPart as ErgonToolReturnPart,
    UserPromptPart as ErgonUserPromptPart,
)
from ergon_builtins.common.llm_context.adapters.base import TranscriptAdapter
from ergon_builtins.common.llm_context.adapters.pydantic_ai import (
    PydanticAITranscriptAdapter,
)
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)


def test_text_and_thinking_are_response_parts() -> None:
    adapter: TranscriptAdapter[list[ModelRequest | ModelResponse], list[ModelRequest | ModelResponse]] = (
        PydanticAITranscriptAdapter()
    )
    turns = adapter.build_turns(
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

    assert len(turns) == 1
    turn = turns[0]
    assert isinstance(turn, GenerationTurn)
    assert any(isinstance(part, ErgonUserPromptPart) for part in turn.messages_in)
    assert any(isinstance(part, ErgonThinkingPart) for part in turn.response_parts)
    assert any(isinstance(part, ErgonTextPart) for part in turn.response_parts)


def test_tool_return_is_attached_to_generating_turn() -> None:
    adapter = PydanticAITranscriptAdapter()
    turns = adapter.build_turns(
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
            ModelResponse(parts=[TextPart(content="done")]),
        ]
    )

    assert len(turns) == 2
    first = turns[0]
    assert any(isinstance(part, ErgonToolCallPart) for part in first.response_parts)
    assert len(first.tool_results) == 1
    result = first.tool_results[0]
    assert isinstance(result, ErgonToolReturnPart)
    assert result.tool_call_id == "call-1"
    assert result.tool_name == "search"
    assert result.content == '{"result": "found"}'
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
pytest tests/unit/builtins/common/test_transcript_adapters.py -q
```

Expected: FAIL because `adapters/pydantic_ai.py` does not exist.

- [ ] **Step 3: Implement the transcript utility**

Create `ergon_builtins/ergon_builtins/common/llm_context/adapters/pydantic_ai.py` by moving the existing parsing helpers out of `react_worker.py`:

```python
"""PydanticAI transcript adapter."""

import dataclasses  # slopcop: ignore[no-dataclass]
import json
from typing import Any

from ergon_core.api.generation import (
    GenerationTurn,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    TokenLogprob,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from ergon_core.core.persistence.context.event_payloads import (
    AssistantTextPayload,
    SystemPromptPayload,
    ThinkingPayload,
    ToolCallPayload,
    ToolResultPayload,
    UserMessagePayload,
)
from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_builtins.common.llm_context.adapters.base import TranscriptAdapter
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse
from pydantic_ai.messages import SystemPromptPart as PydanticSystemPromptPart
from pydantic_ai.messages import TextPart as PydanticTextPart
from pydantic_ai.messages import ThinkingPart as PydanticThinkingPart
from pydantic_ai.messages import ToolCallPart as PydanticToolCallPart
from pydantic_ai.messages import ToolReturnPart as PydanticToolReturnPart
from pydantic_ai.messages import UserPromptPart as PydanticUserPromptPart


class PydanticAITranscriptAdapter(TranscriptAdapter[list[ModelMessage], list[ModelMessage]]):
    """Convert complete PydanticAI message history into Ergon turns."""

    def build_turns(self, transcript: list[ModelMessage]) -> list[GenerationTurn]:
        """Build turns from a complete PydanticAI message list.

        The full message history is required because tool returns appear in the
        request after the response that created the tool call.
        """
        turns: list[GenerationTurn] = []
        pending_response: ModelResponse | None = None
        pending_request_in: ModelRequest | None = None

        for message in transcript:
            if isinstance(message, ModelRequest):
                if pending_response is not None:
                    turns.append(
                        _to_turn(
                            pending_request_in,
                            pending_response,
                            tool_result_request=message,
                        )
                    )
                    pending_response = None
                    pending_request_in = None
                pending_request_in = message
            elif isinstance(message, ModelResponse):
                pending_response = message

        if pending_response is not None:
            turns.append(_to_turn(pending_request_in, pending_response, tool_result_request=None))

        return turns

    def assemble_replay(self, events: list[RunContextEvent]) -> list[ModelMessage]:
        """Reconstruct PydanticAI messages from ordered context events."""
        messages: list[ModelMessage] = []
        current_request_parts: list[Any] = []
        current_response_parts: list[Any] = []

        for event in events:
            if event.event_type in ("system_prompt", "user_message"):
                current_request_parts.append(_to_pydantic_request_part(event))
            elif event.event_type in ("thinking", "assistant_text", "tool_call"):
                if current_request_parts and not current_response_parts:
                    messages.append(ModelRequest(parts=current_request_parts))
                    current_request_parts = []
                current_response_parts.append(_to_pydantic_response_part(event))
            elif event.event_type == "tool_result":
                if current_response_parts:
                    messages.append(ModelResponse(parts=current_response_parts))
                    current_response_parts = []
                current_request_parts.append(_to_pydantic_request_part(event))

        if current_response_parts:
            messages.append(ModelResponse(parts=current_response_parts))

        return messages


def _to_turn(
    request_in: ModelRequest | None,
    response: ModelResponse,
    tool_result_request: ModelRequest | None,
) -> GenerationTurn:
    raw_resp = _make_json_safe(dataclasses.asdict(response))
    return GenerationTurn(
        messages_in=_extract_request_parts(request_in) if request_in else [],
        response_parts=_extract_response_parts(response),
        tool_results=_extract_tool_results(tool_result_request) if tool_result_request else [],
        turn_logprobs=extract_logprobs(raw_resp),
    )


def extract_logprobs(raw: dict[str, Any]) -> list[TokenLogprob] | None:
    """Extract per-token logprobs from a PydanticAI response dump."""
    details = raw.get("provider_details")
    if not isinstance(details, dict):
        return None
    raw_logprobs = details.get("logprobs")
    if not isinstance(raw_logprobs, list) or not raw_logprobs:
        return None
    return [
        TokenLogprob(
            token=entry["token"],
            logprob=entry["logprob"],
            top_logprobs=entry.get("top_logprobs", []),
        )
        for entry in raw_logprobs
        if isinstance(entry, dict) and "token" in entry and "logprob" in entry
    ]


def _to_pydantic_response_part(event: RunContextEvent) -> Any:  # slopcop: ignore[no-typing-any]
    parsed = event.parsed_payload()
    if event.event_type == "thinking":
        if not isinstance(parsed, ThinkingPayload):
            raise ValueError(f"Expected ThinkingPayload for thinking event, got {type(parsed)}")
        return PydanticThinkingPart(content=parsed.text)
    if event.event_type == "assistant_text":
        if not isinstance(parsed, AssistantTextPayload):
            raise ValueError(f"Expected AssistantTextPayload for assistant_text event, got {type(parsed)}")
        return PydanticTextPart(content=parsed.text)
    if event.event_type == "tool_call":
        if not isinstance(parsed, ToolCallPayload):
            raise ValueError(f"Expected ToolCallPayload for tool_call event, got {type(parsed)}")
        return PydanticToolCallPart(
            tool_name=parsed.tool_name,
            tool_call_id=parsed.tool_call_id,
            args=parsed.args,
        )
    raise ValueError(f"Unexpected response event_type: {event.event_type!r}")


def _to_pydantic_request_part(event: RunContextEvent) -> Any:  # slopcop: ignore[no-typing-any]
    parsed = event.parsed_payload()
    if event.event_type == "system_prompt":
        if not isinstance(parsed, SystemPromptPayload):
            raise ValueError(f"Expected SystemPromptPayload for system_prompt event, got {type(parsed)}")
        return PydanticSystemPromptPart(content=parsed.text)
    if event.event_type == "user_message":
        if not isinstance(parsed, UserMessagePayload):
            raise ValueError(f"Expected UserMessagePayload for user_message event, got {type(parsed)}")
        return PydanticUserPromptPart(content=parsed.text)
    if event.event_type == "tool_result":
        if not isinstance(parsed, ToolResultPayload):
            raise ValueError(f"Expected ToolResultPayload for tool_result event, got {type(parsed)}")
        return PydanticToolReturnPart(
            tool_call_id=parsed.tool_call_id,
            tool_name=parsed.tool_name,
            content=str(parsed.result),
        )
    raise ValueError(f"Unexpected request event_type: {event.event_type!r}")


def _extract_request_parts(request: ModelRequest) -> list[Any]:  # slopcop: ignore[no-typing-any]
    parts: list[Any] = []  # slopcop: ignore[no-typing-any]
    for part in request.parts:
        if isinstance(part, PydanticSystemPromptPart):
            parts.append(SystemPromptPart(content=part.content))
        elif isinstance(part, PydanticUserPromptPart) and isinstance(part.content, str):
            parts.append(UserPromptPart(content=part.content))
    return parts


def _extract_response_parts(response: ModelResponse) -> list[Any]:  # slopcop: ignore[no-typing-any]
    parts: list[Any] = []  # slopcop: ignore[no-typing-any]
    for part in response.parts:
        if isinstance(part, PydanticTextPart):
            parts.append(TextPart(content=part.content))
        elif isinstance(part, PydanticToolCallPart):
            parts.append(
                ToolCallPart(
                    tool_name=part.tool_name,
                    tool_call_id=part.tool_call_id,
                    args=part.args_as_dict(),
                )
            )
        elif isinstance(part, PydanticThinkingPart):
            parts.append(ThinkingPart(content=part.content))
    return parts


def _extract_tool_results(request: ModelRequest) -> list[ToolReturnPart]:
    results: list[ToolReturnPart] = []
    for part in request.parts:
        if isinstance(part, PydanticToolReturnPart):
            content = part.content
            serialized = content if isinstance(content, str) else json.dumps(content, default=str)
            results.append(
                ToolReturnPart(
                    tool_call_id=part.tool_call_id,
                    tool_name=part.tool_name,
                    content=serialized,
                )
            )
    return results


def _make_json_safe(obj: Any) -> Any:  # slopcop: ignore[no-typing-any]
    from datetime import datetime

    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_safe(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return obj
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```bash
pytest tests/unit/builtins/common/test_transcript_adapters.py -q
```

Expected: PASS.

- [ ] **Step 5: Update old generation-turn tests to import the new utility**

Modify `tests/unit/state/test_generation_turn_build.py`:

```python
from ergon_builtins.common.llm_context.adapters.pydantic_ai import PydanticAITranscriptAdapter


def _build_turns(messages):
    return PydanticAITranscriptAdapter().build_turns(messages)
```

Remove the old import from `ergon_builtins.workers.baselines.react_worker`.

- [ ] **Step 6: Run the old and new transcript tests together**

Run:

```bash
pytest tests/unit/state/test_generation_turn_build.py tests/unit/builtins/common/test_transcript_adapters.py -q
```

Expected: PASS.

---

## Task 3: Simplify `ReActWorker`

**Files:**

- Modify: `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`
- Test: `tests/unit/workers/test_react_worker_contract.py`

- [ ] **Step 1: Add a contract test that transcript helpers no longer live in `react_worker.py`**

Modify `tests/unit/workers/test_react_worker_contract.py`:

```python
def test_pydantic_ai_transcript_adapter_lives_outside_worker() -> None:
    import ergon_builtins.workers.baselines.react_worker as react_worker

    assert not hasattr(react_worker, "_build_turns")
    assert not hasattr(react_worker, "_extract_request_parts")
    assert not hasattr(react_worker, "_extract_response_parts")
    assert not hasattr(react_worker, "_extract_tool_results")
```

- [ ] **Step 2: Run the contract test and verify it fails**

Run:

```bash
pytest tests/unit/workers/test_react_worker_contract.py -q
```

Expected: FAIL because helper functions still exist in `react_worker.py`.

- [ ] **Step 3: Update `ReActWorker` imports**

In `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`, remove imports that are only used by transcript parsing:

```python
import dataclasses  # remove
from ergon_core.api.generation import SystemPromptPart, TextPart, ThinkingPart, ToolCallPart, ToolReturnPart, UserPromptPart  # remove
from ergon_core.api.json_types import JsonObject  # remove if only used for model_settings type
from ergon_core.core.providers.generation.pydantic_ai_format import extract_logprobs  # remove
from ergon_core.core.rl import LOGPROB_SETTINGS  # remove
from pydantic_ai.messages import ModelRequest, ModelResponse  # remove
from pydantic_ai.messages import SystemPromptPart as PydanticSystemPromptPart  # remove
from pydantic_ai.messages import TextPart as PydanticTextPart  # remove
from pydantic_ai.messages import ThinkingPart as PydanticThinkingPart  # remove
from pydantic_ai.messages import ToolCallPart as PydanticToolCallPart  # remove
from pydantic_ai.messages import ToolReturnPart as PydanticToolReturnPart  # remove
from pydantic_ai.messages import UserPromptPart as PydanticUserPromptPart  # remove
```

Add:

```python
from ergon_builtins.common.llm_context.capture_settings import build_capture_model_settings
from ergon_builtins.common.llm_context.adapters.pydantic_ai import PydanticAITranscriptAdapter
```

- [ ] **Step 4: Update model settings and transcript extraction**

Replace:

```python
model_settings: JsonObject | None = None
if resolved.supports_logprobs and self.model and self.model.startswith("vllm:"):
    model_settings = LOGPROB_SETTINGS
```

with:

```python
model_settings = build_capture_model_settings(self.model, resolved)
```

Replace:

```python
turns = _build_turns(run.ctx.state.message_history)
```

with:

```python
turns = PydanticAITranscriptAdapter().build_turns(run.ctx.state.message_history)
```

- [ ] **Step 5: Delete transcript helper functions from `react_worker.py`**

Delete the helper block that starts at:

```python
# ---------------------------------------------------------------------------
# PydanticAI message → GenerationTurn
# ---------------------------------------------------------------------------
```

Keep `_format_task` and `_latest_final_result_message` in `react_worker.py` because they are worker behavior, not PydanticAI transcript parsing.

- [ ] **Step 6: Run contract and worker tests**

Run:

```bash
pytest tests/unit/workers/test_react_worker_contract.py tests/unit/state/test_generation_turn_build.py tests/unit/builtins/common/test_capture_settings.py tests/unit/builtins/common/test_transcript_adapters.py -q
```

Expected: PASS.

---

## Task 4: Persist `GenerationTurn.tool_results`

**Files:**

- Modify: `ergon_core/ergon_core/core/persistence/context/repository.py`
- Test: `tests/unit/persistence/test_context_event_repository.py`

- [ ] **Step 1: Write a failing repository test**

Create `tests/unit/persistence/test_context_event_repository.py`:

```python
from uuid import UUID

import pytest
from ergon_core.api.generation import GenerationTurn, ToolCallPart, ToolReturnPart, UserPromptPart
from ergon_core.core.persistence.context.repository import ContextEventRepository
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution
from ergon_core.core.persistence.shared.ids import new_id
from sqlmodel import Session


@pytest.mark.asyncio
async def test_persist_turn_records_tool_results_from_tool_results(session: Session) -> None:
    run_id = new_id()
    execution_id = new_id()

    session.add(RunRecord(id=run_id, experiment_id=UUID(int=1), name="test", status="running"))
    session.add(
        RunTaskExecution(
            id=execution_id,
            run_id=run_id,
            definition_task_id=UUID(int=2),
            node_id=UUID(int=3),
            attempt_number=1,
            status="running",
        )
    )
    session.commit()

    repo = ContextEventRepository()
    events = await repo.persist_turn(
        session,
        run_id=run_id,
        execution_id=execution_id,
        worker_binding_key="worker",
        turn=GenerationTurn(
            messages_in=[UserPromptPart(content="search")],
            response_parts=[
                ToolCallPart(tool_name="search", tool_call_id="call-1", args={"query": "ergon"})
            ],
            tool_results=[
                ToolReturnPart(tool_name="search", tool_call_id="call-1", content="found")
            ],
        ),
    )

    assert [event.event_type for event in events] == ["user_message", "tool_call", "tool_result"]
    tool_result = events[-1].parsed_payload()
    assert tool_result.event_type == "tool_result"
    assert tool_result.tool_name == "search"
    assert tool_result.tool_call_id == "call-1"
    assert tool_result.result == "found"
```

If the project uses a differently named DB fixture than `session`, adapt only the fixture name and setup rows to the existing test harness. Keep the assertion shape unchanged.

- [ ] **Step 2: Run the focused repository test and verify it fails**

Run:

```bash
pytest tests/unit/persistence/test_context_event_repository.py -q
```

Expected: FAIL because `_events_from_tool_results` currently scans `turn.messages_in`, not `turn.tool_results`.

- [ ] **Step 3: Update `_events_from_tool_results`**

In `ergon_core/ergon_core/core/persistence/context/repository.py`, replace the loop source:

```python
for part in turn.messages_in:
```

with a helper that prefers `turn.tool_results` and preserves compatibility with old/custom workers:

```python
tool_result_parts = [
    *turn.tool_results,
    *(part for part in turn.messages_in if isinstance(part, ToolReturnPart)),
]
for part in tool_result_parts:
```

Update the docstring to:

```python
"""Produce tool_result events from GenerationTurn tool observations."""
```

- [ ] **Step 4: Run the focused repository test and verify it passes**

Run:

```bash
pytest tests/unit/persistence/test_context_event_repository.py -q
```

Expected: PASS.

---

## Task 5: Add End-to-End Unit Coverage for ReAct Capture Shape

**Files:**

- Modify or create: `tests/unit/builtins/common/test_transcript_adapters.py`
- Modify or create: `tests/unit/persistence/test_context_event_repository.py`

- [ ] **Step 1: Add a combined transcript-to-event regression**

Add a test that builds PydanticAI messages, converts them to `GenerationTurn`, persists the first turn, and asserts event types:

```python
@pytest.mark.asyncio
async def test_pydantic_ai_tool_observation_becomes_context_event(session: Session) -> None:
    from ergon_builtins.common.llm_context.adapters.pydantic_ai import PydanticAITranscriptAdapter

    turns = PydanticAITranscriptAdapter().build_turns(
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
                        content="found",
                    )
                ]
            ),
        ]
    )

    events = await repo.persist_turn(
        session,
        run_id=run_id,
        execution_id=execution_id,
        worker_binding_key="worker",
        turn=turns[0],
    )

    assert [event.event_type for event in events] == ["user_message", "tool_call", "tool_result"]
```

Use the same DB setup helper from Task 4. This test is intentionally redundant: it protects the integration boundary where the current bug occurred.

- [ ] **Step 2: Add a thinking regression**

Add a test with `ThinkingPart(content="let me think")` in the PydanticAI response, then persist the resulting turn and assert a `thinking` context event appears before `assistant_text`:

```python
assert [event.event_type for event in events] == ["user_message", "thinking", "assistant_text"]
```

- [ ] **Step 3: Run the combined tests**

Run:

```bash
pytest tests/unit/builtins/common/test_transcript_adapters.py tests/unit/persistence/test_context_event_repository.py -q
```

Expected: PASS.

---

## Task 6: Verification Against a Real LLM Smoke Run

**Files:**

- No code changes required.
- Optional inspection command only.

- [ ] **Step 1: Run a small real LLM benchmark using a reasoning-capable model**

Use the repo's existing real-LLM harness or CLI with a cheap one-task run. Prefer a model target already used by the repo, such as:

```bash
pytest tests/real_llm/benchmarks/test_researchrubrics.py -q
```

If the real-LLM test is intentionally skipped because credentials or budget are unavailable, record that skip in the implementation summary.

- [ ] **Step 2: Inspect the run snapshot for richer context events**

For a known run id, inspect event counts:

```bash
RUN_ID=<run-id-from-smoke-run> python - <<'PY'
import json, urllib.request
import os

run_id = os.environ["RUN_ID"]
with urllib.request.urlopen(f"http://127.0.0.1:3002/api/runs/{run_id}", timeout=5) as r:
    data = json.load(r)

counts = {}
for events in (data.get("contextEventsByTask") or {}).values():
    for event in events:
        counts[event.get("eventType")] = counts.get(event.get("eventType"), 0) + 1

print(counts)
PY
```

Expected for a tool-using run: `tool_result` count is non-zero. Expected for a provider/model that returns thinking: `thinking` count is non-zero.

Do not fail the implementation if `thinking` is zero for a provider that does not return thoughts despite the request. Do fail if tool-using ReAct runs still have zero `tool_result` events.

---

## Task 7: Final Test Pass

**Files:**

- No code changes unless tests reveal a regression.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
pytest tests/unit/builtins/common/test_capture_settings.py tests/unit/builtins/common/test_transcript_adapters.py tests/unit/persistence/test_context_event_repository.py tests/unit/state/test_generation_turn_build.py tests/unit/workers/test_react_worker_contract.py -q
```

Expected: PASS.

- [ ] **Step 2: Run lints for edited Python files**

Run the repo's standard Python lint/type command if available. If the repo does not expose a single lint command, at minimum run:

```bash
python -m compileall ergon_builtins/ergon_builtins/common ergon_builtins/ergon_builtins/workers/baselines ergon_core/ergon_core/core/persistence/context
```

Expected: PASS.

- [ ] **Step 3: Record implementation notes**

In the implementation summary, include:

- Whether `tool_result` is now persisted from `GenerationTurn.tool_results`.
- Which provider settings were added for thinking/reasoning.
- Whether real-LLM verification produced `thinking` events or only verified `tool_result`.
- Any provider-specific caveat, especially Anthropic thinking plus structured output behavior.

---

## Acceptance Criteria

- ReAct worker no longer owns PydanticAI message parsing internals.
- PydanticAI transcript extraction is reusable by other PydanticAI-based workers.
- Real ReAct workers pass capture-oriented model settings when the provider supports thinking/reasoning/logprobs.
- `ContextEventRepository.persist_turn` writes `tool_result` rows from `GenerationTurn.tool_results`.
- A tool-using ReAct run can be inspected through `GET /api/runs/{run_id}` and shows non-zero `tool_result` events.
- Thinking blocks are persisted as `thinking` events when the provider returns PydanticAI `ThinkingPart` objects.

