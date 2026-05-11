"""Stub worker that produces synthetic context chunk data for RL testing.

Unlike stub-worker (which returns a plain string with no turns), this
worker generates fake token-level data that exercises the full trajectory
extraction pipeline: RunContextEvent persistence, logprob storage,
and rollout_func return formatting.

Use with ``--worker training-stub`` for CPU-only integration tests of
the RL training loop.
"""

import random
from collections.abc import AsyncGenerator

from ergon_core.api import Task, Worker, WorkerContext, WorkerOutput, WorkerStreamItem
from ergon_core.core.domain.generation.context_parts import (
    AssistantTextPart,
    ContextPartChunk,
    TokenLogprob,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)


class TrainingStubWorker(Worker):
    type_slug = "training-stub"

    def __init__(
        self,
        *,
        name: str = "training-stub",
        model: str | None,
    ) -> None:
        super().__init__(name=name, model=model)

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        output = ""
        for chunk in _build_synthetic_chunks(task.task_slug):
            if isinstance(chunk.part, AssistantTextPart):
                output = chunk.part.content
            yield chunk
        yield WorkerOutput(output=output, success=True)


def _build_synthetic_chunks(task_slug: str) -> list[ContextPartChunk]:
    """Generate 2-3 fake turns worth of chunks with synthetic logprobs."""
    num_turns = random.randint(2, 3)
    chunks: list[ContextPartChunk] = [
        ContextPartChunk(part=UserMessagePart(content=f"Task: Synthetic task {task_slug}"))
    ]

    for i in range(num_turns):
        num_tokens = random.randint(8, 16)
        logprobs = [
            TokenLogprob(
                token=f"tok_{j}",
                logprob=-random.uniform(0.1, 3.0),
            )
            for j in range(num_tokens)
        ]

        is_last = i == num_turns - 1
        if not is_last:
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
        else:
            chunks.append(
                ContextPartChunk(
                    part=AssistantTextPart(content=f"Synthetic response turn {i}"),
                    logprobs=logprobs,
                )
            )

    return chunks
