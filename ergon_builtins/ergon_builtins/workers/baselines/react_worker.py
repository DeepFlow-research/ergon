# ergon_builtins/ergon_builtins/workers/baselines/react_worker.py
"""ReAct-style worker using pydantic-ai Agent for tool-augmented execution."""

import json
import logging
from collections.abc import AsyncGenerator, Callable
from types import NoneType
from typing import Any, ClassVar, cast
from uuid import UUID

from ergon_core.api import Task, Worker, WorkerContext, WorkerOutput, WorkerStreamItem
from ergon_core.core.domain.generation.context_parts import (
    AssistantTextPart,
    ContextPartChunk,
    ToolCallPart,
)
from ergon_core.core.application.context.events import ContextEventService
from pydantic import BaseModel, Field, PrivateAttr
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

    All wiring (system prompt, iteration budget) is declared as Pydantic
    fields so the worker round-trips through ``task_json`` snapshots.
    The ``tools`` field is excluded from serialization — registry
    factories populate it at runtime by closing over the sandbox; see
    e.g. ``MiniF2FReactWorker.execute`` which builds tools from a
    sandbox-bound toolkit before delegating to ``super().execute``.
    """

    type_slug: ClassVar[str] = "react-v1"

    system_prompt: str | None = None
    max_iterations: int = 10
    # `_tools` and `_seed_messages` are runtime-only state — they hold
    # references to callables/pydantic-ai SDK objects that are not
    # round-trippable through model_dump/model_validate. PrivateAttr
    # keeps them out of the Pydantic field surface entirely.
    _tools: list[AgentTool] = PrivateAttr(default_factory=list)
    _seed_messages: list[ModelMessage] | None = PrivateAttr(default=None)

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
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
                tools=self._tools,
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


def _format_task(task: Task) -> str:
    lines = [f"Task: {task.description}"]
    payload = task.task_payload.model_dump(mode="json")
    if payload:
        lines.append("")
        lines.append(f"Payload: {json.dumps(payload, default=str)}")
    return "\n".join(lines)
