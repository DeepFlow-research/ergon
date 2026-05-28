"""Custom sampler example that prefers easier samples from a larger pool."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from ergon_builtins.agents.react.worker import ReActWorker
from ergon_builtins.benchmarks.minif2f.dataset import load_minif2f_rows
from ergon_builtins.benchmarks.minif2f.prompts import MINIF2F_SYSTEM_PROMPT
from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
from ergon_builtins.benchmarks.minif2f.sample import make_minif2f_sample
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit
from ergon_core.api import Environment, Experiment, RandomSampler, Sample, SamplingContext
from experiment_api._shared import prepare_experiment_runtime


class EasyFirstSampler(RandomSampler):
    name: str = "easy-first"

    async def select(
        self,
        *,
        samples: Sequence[Sample],
        k: int,
        context: SamplingContext,
    ) -> Sequence[Sample]:
        del k, context
        return sorted(samples, key=_difficulty_key)


def _difficulty_key(sample: Sample) -> tuple[int, str]:
    difficulty = sample.metadata.get("difficulty", 0)
    if isinstance(difficulty, int):
        score = difficulty
    elif isinstance(difficulty, float):
        score = int(difficulty)
    elif isinstance(difficulty, str):
        score = int(difficulty)
    else:
        score = 0
    return (score, sample.sample_key)


async def main() -> None:
    worker = ReActWorker(
        name="mini-proof-solver",
        model="openai:gpt-4o",
        system_prompt=MINIF2F_SYSTEM_PROMPT,
        max_iterations=30,
        toolkit=MiniF2FToolkit(),
    )
    env = Environment.from_records(
        name="mini-validation",
        records=load_minif2f_rows(split="validation", limit=64),
        make_sample=lambda row: make_minif2f_sample(
            row,
            environment_name="mini-validation",
            split="validation",
            worker=worker,
            evaluators=[MiniF2FRubric(name="minif2f-proof")],
            sandbox=LeanSandbox(),
        ),
    )
    experiment = Experiment(name="mini-curriculum", environments=[env])
    prepare_experiment_runtime()
    result = await experiment.submit(
        k=16,
        candidate_pool_size=64,
        sampler=EasyFirstSampler(seed=0),
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
