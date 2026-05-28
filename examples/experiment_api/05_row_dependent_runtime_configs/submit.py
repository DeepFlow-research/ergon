"""Row-dependent worker, evaluator, and sandbox selection example."""

from __future__ import annotations

import asyncio

from ergon_builtins.agents.react.worker import ReActWorker
from ergon_builtins.benchmarks.swebench_verified.dataset import iter_swebench_rows
from ergon_builtins.benchmarks.swebench_verified.prompts import SWEBENCH_SYSTEM_PROMPT
from ergon_builtins.benchmarks.swebench_verified.rubric import SWEBenchRubric
from ergon_builtins.benchmarks.swebench_verified.sandbox import SWEBenchSandbox
from ergon_builtins.benchmarks.swebench_verified.sample import make_swebench_sample
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchInstance
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
from ergon_core.api import Environment, Evaluator, Experiment, RandomSampler, Sandbox, Worker
from experiment_api._shared import prepare_experiment_runtime


def worker_for_row(row: SWEBenchInstance) -> Worker:
    model = "openai:gpt-4o" if row.repo.startswith("django/") else "openai:gpt-4o-mini"
    return ReActWorker(
        name="swebench-solver",
        model=model,
        system_prompt=SWEBENCH_SYSTEM_PROMPT,
        max_iterations=50,
        toolkit=SWEBenchToolkit(),
    )


def evaluators_for_row(row: SWEBenchInstance) -> list[Evaluator]:
    del row
    return [SWEBenchRubric(name="swebench-rubric")]


def sandbox_for_row(row: SWEBenchInstance) -> Sandbox:
    del row
    return SWEBenchSandbox()


async def main() -> None:
    env = Environment.from_dataset(
        name="swebench-row-dependent",
        dataset=iter_swebench_rows(split="train", streaming=True, limit=100),
        source_mode="streaming",
        make_sample=lambda row: make_swebench_sample(
            row,
            environment_name="swebench-row-dependent",
            split="train",
            worker=worker_for_row(row),
            evaluators=evaluators_for_row(row),
            sandbox=sandbox_for_row(row),
        ),
    )
    experiment = Experiment(name="row-dependent-runtime-configs", environments=[env])
    prepare_experiment_runtime()
    result = await experiment.submit(
        k=8,
        candidate_pool_size=32,
        sampler=RandomSampler(seed=0),
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
