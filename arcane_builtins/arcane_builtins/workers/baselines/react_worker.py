"""ReAct-style worker using pydantic-ai Agent for tool-augmented execution."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from h_arcane.api import BenchmarkTask, Worker, WorkerContext, WorkerResult
from pydantic import BaseModel

try:
    from pydantic_ai import Agent
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        RetryPromptPart,
        TextPart,
        ThinkingPart,
        ToolCallPart,
        ToolReturnPart,
    )

    _HAS_PYDANTIC_AI = True
except ImportError:
    _HAS_PYDANTIC_AI = False


class _AgentOutput(BaseModel):
    """Structured output the ReAct agent returns at the end of a run."""

    output_text: str
    reasoning: str | None = None


class ReActWorker(Worker):
    """ReAct-style worker that delegates to a pydantic-ai Agent.

    The agent iterates over tool calls (Reasoning → Action → Observation) until
    it produces a final answer or hits *max_iterations*.
    """

    type_slug = "react-v1"

    def __init__(
        self,
        *,
        name: str,
        model: str | None = None,
        tools: list[Any] | None = None,
        system_prompt: str = "",
        max_iterations: int = 10,
    ) -> None:
        super().__init__(name=name, model=model)
        self.tools: list[Any] = tools or []
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> WorkerResult:
        if not _HAS_PYDANTIC_AI:
            return WorkerResult(
                output="pydantic-ai is not installed",
                success=False,
                metadata={"error": "missing_dependency"},
            )

        agent: Agent[None, _AgentOutput] = Agent(
            model=self.model or "openai:gpt-4o",
            instructions=self.system_prompt or None,
            tools=self.tools,
            output_type=_AgentOutput,
        )

        task_prompt = self._format_task(task)
        actions: list[dict[str, Any]] = []
        started_at = datetime.now(timezone.utc)

        try:
            node_count = 0
            async with agent.iter(task_prompt) as run:
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
            actions = self._extract_actions(messages)
            output_text = (
                result.output.output_text
                if isinstance(result.output, _AgentOutput)
                else str(result.output)
            )
            reasoning = result.output.reasoning if isinstance(result.output, _AgentOutput) else None

        except Exception as exc:
            elapsed_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
            return WorkerResult(
                output=f"Agent execution failed: {exc}",
                success=False,
                artifacts={"actions": actions},
                metadata={"error": str(exc), "elapsed_ms": elapsed_ms},
            )

        elapsed_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
        return WorkerResult(
            output=output_text,
            success=True,
            artifacts={"actions": actions, "reasoning": reasoning},
            metadata={
                "model": self.model,
                "node_count": node_count,
                "action_count": len(actions),
                "elapsed_ms": elapsed_ms,
            },
        )

    def _format_task(self, task: BenchmarkTask) -> str:
        lines = [f"Task: {task.description}"]
        if task.task_payload:
            lines.append("")
            lines.append(f"Payload: {json.dumps(task.task_payload, default=str)}")
        return "\n".join(lines)

    def _extract_actions(self, messages: list[Any]) -> list[dict[str, Any]]:
        """Walk pydantic-ai messages and extract a flat action log."""
        if not _HAS_PYDANTIC_AI:
            return []

        actions: list[dict[str, Any]] = []
        pending: dict[str, dict[str, Any]] = {}

        for message in messages:
            ts = getattr(message, "timestamp", None) or datetime.now(timezone.utc)
            ts_iso = ts.isoformat() if isinstance(ts, datetime) else str(ts)

            if isinstance(message, ModelResponse):
                for part in message.parts:
                    if isinstance(part, ToolCallPart):
                        pending[part.tool_call_id] = {
                            "tool_name": part.tool_name,
                            "input": self._safe_serialize(part.args),
                            "started_at": ts_iso,
                        }
                    elif isinstance(part, TextPart):
                        actions.append({
                            "action_type": "message",
                            "output": part.content,
                            "timestamp": ts_iso,
                        })
                    elif isinstance(part, ThinkingPart):
                        actions.append({
                            "action_type": "reasoning",
                            "output": part.content,
                            "timestamp": ts_iso,
                        })

            elif isinstance(message, ModelRequest):
                for req_part in message.parts:
                    if isinstance(req_part, ToolReturnPart):
                        call_info = pending.pop(req_part.tool_call_id, {})
                        actions.append({
                            "action_type": call_info.get("tool_name", req_part.tool_name),
                            "input": call_info.get("input", ""),
                            "output": self._safe_serialize(req_part.content),
                            "started_at": call_info.get("started_at", ts_iso),
                            "completed_at": ts_iso,
                        })
                    elif isinstance(req_part, RetryPromptPart):
                        actions.append({
                            "action_type": "retry_prompt",
                            "output": self._safe_serialize(req_part.content),
                            "timestamp": ts_iso,
                        })

        return actions

    @staticmethod
    def _safe_serialize(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, BaseModel):
            return json.dumps(value.model_dump(), default=str)
        try:
            return json.dumps(value, default=str)
        except (TypeError, ValueError):
            return str(value)
