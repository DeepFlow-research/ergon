# ergon_builtins/ergon_builtins/workers/baselines/react_worker.py
"""ReAct-style worker using pydantic-ai Agent for tool-augmented execution."""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any, Self
from uuid import UUID

from ergon_builtins.common.llm_context.adapters.pydantic_ai import PydanticAITranscriptAdapter
from ergon_builtins.models.resolution import resolve_model_target
from ergon_core.api import BenchmarkTask, Tool, Worker, WorkerContext, WorkerOutput
from ergon_core.api.generation import GenerationTurn
from ergon_core.core.persistence.context.repository import ContextEventRepository
from ergon_core.core.persistence.shared.db import get_session

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
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
            model_settings=resolved.capture_model_settings,
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
        turns = PydanticAITranscriptAdapter().build_turns(run.ctx.state.message_history)
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
        worker._seed_messages = PydanticAITranscriptAdapter().assemble_replay(events)
        return worker


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
        try:
            event_type = event.event_type
        except AttributeError:
            continue
        if event_type != "tool_call":
            continue
        payload = event.parsed_payload()
        if not isinstance(payload, payload_type) or payload.tool_name != "final_result":
            continue
        messages.append(str(payload.args.get("final_assistant_message", "")))
    return messages[-1] if messages else ""
