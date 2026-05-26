"""Heterogeneous training-style experiment with four builtin environments."""

from __future__ import annotations

import asyncio

from ergon_builtins.benchmarks.gdpeval.benchmark import _default_gdpeval_sandbox
from ergon_builtins.benchmarks.gdpeval.worker_factory import (
    make_gdpeval_rubric,
    make_gdpeval_worker,
)
from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
from ergon_builtins.benchmarks.minif2f.worker_factory import make_minif2f_rubric
from ergon_builtins.benchmarks.researchrubrics.benchmark import _default_research_sandbox
from ergon_builtins.benchmarks.researchrubrics.worker_factory import make_research_rubric
from ergon_builtins.benchmarks.swebench_verified.benchmark import _default_swebench_sandbox
from ergon_builtins.benchmarks.swebench_verified.worker_factory import make_swebench_rubric
from ergon_builtins.environments import (
    GDPEvalEnvironment,
    MiniF2FEnvironment,
    ResearchRubricsEnvironment,
    SweBenchVerifiedEnvironment,
)
from ergon_core.api import Experiment, RandomSampler
from experiment_api._shared import experiment_submission_service


async def main() -> None:
    worker = make_gdpeval_worker(model="openai:gpt-4o")
    experiment = Experiment(
        name="generalist-mixed-training",
        environments=[
            MiniF2FEnvironment(
                name="mini-validation",
                split="validation",
                limit=10,
                worker=worker,
                evaluators=[make_minif2f_rubric()],
                sandbox=LeanSandbox(),
            ),
            ResearchRubricsEnvironment(
                name="research-validation",
                split="validation",
                limit=10,
                worker=worker,
                evaluators=[make_research_rubric()],
                sandbox=_default_research_sandbox(),
            ),
            GDPEvalEnvironment(
                name="gdp-validation",
                split="validation",
                limit=10,
                worker=worker,
                evaluators=[make_gdpeval_rubric()],
                sandbox=_default_gdpeval_sandbox(),
            ),
            SweBenchVerifiedEnvironment(
                name="swebench-train",
                split="train",
                streaming=True,
                limit=100,
                worker=worker,
                evaluators=[make_swebench_rubric()],
                sandbox=_default_swebench_sandbox(),
            ),
        ],
    )
    result = await experiment.submit(
        service=experiment_submission_service(),
        k=32,
        candidate_pool_size=128,
        sampler=RandomSampler(seed=0),
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
