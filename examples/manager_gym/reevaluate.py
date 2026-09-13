"""Submit a new native evaluation of an unchanged exported MAG snapshot."""

import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID, uuid4

from ergon_core.api import Environment, Experiment
from ergon_builtins.benchmarks.manager_gym.inference import INTERNAL_MODEL
from ergon_builtins.benchmarks.manager_gym.sample import make_snapshot_reevaluation_sample
from ergon_builtins.benchmarks.manager_gym.state import EpisodeState, snapshot_hash


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--source-sample-id", type=UUID, required=True)
    parser.add_argument("--model", default=INTERNAL_MODEL)
    args = parser.parse_args()
    raw = json.loads(args.snapshot.read_text())
    state = EpisodeState.model_validate(raw)
    digest = sha256(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if snapshot_hash(state) != digest:
        raise ValueError(
            "Snapshot schema differs from this code version; do not silently rewrite historical evidence"
        )
    name = f"mag-reevaluation-{uuid4().hex[:8]}"
    sample = make_snapshot_reevaluation_sample(
        state, source_sample_id=args.source_sample_id, environment_name=name, model=args.model
    )
    result = await Experiment(
        name=name,
        environments=[
            Environment.from_records(name=name, records=[sample], make_sample=lambda s: s)
        ],
    ).submit(k=1)
    print(
        json.dumps(
            {
                "evaluation_of_sample": str(args.source_sample_id),
                "sample_id": str(result.sample_ids[0]),
                "snapshot_hash": digest,
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
