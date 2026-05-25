from uuid import uuid4
from types import SimpleNamespace

import pytest
from ergon_core.core.jobs.resources.persist_outputs import composition as persist_outputs
from ergon_core.core.jobs.resources.persist_outputs.contract import PersistOutputsRequest


class _Manager:
    def get_sandbox(self, task_id):
        return SimpleNamespace(output_path="/workspace/final_output")


class _Publisher:
    def __init__(self, **kwargs):
        pass

    def publish_value(self, **kwargs):
        raise AssertionError("worker final assistant message must not be published as a resource")

    @classmethod
    def from_public_sandbox(cls, **kwargs):
        return cls(**kwargs)


class _PublishService:
    async def publish_sandbox_files(self, **kwargs):
        return [object(), object()]


@pytest.mark.asyncio
async def test_worker_final_message_is_not_published_as_run_resource(monkeypatch) -> None:
    monkeypatch.setattr(persist_outputs, "SandboxResourcePublisher", _Publisher)
    monkeypatch.setattr(persist_outputs, "SampleResourcePublishService", _PublishService)

    count = await persist_outputs.publish_public_sandbox_resources(
        _Manager().get_sandbox(uuid4()),
        PersistOutputsRequest.model_validate(
            {
                "sample_id": uuid4(),
                "definition_id": uuid4(),
                "task_id": uuid4(),
                "execution_id": uuid4(),
                "sandbox_id": "sandbox",
                "benchmark_type": "smoke",
            }
        ),
    )

    assert count == 2
