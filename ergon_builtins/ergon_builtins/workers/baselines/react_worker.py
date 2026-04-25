# ergon_builtins/ergon_builtins/workers/baselines/react_worker.py
"""ReAct-style worker using pydantic-ai Agent for tool-augmented execution."""

import dataclasses  # slopcop: ignore[no-dataclass]
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any, Self
from uuid import UUID

from ergon_core.api import BenchmarkTask, Tool, Worker, WorkerContext, WorkerOutput
from ergon_core.api.generation import (
    GenerationTurn,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from ergon_core.core.persistence.context.assembly import assemble_pydantic_ai_messages
from ergon_core.core.persistence.context.repository import ContextEventRepository
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.providers.generation.model_resolution import resolve_model_target
from ergon_core.core.providers.generation.pydantic_ai_format import extract_logprobs
from ergon_core.core.rl import LOGPROB_SETTINGS

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
)
from pydantic_ai.messages import (
    SystemPromptPart as PydanticSystemPromptPart,
)
from pydantic_ai.messages import (
    TextPart as PydanticTextPart,
)
from pydantic_ai.messages import (
    ThinkingPart as PydanticThinkingPart,
)
from pydantic_ai.messages import (
    ToolCallPart as PydanticToolCallPart,
)
from pydantic_ai.messages import (
    ToolReturnPart as PydanticToolReturnPart,
)
from pydantic_ai.messages import (
    UserPromptPart as PydanticUserPromptPart,
)
from sqlmodel import Session

logger = logging.getLogger(__name__)


class _AgentOutput(BaseModel):
    """Structured output the ReAct agent returns at the end of a run."""

    final_assistant_message: str
    reasoning: str | None = None


class ReActWorker(Worker):
    """ReAct-style worker that delegates to a pydantic-ai Agent.

    Yields ``GenerationTurn`` objects after the run completes. Each
    yielded turn is persisted to PG by the runtime.

    All wiring (tool list, system prompt, iteration budget) is supplied
    at construction time — the worker is framework-agnostic. Registry
    factories build per-benchmark instances by closing over the sandbox
    and passing a concrete toolkit through ``tools=``.
    """

    type_slug = "react-v1"

    def __init__(
        self,
        *,
        name: str,
        model: str | None,
        task_id: UUID,
        sandbox_id: str,
        tools: list[Tool],
        system_prompt: str | None,
        max_iterations: int,
    ) -> None:
        super().__init__(name=name, model=model, task_id=task_id, sandbox_id=sandbox_id)
        self.tools: list[Tool] = tools
        self.system_prompt: str | None = system_prompt
        self.max_iterations: int = max_iterations
        self._seed_messages: list[ModelMessage] | None = None

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        async for turn in self._run_agent(task):
            yield turn

    async def _run_agent(
        self,
        task: BenchmarkTask,
    ) -> AsyncGenerator[GenerationTurn, None]:
        """Run the underlying pydantic-ai agent and yield the turns it produced."""
        resolved = resolve_model_target(self.model)

        model_settings: dict[str, object] | None = None
        if resolved.supports_logprobs and self.model and self.model.startswith("vllm:"):
            model_settings = LOGPROB_SETTINGS

        agent: Agent[None, _AgentOutput] = Agent(
            model=resolved.model,
            instructions=self.system_prompt or None,
            tools=self.tools,
            output_type=_AgentOutput,
        )

        task_prompt = _format_task(task)
        node_count = 0

        async with agent.iter(
            task_prompt,
            model_settings=model_settings,
            message_history=self._seed_messages,
        ) as run:
            async for _node in run:
                node_count += 1
                if node_count >= self.max_iterations:
                    logger.warning(
                        "ReActWorker hit max_iterations=%d; persisting partial turns",
                        self.max_iterations,
                    )
                    break

        # Build all turns from the complete message history after the run.
        # Using ctx.state.message_history (not incremental slices) ensures tool_results
        # are correctly paired with their generating ModelResponse.
        # Works for both complete and partial (max_iterations) runs —
        # pydantic-ai 0.7.x moved all_messages() to AgentRunResult, but
        # ctx.state.message_history is always populated incrementally.
        turns = _build_turns(run.ctx.state.message_history)
        for turn in turns:
            yield turn

    def get_output(self, context: WorkerContext) -> WorkerOutput:
        """Extract the agent's text output from the last context event."""
        return self._base_output(context)

    def _base_output(self, context: WorkerContext) -> WorkerOutput:
        """Build the worker's output from persisted context events."""
        # reason: avoid circular import at module level
        from ergon_core.core.persistence.context.event_payloads import (
            AssistantTextPayload,
            ThinkingPayload,
            ToolCallPayload,
        )

        with get_session() as session:
            repo = ContextEventRepository()
            events = repo.get_for_execution(session, context.execution_id)
        turn_ids: set[str] = set()
        for e in events:
            payload = e.parsed_payload()
            if isinstance(payload, (AssistantTextPayload, ToolCallPayload, ThinkingPayload)):
                turn_ids.add(payload.turn_id)

        text_events = [e for e in events if e.event_type == "assistant_text"]
        if not text_events:
            output = _latest_final_result_message(events, ToolCallPayload)
            if not output:
                return WorkerOutput(output="", success=False)
            return WorkerOutput(
                output=output,
                success=bool(output),
                metadata={"turn_count": len(turn_ids)},
            )
        last = text_events[-1].parsed_payload()
        if not isinstance(last, AssistantTextPayload):
            raise ValueError(f"Expected AssistantTextPayload, got {type(last)}")
        return WorkerOutput(
            output=last.text,
            success=True,
            metadata={"turn_count": len(turn_ids)},
        )

    @classmethod
    def from_buffer(
        cls,
        execution_id: UUID,
        session: Session,
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> Self | None:
        """Return a ReActWorker pre-seeded with context event history."""
        repo = ContextEventRepository()
        events = repo.get_for_execution(session, execution_id)
        if not events:
            return None
        worker = cls(**kwargs)
        worker._seed_messages = assemble_pydantic_ai_messages(events)
        return worker


# ---------------------------------------------------------------------------
# PydanticAI message → GenerationTurn
# ---------------------------------------------------------------------------


def _format_task(task: BenchmarkTask) -> str:
    lines = [f"Task: {task.description}"]
    payload = task.task_payload.model_dump(mode="json")
    if payload:
        lines.append("")
        lines.append(f"Payload: {json.dumps(payload, default=str)}")
    return "\n".join(lines)


def _latest_final_result_message(
    events: list[Any],  # slopcop: ignore[no-typing-any]
    payload_type: type[Any],  # slopcop: ignore[no-typing-any]
) -> str:
    """Extract fallback text from the latest ``final_result`` tool call."""
    messages: list[str] = []
    for event in events:
        if getattr(event, "event_type", None) != "tool_call":
            continue
        payload = event.parsed_payload()
        if not isinstance(payload, payload_type) or payload.tool_name != "final_result":
            continue
        messages.append(str(payload.args.get("final_assistant_message", "")))
    return messages[-1] if messages else ""


def _build_turns(messages: list[ModelMessage]) -> list[GenerationTurn]:
    """Build GenerationTurn objects from a complete PydanticAI message list.

    Caller must pass the full message history — NOT incremental slices.
    Using incremental slices causes tool_results to always be empty because
    ToolReturnParts appear in the *next* ModelRequest, which is not in the slice.
    """
    turns: list[GenerationTurn] = []
    pending_response: ModelResponse | None = None
    pending_request_in: ModelRequest | None = None

    for message in messages:
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


def _extract_request_parts(request: ModelRequest) -> list[Any]:  # slopcop: ignore[no-typing-any]
    parts: list[Any] = []  # slopcop: ignore[no-typing-any]
    for part in request.parts:
        if isinstance(part, PydanticSystemPromptPart):
            parts.append(SystemPromptPart(content=part.content))
        elif isinstance(part, PydanticUserPromptPart) and isinstance(part.content, str):
            parts.append(UserPromptPart(content=part.content))
        # ToolReturnParts are extracted separately as tool_results — skip here
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
    # reason: avoid polluting module namespace with stdlib datetime
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
