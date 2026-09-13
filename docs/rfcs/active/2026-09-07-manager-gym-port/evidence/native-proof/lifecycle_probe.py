"""Submit one real native E2B task to the isolated local proof stack."""

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from sqlmodel import select

load_dotenv(Path.cwd() / ".env", override=False)

from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox
from ergon_core.api import Environment, Experiment, Sample, Task
from ergon_core.api.rubric.rubric import Rubric
from ergon_core.core.infrastructure.sandbox.lifecycle import terminate_external_sandbox
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import (
    SampleRecord,
    SampleResource,
    SampleTaskAttempt,
    SampleTaskEvaluation,
)
from tests.fixtures.mag_preport import PreportCriterion, PreportWorker

OUT = Path(__file__).with_name("lifecycle-result.json")


async def main() -> None:
    name = f"mag-preport-{uuid4().hex[:8]}"
    sample = Sample.from_tasks(
        name=name,
        sample_key="proof",
        environment_name=name,
        tasks=[
            Task(
                task_slug="proof",
                instance_key="proof",
                description="Write and independently check one E2B artifact.",
                worker=PreportWorker(name="proof", model="test:none"),
                sandbox=E2BSandbox(timeout_seconds=300),
                evaluators=(Rubric(name="proof", criteria=(PreportCriterion(slug="proof"),)),),
            )
        ],
    )
    experiment = Experiment(
        name=name,
        environments=[
            Environment.from_records(name=name, records=[sample], make_sample=lambda s: s)
        ],
    )
    submitted = await experiment.submit(k=1)
    sample_id = submitted.sample_ids[0]
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "sample_id": str(sample_id),
        "scope": "real Inngest/Postgres/E2B native lifecycle; deterministic worker and criterion",
    }
    OUT.write_text(json.dumps(result, indent=2))
    deadline = time.monotonic() + 180
    while True:
        with get_session() as session:
            record = session.get(SampleRecord, sample_id)
            nodes = session.exec(
                select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)
            ).all()
            attempts = session.exec(
                select(SampleTaskAttempt).where(SampleTaskAttempt.sample_id == sample_id)
            ).all()
            evaluations = session.exec(
                select(SampleTaskEvaluation).where(SampleTaskEvaluation.sample_id == sample_id)
            ).all()
            resources = session.exec(
                select(SampleResource).where(SampleResource.sample_id == sample_id)
            ).all()
            result.update(
                sample_status=str(record.status),
                nodes=[{"task_id": str(n.task_id), "status": n.status} for n in nodes],
                attempts=[
                    {
                        "id": str(a.id),
                        "status": str(a.status),
                        "sandbox_id": a.sandbox_id,
                        "worker_output": a.worker_output_json,
                        "error": a.error_json,
                    }
                    for a in attempts
                ],
                evaluations=[
                    {"score": e.score, "passed": e.passed, "summary": e.summary_json}
                    for e in evaluations
                ],
                resources=[
                    {"name": r.name, "size_bytes": r.size_bytes, "error": r.error}
                    for r in resources
                ],
            )
        OUT.write_text(json.dumps(result, indent=2, default=str))
        if (
            str(record.status).lower() in {"completed", "failed", "cancelled"}
            or time.monotonic() >= deadline
        ):
            break
        await asyncio.sleep(5)
    result["cleanup_check"] = [
        (await terminate_external_sandbox(sandbox_id)).model_dump(mode="json")
        for sandbox_id in {a.sandbox_id for a in attempts if a.sandbox_id}
    ]
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    OUT.write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
