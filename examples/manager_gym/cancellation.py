"""Prove native sample cancellation stops a running manager, child and later spawn."""

import argparse
import asyncio
from pathlib import Path
from time import monotonic
from uuid import uuid4

from ergon_core.api import Environment, Experiment, Sample, Task
from ergon_core.core.application.runtime.sample_records import cancel_sample
from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox
from examples.manager_gym.acceptance import (
    inspect_sample,
    closed_sandboxes,
    export_evidence,
    write_json,
    code_digest,
)
from tests.fixtures.mag_contract import CancellationContractWorker


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    name = f"mag-cancellation-{uuid4().hex[:8]}"
    sample = Sample.from_tasks(
        name="Native sample cancellation",
        sample_key="cancellation",
        environment_name=name,
        tasks=[
            Task(
                task_slug="cancel-root",
                instance_key="root",
                description="Live cancellation probe",
                worker=CancellationContractWorker(name="Cancellation manager", model="test:none"),
                sandbox=E2BSandbox(timeout_seconds=600),
            )
        ],
    )
    submitted = await Experiment(
        name=name,
        environments=[
            Environment.from_records(name=name, records=[sample], make_sample=lambda row: row)
        ],
    ).submit(k=1)
    key = submitted.sample_ids[0]
    write_json(
        args.output / "cancellation.json", {"sample_id": str(key), "code_digest": code_digest()}
    )
    deadline = monotonic() + 120
    while True:
        evidence = inspect_sample(str(key))
        if len(evidence["attempts"]) == 2 and all(
            a["status"] == "running" and a.get("sandbox_id") for a in evidence["attempts"]
        ):
            break
        if monotonic() > deadline:
            raise TimeoutError("Cancellation probe did not reach two running E2B attempts")
        await asyncio.sleep(1)
    await asyncio.to_thread(cancel_sample, key)
    # Outlast the manager's delayed spawn; early closure alone missed the old bug.
    await asyncio.sleep(50)
    evidence = inspect_sample(str(key))
    boxes = await closed_sandboxes(evidence)
    checks = {
        "sample_cancelled": evidence["sample"]["status"] == "cancelled",
        "no_late_spawn": len(evidence["nodes"]) == len(evidence["attempts"]) == 2,
        "tasks_cancelled": {n["status"] for n in evidence["nodes"]} == {"cancelled"},
        "attempts_cancelled": {a["status"] for a in evidence["attempts"]} == {"cancelled"},
        "sandboxes_closed": len(boxes) == 2 and all(boxes.values()),
    }
    evidence["checks"], evidence["sandbox_checks"] = checks, boxes
    export_evidence(args.output / str(key), str(key), evidence)
    write_json(
        args.output / "cancellation.json",
        {
            "sample_id": str(key),
            "code_digest": code_digest(),
            "checks": checks,
            "accepted": all(checks.values()),
        },
    )
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
