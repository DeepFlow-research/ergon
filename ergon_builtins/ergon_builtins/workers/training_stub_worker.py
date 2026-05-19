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
from hashlib import sha256
from typing import ClassVar

from ergon_core.api import Task, Worker, WorkerContext, WorkerOutput, WorkerStreamItem
from ergon_core.core.shared.context_parts import (
    AssistantTextPart,
    ContextPartChunk,
    TokenLogprob,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)


class TrainingStubWorker(Worker):
    type_slug: ClassVar[str] = "training-stub"
    name: str = "training-stub"
    seed: int = 0
    min_turns: int = 2
    max_turns: int = 3
    min_tokens: int = 8
    max_tokens: int = 16

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        output = ""
        for chunk in _build_synthetic_chunks(
            task.task_slug,
            seed=self.seed,
            min_turns=self.min_turns,
            max_turns=self.max_turns,
            min_tokens=self.min_tokens,
            max_tokens=self.max_tokens,
        ):
            if isinstance(chunk.part, AssistantTextPart):
                output = chunk.part.content
            yield chunk
        yield WorkerOutput(output=output, success=True)


def _build_synthetic_chunks(
    task_slug: str,
    *,
    seed: int = 0,
    min_turns: int = 2,
    max_turns: int = 3,
    min_tokens: int = 8,
    max_tokens: int = 16,
) -> list[ContextPartChunk]:
    """Generate 2-3 fake turns worth of chunks with synthetic logprobs."""
    rng = random.Random(_task_seed(seed, task_slug))
    num_turns = rng.randint(min_turns, max_turns)
    chunks: list[ContextPartChunk] = [
        ContextPartChunk(part=UserMessagePart(content=f"Task: Synthetic task {task_slug}"))
    ]

    for i in range(num_turns):
        num_tokens = rng.randint(min_tokens, max_tokens)
        logprobs = [
            TokenLogprob(
                token=f"tok_{j}",
                logprob=-rng.uniform(0.1, 3.0),
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


def _task_seed(seed: int, task_slug: str) -> int:
    digest = sha256(f"{seed}:{task_slug}".encode()).digest()
    return int.from_bytes(digest[:8], "big")
