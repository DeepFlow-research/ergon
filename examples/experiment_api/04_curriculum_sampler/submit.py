"""Custom sampler example that prefers easier samples from a larger pool."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from ergon_builtins.environments import MiniF2FEnvironment
from ergon_core.api import Experiment, RandomSampler, Sample, SamplingContext
from experiment_api._shared import experiment_submission_service


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
    env = MiniF2FEnvironment(name="mini-validation", split="validation", limit=64)
    experiment = Experiment(name="mini-curriculum", environments=[env])
    result = await experiment.submit(
        service=experiment_submission_service(),
        k=16,
        candidate_pool_size=64,
        sampler=EasyFirstSampler(seed=0),
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
