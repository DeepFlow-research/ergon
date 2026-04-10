"""Stub worker that produces synthetic GenerationTurn data for RL testing.

Unlike stub-worker (which returns a plain string with no turns), this
worker generates fake token-level data that exercises the full trajectory
extraction pipeline: RunGenerationTurn persistence, logprob storage,
and rollout_func return formatting.

Use with ``--worker training-stub`` for CPU-only integration tests of
the RL training loop.
"""

import random

from ergon_core.api import BenchmarkTask, Worker, WorkerContext, WorkerResult
from ergon_core.api.generation import GenerationTurn, TokenLogprob


class TrainingStubWorker(Worker):
    type_slug = "training-stub"

    def __init__(self, *, name: str = "training-stub", model: str | None = None) -> None:
        self.name = name
        self.model = model

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> WorkerResult:
        turns = _build_synthetic_turns(task.task_key)

        return WorkerResult(
            output=f"Training stub output for {task.task_key}",
            success=True,
            turns=turns,
            metadata={"task_key": task.task_key, "model": self.model, "synthetic": True},
        )


def _build_synthetic_turns(task_key: str) -> list[GenerationTurn]:
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

        tool_results: list[dict] = []
        if i < num_turns - 1:
            tool_results = [
                {
                    "tool_call_id": f"call_{i}",
                    "tool_name": "stub_tool",
                    "result": f"Tool result for turn {i} of {task_key}",
                }
            ]

        turns.append(
            GenerationTurn(
                raw_request={"messages": [{"role": "user", "content": f"Turn {i} prompt"}]},
                raw_response={
                    "parts": [{"part_kind": "text", "content": f"Synthetic response turn {i}"}],
                    "provider_details": {"logprobs": [lp.model_dump() for lp in logprobs]},
                },
                tool_results=tool_results,
                logprobs=logprobs,
                policy_version="synthetic-v0",
            )
        )

    return turns
