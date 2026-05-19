"""Composition helpers for sandbox output publishing."""

from __future__ import annotations

from typing import Protocol

from ergon_core.core.application.resources.publishing import RunResourcePublishService
from ergon_core.core.infrastructure.sandbox.resource_publisher import SandboxResourcePublisher
from ergon_core.core.persistence.shared.enums import RunResourceKind

from .contract import PersistOutputsRequest


class PublicSandboxWithOutputPath(Protocol):
    output_path: str


async def publish_public_sandbox_resources(
    sandbox: PublicSandboxWithOutputPath,
    payload: PersistOutputsRequest,
) -> int:
    publish_dir = payload.output_dir or sandbox.output_path
    publish_dirs = ((publish_dir, RunResourceKind.REPORT),)
    publisher = SandboxResourcePublisher.from_public_sandbox(
        sandbox=sandbox,
        run_id=payload.run_id,
        task_execution_id=payload.execution_id,
        publish_dirs=publish_dirs,
    )
    synced = await RunResourcePublishService().publish_sandbox_files(
        reader=publisher,
        blob_store=publisher,
        run_id=payload.run_id,
        task_execution_id=payload.execution_id,
        publish_dirs=publish_dirs,
    )
    return len(synced)
