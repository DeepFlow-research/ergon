from uuid import uuid4

import pytest
from ergon_core.core.runtime.inngest import persist_outputs
from ergon_core.core.runtime.services.child_function_payloads import PersistOutputsRequest


class _Manager:
    def get_sandbox(self, task_id):
        return object()


class _Publisher:
    def __init__(self, **kwargs):
        pass

    async def sync(self):
        return [object(), object()]

    def publish_value(self, **kwargs):
        raise AssertionError("worker final assistant message must not be published as a resource")


@pytest.mark.asyncio
async def test_worker_final_message_is_not_published_as_run_resource(monkeypatch) -> None:
    monkeypatch.setattr(persist_outputs, "SandboxResourcePublisher", _Publisher)

    count = await persist_outputs._publish_resources(
        _Manager(),
        PersistOutputsRequest.model_validate(
            {
                "run_id": uuid4(),
                "definition_id": uuid4(),
                "task_id": uuid4(),
                "execution_id": uuid4(),
                "sandbox_id": "sandbox",
                "benchmark_type": "smoke",
                "worker_final_assistant_message": "final answer",
            }
        ),
    )

    assert count == 2
