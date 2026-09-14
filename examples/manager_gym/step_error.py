"""Prove original step errors survive the native E2B worker lifecycle."""

import argparse
import asyncio
from pathlib import Path
from time import monotonic
from uuid import uuid4

from ergon_core.api import Environment, Experiment, Sample, Task
from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox
from examples.manager_gym.acceptance import (
    inspect_sample,
    closed_sandboxes,
    export_evidence,
    write_json,
    code_digest,
)
from tests.fixtures.mag_contract import ContractStepFailure


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    name = f"mag-step-error-{uuid4().hex[:8]}"
    sample = Sample.from_tasks(
        name="Native step error",
        sample_key="step-error",
        environment_name=name,
        tasks=[
            Task(
                task_slug="step-error",
                instance_key="root",
                description="Retain a scripted empty-message step failure",
                worker=ContractStepFailure(name="Step failure", model="test:none"),
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
    key = str(submitted.sample_ids[0])
    write_json(args.output / "step-error.json", {"sample_id": key, "code_digest": code_digest()})
    deadline = monotonic() + 180
    while True:
        evidence = inspect_sample(key)
        if evidence["sample"]["status"] in {"completed", "failed", "cancelled"}:
            break
        if monotonic() > deadline:
            raise TimeoutError("Native step-error proof did not finish")
        await asyncio.sleep(1)
    boxes = await closed_sandboxes(evidence)
    errors = [a.get("error_json") or {} for a in evidence["attempts"]]
    checks = {
        "one_failed_attempt": len(errors) == 1 and evidence["attempts"][0]["status"] == "failed",
        "sample_failed": evidence["sample"]["status"] == "failed",
        "original_type_and_message": len(errors) == 1
        and errors[0].get("exception_type") == errors[0].get("message") == "TimeoutError",
        "original_note_retained": len(errors) == 1
        and "native-step-failure-proof" in errors[0].get("stack", ""),
        "step_wrapper_recorded": len(errors) == 1
        and errors[0].get("context", {}).get("workflow_error_type") == "StepError",
        "sandbox_closed": len(boxes) == 1 and all(boxes.values()),
    }
    evidence["checks"], evidence["sandbox_checks"] = checks, boxes
    export_evidence(args.output / key, key, evidence)
    write_json(
        args.output / "step-error.json",
        {
            "sample_id": key,
            "code_digest": code_digest(),
            "checks": checks,
            "accepted": all(checks.values()),
            "model_calls": 0,
        },
    )
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
