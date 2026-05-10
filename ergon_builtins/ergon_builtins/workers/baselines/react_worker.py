# ergon_builtins/ergon_builtins/workers/baselines/react_worker.py
"""ReAct-style worker using pydantic-ai Agent for tool-augmented execution."""

import json
import logging
from collections.abc import AsyncGenerator, Callable
from types import NoneType
from typing import Any, Self, cast
from uuid import UUID

from ergon_core.api import Sandbox, Task, Worker, WorkerContext, WorkerOutput, WorkerStreamItem
from ergon_core.core.domain.generation.context_parts import (
    AssistantTextPart,
    ContextPartChunk,
    ToolCallPart,
)
from ergon_core.core.application.context.events import ContextEventService
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.tools import Tool
from sqlmodel import Session

from ergon_builtins.common.llm_context.adapters.pydantic_ai import (
    PydanticAITranscriptAdapter,
    TranscriptTurnCursor,
)
from ergon_builtins.models.resolution import resolve_model_target
from ergon_builtins.observability.pydantic_ai_logfire import configure_pydantic_ai_logfire
from pydantic import PrivateAttr

logger = logging.getLogger(__name__)

AgentTool = Tool[object] | Callable[..., object]


class _AgentOutput(BaseModel):
    """Structured output the ReAct agent returns at the end of a run."""

    final_assistant_message: str
    reasoning: str | None = None


class ReActWorker(Worker):
    """ReAct-style worker that delegates to a pydantic-ai Agent.

    Yields ``ContextPartChunk`` objects as the PydanticAI transcript grows. Each
    yielded chunk is enriched and persisted by the runtime.

    All wiring (tool list, system prompt, iteration budget) is supplied
    at construction time — the worker is framework-agnostic. Registry
    factories build per-benchmark instances by closing over the sandbox
    and passing a concrete toolkit through ``tools=``.
    """

    type_slug = "react-v1"

    tools: list[Any]  # slopcop: ignore[no-typing-any]
    system_prompt: str | None
    max_iterations: int
    _seed_messages: list[ModelMessage] | None = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        name: str,
        model: str | None,
        tools: list[AgentTool],
        system_prompt: str | None,
        max_iterations: int,
    ) -> None:
        super().__init__(
            name=name,
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            max_iterations=max_iterations,
        )

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        async for chunk in self._run_agent(task, context):
            yield chunk

    def build_agent_deps(
        self, context: WorkerContext
    ) -> Any | None:  # slopcop: ignore[no-typing-any]
        return None

    async def _run_agent(
        self,
        task: Task,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        """Run the underlying pydantic-ai agent and yield the chunks it produced."""
        resolved = resolve_model_target(self.model)
        configure_pydantic_ai_logfire()
        agent_deps = self.build_agent_deps(context)
        deps_type = type(agent_deps) if agent_deps is not None else NoneType

        agent = cast(
            "Agent[Any, _AgentOutput]",
            Agent(
                model=resolved.model,
                instructions=self.system_prompt or None,
                tools=self.tools,
                output_type=_AgentOutput,
                deps_type=cast(type[Any], deps_type),
            ),
        )

        task_prompt = _format_task(task)
        node_count = 0
        adapter = PydanticAITranscriptAdapter()
        cursor = TranscriptTurnCursor()
        emitted_chunks: list[ContextPartChunk] = []
        run = None

        try:
            async with agent.iter(
                task_prompt,
                model_settings=resolved.capture_model_settings,
                message_history=self._seed_messages,
                deps=agent_deps,
            ) as active_run:
                run = active_run
                async for _node in run:
                    node_count += 1
                    for chunk in adapter.build_new_chunks(
                        run.ctx.state.message_history,
                        cursor,
                        flush_pending=False,
                    ):
                        emitted_chunks.append(chunk)
                        yield chunk
                    if node_count >= self.max_iterations:
                        logger.warning(
                            "ReActWorker hit max_iterations=%d; persisting partial turns",
                            self.max_iterations,
                        )
                        for chunk in adapter.build_new_chunks(
                            run.ctx.state.message_history,
                            cursor,
                            flush_pending=True,
                        ):
                            emitted_chunks.append(chunk)
                            yield chunk
                        raise RuntimeError(
                            f"ReActWorker exceeded max_iterations={self.max_iterations}"
                        )
        except Exception:  # slopcop: ignore[no-broad-except]
            if run is not None:
                for chunk in adapter.build_new_chunks(
                    run.ctx.state.message_history,
                    cursor,
                    flush_pending=True,
                ):
                    emitted_chunks.append(chunk)
                    yield chunk
            raise

        if run is not None:
            for chunk in adapter.build_new_chunks(
                run.ctx.state.message_history,
                cursor,
                flush_pending=True,
            ):
                emitted_chunks.append(chunk)
                yield chunk

        yield _worker_output_from_chunks(emitted_chunks)

    @classmethod
    def from_buffer(
        cls,
        execution_id: UUID,
        session: Session,
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> Self | None:
        """Return a ReActWorker pre-seeded with context event history."""
        repo = ContextEventService()
        events = repo.get_for_execution(session, execution_id)
        if not events:
            return None
        worker = cls(**kwargs)
        worker._seed_messages = PydanticAITranscriptAdapter().assemble_replay(events)
        return worker


def _format_task(task: Task) -> str:
    lines = [f"Task: {task.description}"]
    payload = task.task_payload.model_dump(mode="json")
    if payload:
        lines.append("")
        lines.append(f"Payload: {json.dumps(payload, default=str)}")
    return "\n".join(lines)


def _worker_output_from_chunks(chunks: list[ContextPartChunk]) -> WorkerOutput:
    output = _latest_final_result_message(chunks)
    if output:
        return WorkerOutput(output=output, success=True)

    text_parts = [
        chunk.part.content for chunk in chunks if isinstance(chunk.part, AssistantTextPart)
    ]
    if text_parts:
        return WorkerOutput(output=text_parts[-1], success=True)

    return WorkerOutput(output="", success=False)


def _latest_final_result_message(chunks: list[ContextPartChunk]) -> str:
    """Extract fallback text from the latest ``final_result`` tool call."""
    messages: list[str] = []
    for chunk in chunks:
        part = chunk.part
        if not isinstance(part, ToolCallPart) or part.tool_name != "final_result":
            continue
        messages.append(str(part.args.get("final_assistant_message", "")))
    return messages[-1] if messages else ""
