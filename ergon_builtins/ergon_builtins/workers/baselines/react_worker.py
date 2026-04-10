"""ReAct-style worker using pydantic-ai Agent for tool-augmented execution."""

import dataclasses  # slopcop: ignore[no-dataclass]
import json
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolReturnPart,
)

from ergon_core.api import BenchmarkTask, Worker, WorkerContext, WorkerResult
from ergon_core.api.generation import GenerationTurn
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

    Produces ``GenerationTurn`` records from PydanticAI's native message
    history — no format conversion.
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

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> WorkerResult:
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
        started_at = datetime.now(timezone.utc)

        try:
            node_count = 0
            async with agent.iter(task_prompt, model_settings=model_settings) as run:
                async for _node in run:
                    node_count += 1
                    if node_count >= self.max_iterations:
                        break
                result = run.result

            if result is None:
                return WorkerResult(
                    output="Agent run ended without producing a result",
                    success=False,
                    metadata={"node_count": node_count},
                )

            messages = result.new_messages()
            turns = _build_turns(messages)
            output_text = (
                result.output.output_text
                if isinstance(result.output, _AgentOutput)
                else str(result.output)
            )
            reasoning = result.output.reasoning if isinstance(result.output, _AgentOutput) else None

        except Exception as exc:  # slopcop: ignore[no-broad-except]
            elapsed_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
            return WorkerResult(
                output=f"Agent execution failed: {exc}",
                success=False,
                metadata={"error": str(exc), "elapsed_ms": elapsed_ms},
            )

        elapsed_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)

        return WorkerResult(
            output=output_text,
            success=True,
            turns=turns,
            artifacts={"reasoning": reasoning},
            metadata={
                "model": self.model,
                "node_count": node_count,
                "turn_count": len(turns),
                "elapsed_ms": elapsed_ms,
                "policy_version": resolved.policy_version,
            },
        )


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
    pending_request: ModelRequest | None = None

    for message in messages:
        if isinstance(message, ModelResponse):
            if pending is not None:
                turns.append(_to_turn(pending, pending_request, []))
            pending = message
            pending_request = None
        elif isinstance(message, ModelRequest):
            if pending is not None:
                tool_results = _extract_tool_results(message)
                turns.append(_to_turn(pending, pending_request, tool_results))
                pending = None
            pending_request = message

    if pending is not None:
        turns.append(_to_turn(pending, pending_request, []))

    return turns


def _to_turn(
    response: ModelResponse,
    request: ModelRequest | None,
    tool_results: list[dict[str, Any]],  # slopcop: ignore[no-typing-any]
) -> GenerationTurn:
    raw_resp = _make_json_safe(dataclasses.asdict(response))
    raw_req = _make_json_safe(dataclasses.asdict(request)) if request is not None else None
    return GenerationTurn(
        raw_request=raw_req,
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
