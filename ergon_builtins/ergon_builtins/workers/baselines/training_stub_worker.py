"""Stub worker that produces synthetic GenerationTurn data for RL testing.

Unlike stub-worker (which returns a plain string with no turns), this
worker generates fake token-level data that exercises the full trajectory
extraction pipeline: RunContextEvent persistence, logprob storage,
and rollout_func return formatting.

Use with ``--worker training-stub`` for CPU-only integration tests of
the RL training loop.
"""

import random
from collections.abc import AsyncGenerator
from typing import cast
from uuid import UUID

from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import (
    GenerationTurn,
    ModelRequestPart,
    ModelResponsePart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from ergon_core.core.providers.generation.types import TokenLogprob


class TrainingStubWorker(Worker):
    type_slug = "training-stub"

    def __init__(
        self,
        *,
        name: str = "training-stub",
        model: str | None,
        task_id: UUID,
        sandbox_id: str,
    ) -> None:
        super().__init__(name=name, model=model, task_id=task_id, sandbox_id=sandbox_id)

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        for turn in _build_synthetic_turns(task.task_slug):
            yield turn


def _build_synthetic_turns(task_slug: str) -> list[GenerationTurn]:
    """Generate 2-3 fake turns with synthetic logprobs."""
    num_turns = random.randint(2, 3)
    turns: list[GenerationTurn] = []

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
            response_parts = cast(
                list[ModelResponsePart],
                [
                    ToolCallPart(
                        tool_name="stub_tool",
                        tool_call_id=f"call_{i}",
                        args={"turn": i, "task": task_slug},
                    )
                ],
            )
            tool_results = [
                ToolReturnPart(
                    tool_call_id=f"call_{i}",
                    tool_name="stub_tool",
                    content=f"Tool result for turn {i} of {task_slug}",
                )
            ]
        else:
            response_parts = cast(
                list[ModelResponsePart],
                [TextPart(content=f"Synthetic response turn {i}")],
            )
            tool_results = []

        messages_in: list[ModelRequestPart] = (
            [UserPromptPart(content=f"Task: Synthetic task {task_slug}")] if i == 0 else []
        )

        turns.append(
            GenerationTurn(
                messages_in=messages_in,
                response_parts=response_parts,
                tool_results=tool_results,
                turn_logprobs=logprobs,
                policy_version="synthetic-v0",
            )
        )

    return turns
