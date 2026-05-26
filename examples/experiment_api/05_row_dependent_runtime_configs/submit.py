"""Row-dependent worker, evaluator, and sandbox selection example."""

from __future__ import annotations

import asyncio

from ergon_builtins.benchmarks.swebench_verified.benchmark import _default_swebench_sandbox
from ergon_builtins.benchmarks.swebench_verified.sandbox import SWEBenchSandbox
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchInstance
from ergon_builtins.benchmarks.swebench_verified.worker_factory import (
    make_swebench_rubric,
    make_swebench_worker,
)
from ergon_builtins.environments import SweBenchVerifiedEnvironment
from ergon_core.api import Evaluator, Experiment, RandomSampler, Sandbox, Worker
from experiment_api._shared import experiment_submission_service


def worker_for_row(row: SWEBenchInstance) -> Worker:
    if row.repo.startswith("django/"):
        return make_swebench_worker(model="openai:gpt-4o")
    return make_swebench_worker(model="openai:gpt-4o-mini")


def evaluators_for_row(row: SWEBenchInstance) -> list[Evaluator]:
    del row
    return [make_swebench_rubric()]


def sandbox_for_row(row: SWEBenchInstance) -> Sandbox:
    if row.repo.startswith("django/"):
        return SWEBenchSandbox()
    return _default_swebench_sandbox()


async def main() -> None:
    env = SweBenchVerifiedEnvironment(
        name="swebench-row-dependent",
        split="train",
        streaming=True,
        limit=100,
        worker=worker_for_row,
        evaluators=evaluators_for_row,
        sandbox=sandbox_for_row,
    )
    experiment = Experiment(name="row-dependent-runtime-configs", environments=[env])
    result = await experiment.submit(
        service=experiment_submission_service(),
        k=8,
        candidate_pool_size=32,
        sampler=RandomSampler(seed=0),
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
