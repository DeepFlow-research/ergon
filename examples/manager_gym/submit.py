"""Submit native MAG samples through the ordinary Environment/Experiment API.

Run with environment/secret configuration already loaded, for example inside
`docker compose exec api python examples/manager_gym/submit.py ...`.
"""

import argparse
import asyncio
import json
from uuid import uuid4

from ergon_core.api import Environment, Experiment
from ergon_builtins.benchmarks.manager_gym.inference import INTERNAL_MODEL
from ergon_builtins.benchmarks.manager_gym.sample import make_manager_gym_sample
from ergon_builtins.benchmarks.manager_gym.scenario_catalog import SCENARIOS
from ergon_builtins.benchmarks.manager_gym.state import EpisodeConfig


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", action="append", choices=sorted(SCENARIOS))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--manager-mode", choices=["cot", "random", "assign_all"], default="cot")
    parser.add_argument("--max-decisions", type=int, default=50)
    parser.add_argument("--model", default=INTERNAL_MODEL)
    args = parser.parse_args()
    scenarios = list(SCENARIOS) if args.all else args.scenario or ["legal_litigation_ediscovery"]
    name = f"manager-gym-{uuid4().hex[:10]}"
    records = [
        EpisodeConfig(
            scenario=s,
            seed=args.seed,
            max_decisions=args.max_decisions,
            manager_mode=args.manager_mode,
        )
        for s in scenarios
    ]
    environment = Environment.from_records(
        name=name,
        records=records,
        make_sample=lambda config: make_manager_gym_sample(
            config, environment_name=name, model=args.model
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
