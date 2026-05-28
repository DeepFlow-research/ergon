"""Heterogeneous training-style experiment with four builtin environments."""

from __future__ import annotations

import asyncio

from ergon_builtins.agents.react.worker import ReActWorker
from ergon_builtins.benchmarks.gdpeval.dataset import load_gdpeval_rows
from ergon_builtins.benchmarks.gdpeval.prompts import GDPEVAL_SYSTEM_PROMPT
from ergon_builtins.benchmarks.gdpeval.rubric import StagedRubric
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandbox
from ergon_builtins.benchmarks.gdpeval.sample import make_gdpeval_sample
from ergon_builtins.benchmarks.gdpeval.toolkit import GDPEvalToolkit
from ergon_builtins.benchmarks.minif2f.dataset import load_minif2f_rows
from ergon_builtins.benchmarks.minif2f.prompts import MINIF2F_SYSTEM_PROMPT
from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
from ergon_builtins.benchmarks.minif2f.sample import make_minif2f_sample
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit
from ergon_builtins.benchmarks.researchrubrics.dataset import load_researchrubrics_rows
from ergon_builtins.benchmarks.researchrubrics.prompts import RESEARCH_SYSTEM_PROMPT
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.sandbox import ResearchE2BSandbox
from ergon_builtins.benchmarks.researchrubrics.sample import make_researchrubrics_sample
from ergon_builtins.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit
from ergon_builtins.benchmarks.swebench_verified.dataset import iter_swebench_rows
from ergon_builtins.benchmarks.swebench_verified.prompts import SWEBENCH_SYSTEM_PROMPT
from ergon_builtins.benchmarks.swebench_verified.rubric import SWEBenchRubric
from ergon_builtins.benchmarks.swebench_verified.sandbox import SWEBenchSandbox
from ergon_builtins.benchmarks.swebench_verified.sample import make_swebench_sample
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
from ergon_core.api import Environment, Experiment, RandomSampler
from experiment_api._shared import experiment_submission_service


async def main() -> None:
    mini_worker = ReActWorker(
        name="mini-proof-solver",
        model="openai:gpt-4o",
        system_prompt=MINIF2F_SYSTEM_PROMPT,
        max_iterations=30,
        toolkit=MiniF2FToolkit(),
    )
    research_worker = ReActWorker(
        name="research-runner",
        model="openai:gpt-4o",
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        max_iterations=16,
        toolkit=ResearchRubricsToolkit(),
    )
    gdp_worker = ReActWorker(
        name="gdpeval-runner",
        model="openai:gpt-4o",
        system_prompt=GDPEVAL_SYSTEM_PROMPT,
        max_iterations=40,
        toolkit=GDPEvalToolkit(),
    )
    swe_worker = ReActWorker(
        name="swebench-solver",
        model="openai:gpt-4o",
        system_prompt=SWEBENCH_SYSTEM_PROMPT,
        max_iterations=50,
        toolkit=SWEBenchToolkit(),
    )
    experiment = Experiment(
        name="generalist-mixed-training",
        environments=[
            Environment.from_records(
                name="mini-validation",
                records=load_minif2f_rows(split="validation", limit=10),
                make_sample=lambda row: make_minif2f_sample(
                    row,
                    environment_name="mini-validation",
                    split="validation",
                    worker=mini_worker,
                    evaluators=[MiniF2FRubric(name="minif2f-proof")],
                    sandbox=LeanSandbox(),
                ),
            ),
            Environment.from_records(
                name="research-validation",
                records=load_researchrubrics_rows(split="validation", limit=10),
                make_sample=lambda row: make_researchrubrics_sample(
                    row,
                    environment_name="research-validation",
                    split="validation",
                    worker=research_worker,
                    evaluators=[ResearchRubricsRubric(name="researchrubrics-rubric")],
                    sandbox=ResearchE2BSandbox(),
                ),
            ),
            Environment.from_records(
                name="gdp-validation",
                records=load_gdpeval_rows(split="validation", limit=10),
                make_sample=lambda row: make_gdpeval_sample(
                    row,
                    environment_name="gdp-validation",
                    split="validation",
                    worker=gdp_worker,
                    evaluators=[
                        StagedRubric(
                            name="gdpeval-staged-rubric",
                            category_name="default",
                            max_total_score=1.0,
                        )
                    ],
                    sandbox=GDPEvalSandbox(),
                ),
            ),
            Environment.from_dataset(
                name="swebench-train",
                dataset=iter_swebench_rows(split="train", limit=100, streaming=True),
                source_mode="streaming",
                make_sample=lambda row: make_swebench_sample(
                    row,
                    environment_name="swebench-train",
                    split="train",
                    worker=swe_worker,
                    evaluators=[SWEBenchRubric(name="swebench-rubric")],
                    sandbox=SWEBenchSandbox(),
                ),
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
