"""Smallest complete MiniF2F experiment submission example."""

from __future__ import annotations

import asyncio

from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
from ergon_builtins.benchmarks.minif2f.worker_factory import (
    make_minif2f_rubric,
    make_minif2f_worker,
)
from ergon_builtins.environments import MiniF2FEnvironment
from ergon_core.api import Experiment, RandomSampler
from experiment_api._shared import experiment_submission_service


async def main() -> None:
    worker = make_minif2f_worker(model="openai:gpt-4o")
    env = MiniF2FEnvironment(
        name="mini-validation",
        split="validation",
        limit=10,
        worker=worker,
        evaluators=[make_minif2f_rubric()],
        sandbox=LeanSandbox(),
    )
    experiment = Experiment(name="mini-validation-smoke", environments=[env])
    result = await experiment.submit(
        service=experiment_submission_service(),
        k=10,
        sampler=RandomSampler(seed=0),
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
