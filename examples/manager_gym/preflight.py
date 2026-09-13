"""Verify catalog composition and real role schemas through the configured gateway.

Run inside the normal API container after `ergon doctor`. This makes bounded
internal model requests, then writes only configuration and usage receipts.
The separate contract stage verifies E2B, scheduling, messaging and grading.
"""

import argparse
import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path

from ergon_builtins.benchmarks.manager_gym.actions import ManagerDecision
from ergon_builtins.benchmarks.manager_gym.baselines import BulkDecision
from ergon_builtins.benchmarks.manager_gym.inference import (
    inference_profile,
    INTERNAL_MODEL,
    infer,
    require_internal_model,
)
from ergon_builtins.benchmarks.manager_gym.manager import Decomposition
from ergon_builtins.benchmarks.manager_gym.outputs import (
    AITaskOutput,
    HumanWorkOutput,
    HumanTimeEstimation,
)
from ergon_builtins.benchmarks.manager_gym.rubric import JudgeOutput, definitions
from ergon_builtins.benchmarks.manager_gym.scenario_catalog import SCENARIOS
from ergon_builtins.benchmarks.manager_gym.state import (
    EpisodeConfig,
    SOURCE_REVISION,
    BENCHMARK_VERSION,
    new_episode,
    all_tasks,
)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=INTERNAL_MODEL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require_internal_model(args.model)
    for key in ("E2B_API_KEY", "ERGON_OPENAI_COMPATIBLE_API_KEY"):
        if not os.environ.get(key):
            raise ValueError(f"Missing configured secret: {key}")
    cases = [
        (ManagerDecision, "Choose get_workflow_status with reasoning as the one manager action."),
        (
            AITaskOutput,
            "Create one two-sentence legal hold note resource with name, description and inline content; omit resource id.",
        ),
        (
            HumanWorkOutput,
            "As records manager create one short legal hold note resource. Omit resource id. Include work process and quality notes.",
        ),
        (HumanTimeEstimation, "Estimate hours to write a two-sentence legal hold note."),
        (
            Decomposition,
            "Decompose writing a legal hold procedure into three subtasks with executive summary, implementation plan and acceptance criteria.",
        ),
        (
            JudgeOutput,
            "Score out of 10: All records must be retained until counsel releases the hold. Criterion: requires retention pending counsel release.",
        ),
        (
            BulkDecision,
            "Assign task 00000000-0000-0000-0000-000000000001 to ai_writer, giving reasoning and one assignments entry.",
        ),
    ]
    receipts = []
    for schema, prompt in cases:
        result = await infer(
            model=args.model,
            system="Follow the requested structured output contract.",
            prompt=prompt,
            output_type=schema,
        )
        receipts.append(
            {
                "schema": schema.__name__,
                "passed": True,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "elapsed_seconds": result.elapsed_seconds,
            }
        )
    counts = []
    for scenario in SCENARIOS:
        state = new_episode(EpisodeConfig(scenario=scenario))
        tasks = all_tasks(state.workflow)
        counts.append(
            {
                "scenario": scenario,
                "nodes": len(tasks),
                "leaves": sum(not t.subtasks for t in tasks.values()),
                "terminal_criteria": len(definitions(scenario)),
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "observed_at": datetime.now(UTC).isoformat(),
                "inference_profile": inference_profile(),
                "model": args.model,
                "source_revision": SOURCE_REVISION,
                "benchmark_version": BENCHMARK_VERSION,
                "roles": receipts,
                "scenarios": counts,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        f"Validated {len(cases)} model schemas and {len(counts)} scenario compositions: {args.output}"
    )


if __name__ == "__main__":
    asyncio.run(main())
