"""Streaming SWE-bench candidate-buffering example."""

from __future__ import annotations

import asyncio

from ergon_builtins.benchmarks.swebench_verified.benchmark import _default_swebench_sandbox
from ergon_builtins.benchmarks.swebench_verified.worker_factory import (
    make_swebench_rubric,
    make_swebench_worker,
)
from ergon_builtins.environments import SweBenchVerifiedEnvironment
from ergon_core.api import Experiment, RandomSampler
from experiment_api._shared import experiment_submission_service


async def main() -> None:
    env = SweBenchVerifiedEnvironment(
        name="swebench-train",
        split="train",
        streaming=True,
        worker=make_swebench_worker(model="openai:gpt-4o"),
        evaluators=[make_swebench_rubric()],
        sandbox=_default_swebench_sandbox(),
    )
    experiment = Experiment(name="swebench-streaming-buffer", environments=[env])
    result = await experiment.submit(
        service=experiment_submission_service(),
        k=8,
        candidate_pool_size=32,
        sampler=RandomSampler(seed=0),
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
