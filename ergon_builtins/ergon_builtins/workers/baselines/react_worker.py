"""ReAct-style worker using pydantic-ai Agent for tool-augmented execution."""

import dataclasses  # slopcop: ignore[no-dataclass]
import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolReturnPart,
)

from ergon_core.api import BenchmarkTask, Worker, WorkerContext, WorkerOutput
from ergon_core.api.generation import GenerationTurn
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.providers.generation.pydantic_ai_format import extract_logprobs
from ergon_core.core.providers.generation.model_resolution import resolve_model_target
from ergon_core.core.rl import LOGPROB_SETTINGS

logger = logging.getLogger(__name__)


class _AgentOutput(BaseModel):
    """Structured output the ReAct agent returns at the end of a run."""

    output_text: str
    reasoning: str | None = None


class ReActWorker(Worker):
    """ReAct-style worker that delegates to a pydantic-ai Agent.

    Yields ``GenerationTurn`` objects incrementally during execution.
    Each yielded turn is persisted to PG immediately by the runtime.
    """

    type_slug = "react-v1"

    def __init__(
        self,
        *,
        name: str,
        model: str | None = None,
        tools: list[Any] | None = None,  # slopcop: ignore[no-typing-any]
        system_prompt: str | None = None,
        max_iterations: int = 10,
    ) -> None:
        super().__init__(name=name, model=model)
        self.tools: list[Any] = tools or []  # slopcop: ignore[no-typing-any]
        self.system_prompt: str | None = system_prompt
        self.max_iterations = max_iterations
        self._seed_messages: list[ModelMessage] | None = None

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
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
        turn_count = 0
        prev_message_count = 0

        async with agent.iter(task_prompt, model_settings=model_settings) as run:
            async for _node in run:
                node_count += 1

                current_messages = run.result.new_messages() if run.result else []
                if len(current_messages) > prev_message_count:
                    new_turns = _build_turns(current_messages[prev_message_count:])
                    for turn in new_turns:
                        if turn_count == 0:
                            turn = turn.model_copy(update={"prompt_text": task_prompt})
                        yield turn
                        turn_count += 1
                    prev_message_count = len(current_messages)

                if node_count >= self.max_iterations:
                    break

    def get_output(self, context: WorkerContext) -> WorkerOutput:
        """Extract structured _AgentOutput from the last turn's raw_response."""
        with get_session() as session:
            turns = self._turn_repo.get_for_execution(session, context.execution_id)
        if not turns:
            return WorkerOutput(output="", success=False)
        last_turn = turns[-1]
        output_text = _extract_agent_output_text(last_turn.raw_response)
        return WorkerOutput(
            output=output_text,
            success=True,
            metadata={"turn_count": len(turns), "model": self.model},
        )

    @classmethod
    def from_buffer(
        cls,
        turns: list[GenerationTurn],
        task: BenchmarkTask,
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> Self | None:
        """Return a ReActWorker pre-seeded with PydanticAI message history."""
        worker = cls(**kwargs)
        worker._seed_messages = []
        for turn in turns:
            worker._seed_messages.append(
                ModelResponse(**turn.raw_response)
            )  # ty: ignore[invalid-argument-type]
        return worker


# ---------------------------------------------------------------------------
# PydanticAI message → GenerationTurn
# ---------------------------------------------------------------------------


def _format_task(task: BenchmarkTask) -> str:
    lines = [f"Task: {task.description}"]
    if task.task_payload:
        lines.append("")
        lines.append(f"Payload: {json.dumps(task.task_payload, default=str)}")
    return "\n".join(lines)


def _build_turns(messages: list[ModelMessage]) -> list[GenerationTurn]:
    """Build ``GenerationTurn`` objects from PydanticAI message history."""
    turns: list[GenerationTurn] = []
    pending: ModelResponse | None = None

    for message in messages:
        if isinstance(message, ModelResponse):
            if pending is not None:
                turns.append(_to_turn(pending, []))
            pending = message
        elif isinstance(message, ModelRequest):
            if pending is not None:
                tool_results = _extract_tool_results(message)
                turns.append(_to_turn(pending, tool_results))
                pending = None

    if pending is not None:
        turns.append(_to_turn(pending, []))

    return turns


def _to_turn(
    response: ModelResponse,
    tool_results: list[dict[str, Any]],  # slopcop: ignore[no-typing-any]
) -> GenerationTurn:
    raw_resp = _make_json_safe(dataclasses.asdict(response))
    return GenerationTurn(
        raw_response=raw_resp,
        tool_results=tool_results,
        logprobs=extract_logprobs(raw_resp),
    )


def _make_json_safe(obj: Any) -> Any:  # slopcop: ignore[no-typing-any]
    """Recursively convert non-JSON-serializable types (datetime, bytes, etc.) to strings."""
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_safe(v) for v in obj]
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return obj


def _extract_tool_results(
    request: ModelRequest,
) -> list[dict[str, Any]]:  # slopcop: ignore[no-typing-any]
    results: list[dict[str, Any]] = []  # slopcop: ignore[no-typing-any]
    for part in request.parts:
        if isinstance(part, ToolReturnPart):
            content = part.content
            serialized = content if isinstance(content, str) else json.dumps(content, default=str)
            results.append(
                {
                    "tool_call_id": part.tool_call_id,
                    "tool_name": part.tool_name,
                    "result": serialized,
                }
            )
    return results


def _extract_agent_output_text(raw_response: dict) -> str:
    """Extract the output_text from PydanticAI's structured _AgentOutput response."""
    parts = raw_response.get("parts", [])
    for part in parts:
        if isinstance(part, dict) and part.get("part_kind") == "text":
            return part.get("content", "")
    return str(raw_response)
