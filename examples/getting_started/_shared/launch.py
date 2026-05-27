"""Launch helpers for getting-started examples."""

import json
from collections.abc import Sequence
from uuid import UUID


def first_sample_id(sample_result: object) -> UUID:
    """Return the first launched sample id from an Ergon launch result."""
    sample_ids = getattr(sample_result, "sample_ids")
    return sample_ids[0]


def print_submission_summary(
    *,
    experiment_id: UUID | str,
    sampler_invocation_id: UUID | str | None,
    batch_id: UUID | str | None,
    sample_ids: Sequence[UUID | str],
    as_json: bool = True,
) -> None:
    """Print the stable machine-readable submission contract for examples."""
    payload = {
        "experiment_id": str(experiment_id),
        "sampler_invocation_id": (
            str(sampler_invocation_id) if sampler_invocation_id is not None else None
        ),
        "batch_id": str(batch_id) if batch_id is not None else None,
        "sample_ids": [str(sample_id) for sample_id in sample_ids],
    }
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print(f"Experiment id: {payload['experiment_id']}")
    print(f"Sampler invocation id: {payload['sampler_invocation_id']}")
    print(f"Batch id: {payload['batch_id']}")
    print("Sample ids:")
    for sample_id in payload["sample_ids"]:
        print(f"  - {sample_id}")
