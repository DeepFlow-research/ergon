"""Large workflow results replay from retained artifacts, not engine state."""

import json
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import BaseModel

from ergon_core.api.worker import WorkerContext
from ergon_core.core.application.resources.publishing import WorkerCheckpointStore
from ergon_core.core.infrastructure.sandbox.resource_publisher import SandboxResourcePublisher


class LargeResult(BaseModel):
    transcript: str


class RecordedSteps:
    def __init__(self) -> None:
        self.results = {}

    async def run(self, name, operation, *, output_type):
        if name not in self.results:
            self.results[name] = (await operation()).model_dump_json()
        return output_type.model_validate_json(self.results[name])


class RetainingPublisher:
    def __init__(self) -> None:
        self.rows = []

    def publish_value(self, **values):
        data = values["content"].encode()
        values["blob_store"].write_blob(data, sha256(data).hexdigest())
        self.rows.append(values)


@pytest.mark.asyncio
async def test_large_result_replays_after_context_reconstruction_without_inference(tmp_path):
    sample_id, attempt_id, task_id = uuid4(), uuid4(), uuid4()
    blobs = SandboxResourcePublisher(
        sandbox=None, sample_id=sample_id, task_attempt_id=attempt_id, blob_root=tmp_path
    )
    publisher = RetainingPublisher()
    steps = RecordedSteps()
    calls = 0

    def context():
        return WorkerContext._for_job(
            sample_id=sample_id,
            execution_id=attempt_id,
            task_id=task_id,
            sandbox_id="e2b-proof",
            task_mgmt=SimpleNamespace(),
            task_inspect=SimpleNamespace(),
            resource_service=SimpleNamespace(),
            session_factory=lambda: None,
            steps=steps,
            checkpoint_store=WorkerCheckpointStore(blobs, sample_id, attempt_id, publisher),
        )

    async def inference():
        nonlocal calls
        calls += 1
        return LargeResult(transcript="x" * (33_554_432 + 1))

    first = await context().run_step("model-decision", inference, output_type=LargeResult)
    replay = await context().run_step("model-decision", inference, output_type=LargeResult)
    assert replay == first
    assert calls == 1
    assert len(json.dumps(steps.results)) < 256
    assert len(publisher.rows) == 1
    assert publisher.rows[0]["task_attempt_id"] == attempt_id
    assert publisher.rows[0]["name"] == ".checkpoints/model-decision.json"

    reference = json.loads(steps.results["model-decision"])
    path = blobs.blob_path(reference["content_hash"])
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity failure"):
        await context().run_step("model-decision", inference, output_type=LargeResult)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        await context().run_step("model-decision", inference, output_type=LargeResult)
    assert calls == 1


def test_concurrent_identical_blob_writes_are_atomic(tmp_path):
    blobs = SandboxResourcePublisher(
        sandbox=None, sample_id=uuid4(), task_attempt_id=uuid4(), blob_root=tmp_path
    )
    data = b"retained result" * 100_000
    digest = sha256(data).hexdigest()
    with ThreadPoolExecutor(max_workers=8) as executor:
        paths = list(executor.map(lambda _: blobs.write_blob(data, digest), range(8)))
    assert all(path.read_bytes() == data for path in paths)
    assert list(paths[0].parent.iterdir()) == [paths[0]]
