"""Streaming SWE-bench candidate-buffering example."""

from __future__ import annotations

import asyncio

from ergon_builtins.agents.react.worker import ReActWorker
from ergon_builtins.benchmarks.swebench_verified.dataset import iter_swebench_rows
from ergon_builtins.benchmarks.swebench_verified.prompts import SWEBENCH_SYSTEM_PROMPT
from ergon_builtins.benchmarks.swebench_verified.rubric import SWEBenchRubric
from ergon_builtins.benchmarks.swebench_verified.sandbox import SWEBenchSandbox
from ergon_builtins.benchmarks.swebench_verified.sample import make_swebench_sample
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
from ergon_core.api import Environment, Experiment, RandomSampler
from experiment_api._shared import prepare_experiment_runtime


async def main() -> None:
    worker = ReActWorker(
        name="swebench-solver",
        model="openai:gpt-4o",
        system_prompt=SWEBENCH_SYSTEM_PROMPT,
        max_iterations=50,
        toolkit=SWEBenchToolkit(),
    )
    env = Environment.from_dataset(
        name="swebench-train",
        dataset=iter_swebench_rows(split="train", streaming=True),
        source_mode="streaming",
        make_sample=lambda row: make_swebench_sample(
            row,
            environment_name="swebench-train",
            split="train",
            worker=worker,
            evaluators=[SWEBenchRubric(name="swebench-rubric")],
            sandbox=SWEBenchSandbox(),
        ),
    )
    experiment = Experiment(name="swebench-streaming-buffer", environments=[env])
    prepare_experiment_runtime()
    result = await experiment.submit(
        k=8,
        candidate_pool_size=32,
        sampler=RandomSampler(seed=0),
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
