"""Wire native artifact retention into the worker checkpoint facade."""

from ergon_core.api.sandbox import Sandbox
from ergon_core.core.application.resources.publishing import WorkerCheckpointStore
from ergon_core.core.infrastructure.sandbox.resource_publisher import SandboxResourcePublisher

from .contract import WorkerExecuteRequest


def worker_checkpoint_store(
    sandbox: Sandbox, payload: WorkerExecuteRequest
) -> WorkerCheckpointStore:
    return WorkerCheckpointStore(
        SandboxResourcePublisher.from_public_sandbox(
            sandbox=sandbox,
            sample_id=payload.sample_id,
            task_attempt_id=payload.execution_id,
        ),
        sample_id=payload.sample_id,
        task_attempt_id=payload.execution_id,
    )
