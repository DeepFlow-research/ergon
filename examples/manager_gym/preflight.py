"""Check that a model target can play every Manager Gym role before a full run.

Makes one bounded request per role output schema plus a tool round trip, composes
every scenario offline, and writes a JSON receipt with token usage. Run it inside
the API container after `ergon doctor`.
"""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ergon_builtins.benchmarks.manager_gym.actions import ManagerDecision
from ergon_builtins.benchmarks.manager_gym.baselines import BulkDecision
from ergon_builtins.benchmarks.manager_gym.inference import InferenceProfile, Role, infer
from ergon_builtins.benchmarks.manager_gym.manager import Decomposition
from ergon_builtins.benchmarks.manager_gym.outputs import (
    AITaskOutput,
    HumanTimeEstimation,
    HumanWorkOutput,
)
from ergon_builtins.benchmarks.manager_gym.rubric import JudgeOutput, definitions
from ergon_builtins.benchmarks.manager_gym.state import (
    BENCHMARK_VERSION,
    SOURCE_REVISION,
    EpisodeConfig,
    all_tasks,
    new_episode,
)
from ergon_builtins.benchmarks.manager_gym.upstream import SCENARIOS
from pydantic import BaseModel


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=os.environ.get("ERGON_MAG_MODEL"),
        required=not os.environ.get("ERGON_MAG_MODEL"),
        help="Ergon model target for every role and the judge (default: $ERGON_MAG_MODEL).",
    )
    parser.add_argument(
        "--thinking-token-budget",
        type=int,
        help="Reasoning token cap for thinking models served by vLLM.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get("E2B_API_KEY"):
        raise ValueError("Missing E2B_API_KEY; Manager Gym work runs in E2B sandboxes")
    profile = InferenceProfile(thinking_token_budget=args.thinking_token_budget)
    cases: list[tuple[type[BaseModel], Role, str]] = [
        (
            ManagerDecision,
            "manager",
            "Choose get_workflow_status with reasoning as the one manager action.",
        ),
        (
            AITaskOutput,
            "ai",
            "Create one two-sentence legal hold note resource with name, description and inline content; omit resource id.",
        ),
        (
            HumanWorkOutput,
            "human",
            "As records manager create one short legal hold note resource. Omit resource id. Include work process and quality notes.",
        ),
        (
            HumanTimeEstimation,
            "estimator",
            "Estimate hours to write a two-sentence legal hold note.",
        ),
        (
            Decomposition,
            "decomposer",
            "Decompose writing a legal hold procedure into three subtasks with executive summary, implementation plan and acceptance criteria.",
        ),
        (
            JudgeOutput,
            "judge",
            "Score out of 10: All records must be retained until counsel releases the hold. Criterion: requires retention pending counsel release.",
        ),
        (
            BulkDecision,
            "manager",
            "Assign task 00000000-0000-0000-0000-000000000001 to ai_writer, giving reasoning and one assignments entry.",
        ),
    ]
    receipts = []
    for schema, role, prompt in cases:
        result = await infer(
            model=args.model,
            role=role,
            profile=profile,
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
    reference = f"POLICY-{uuid4().hex}"
    calls = 0

    async def lookup_policy() -> str:
        """Read the policy reference required for the final resource."""
        nonlocal calls
        calls += 1
        return f"Reference {reference}. Board approval and independent risk review are required."

    tool_result = await infer(
        model=args.model,
        role="ai",
        profile=profile,
        system="Call lookup_policy, then include its exact returned reference in a resource.",
        prompt="Create a short policy note. Obtain its reference using the tool before answering.",
        output_type=AITaskOutput,
        tools=[lookup_policy],
    )
    if not calls or reference not in json.dumps(tool_result.output):
        raise ValueError("Structured final output bypassed the required tool round trip")
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
                "inference_profile": profile.model_dump(mode="json"),
                "model": args.model,
                "source_revision": SOURCE_REVISION,
                "benchmark_version": BENCHMARK_VERSION,
                "roles": receipts,
                "tool_roundtrip": {
                    "passed": True,
                    "calls": calls,
                    "input_tokens": tool_result.input_tokens,
                    "output_tokens": tool_result.output_tokens,
                },
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
