"""Submit Manager Gym episodes through the ordinary Environment/Experiment API.

Run with the Ergon stack up (`ergon start`) and provider keys configured, for example
`docker compose exec api python examples/manager_gym/submit.py --scenario icaap`.
"""

import argparse
import asyncio
import json
import os
from uuid import uuid4

from ergon_builtins.benchmarks.manager_gym.inference import InferenceProfile
from ergon_builtins.benchmarks.manager_gym.sample import make_manager_gym_sample
from ergon_builtins.benchmarks.manager_gym.state import EpisodeConfig
from ergon_builtins.benchmarks.manager_gym.upstream import SCENARIOS
from ergon_core.api import Environment, Experiment

DEFAULT_SCENARIO = "legal_litigation_ediscovery"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--scenario",
        action="append",
        choices=sorted(SCENARIOS),
        help=f"Scenario to run; repeatable (default: {DEFAULT_SCENARIO}).",
    )
    selection.add_argument("--all", action="store_true", help="Run every scenario.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--manager-mode", choices=["cot", "random", "assign_all"], default="cot")
    parser.add_argument("--max-decisions", type=int, default=50)
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
    parser.add_argument(
        "--rubric-version",
        type=int,
        choices=[1, 2],
        default=2,
        help="1 reproduces upstream scoring; 2 (default) applies the documented fixes.",
    )
    args = parser.parse_args()
    scenarios = list(SCENARIOS) if args.all else args.scenario or [DEFAULT_SCENARIO]
    inference = InferenceProfile(thinking_token_budget=args.thinking_token_budget)
    name = f"manager-gym-{uuid4().hex[:10]}"
    records = [
        EpisodeConfig(
            scenario=s,
            seed=args.seed,
            max_decisions=args.max_decisions,
            manager_mode=args.manager_mode,
            inference=inference,
        )
        for s in scenarios
    ]
    environment = Environment.from_records(
        name=name,
        records=records,
        make_sample=lambda config: make_manager_gym_sample(
            config, environment_name=name, model=args.model, rubric_version=args.rubric_version
        ),
    )
    result = await Experiment(name=name, environments=[environment]).submit(k=len(records))
    print(
        json.dumps(
            {"experiment": name, "sample_ids": [str(i) for i in result.sample_ids]}, indent=2
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
