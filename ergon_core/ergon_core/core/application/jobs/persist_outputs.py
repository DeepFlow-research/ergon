"""Inngest child function: persist outputs from sandbox via blob publisher.

All serialisation goes through :class:`SandboxResourcePublisher` — the
single authoritative path from sandbox → Postgres (``run_resources`` rows)
and local blob store.  The legacy "download-to-local-path + kind='output'"
loop that created a second row per file has been removed; consumers should
read via the publisher (``kind='report'``/``kind='artifact'`` rows whose
``file_path`` points at the content-addressed blob store).
"""

import logging
from datetime import UTC, datetime

from ergon_core.api.registry import registry
from ergon_core.core.infrastructure.sandbox.manager import (
    BaseSandboxManager,
    DefaultSandboxManager,
)
from ergon_core.core.infrastructure.sandbox.resource_publisher import SandboxResourcePublisher
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError
from ergon_core.core.application.jobs.models import PersistOutputsRequest, PersistOutputsResult
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    persist_outputs_context,
)

logger = logging.getLogger(__name__)


async def run_persist_outputs_job(payload: PersistOutputsRequest) -> PersistOutputsResult:
    """Sync sandbox publish dirs to the blob store and register resources."""
    run_id = payload.run_id
    task_id = payload.task_id
    execution_id = payload.execution_id
    span_start = datetime.now(UTC)
    sandbox_id = payload.sandbox_id

    logger.info(
        "persist-outputs run_id=%s task_id=%s sandbox_id=%s",
        run_id,
        task_id,
        sandbox_id,
    )

    if not sandbox_id:
        raise ContractViolationError(
            "persist-outputs invoked without sandbox_id",
            run_id=run_id,
            task_id=task_id,
        )

    manager_cls = registry.sandbox_managers.get(payload.benchmark_type, DefaultSandboxManager)
    sandbox_manager = manager_cls()

    outputs_count = await _publish_resources(sandbox_manager, payload)

    get_trace_sink().emit_span(
        CompletedSpan(
            name="persist.outputs",
            context=persist_outputs_context(run_id, task_id, execution_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(run_id),
                "task_id": str(task_id),
                "execution_id": str(execution_id),
                "outputs_count": outputs_count,
            },
        )
    )

    return PersistOutputsResult(outputs_count=outputs_count)


async def _publish_resources(
    sandbox_manager: BaseSandboxManager,
    payload: PersistOutputsRequest,
) -> int:
    """Sync the live sandbox's publish dirs to the blob store.

    Returns the number of new resource rows created.  No-op when no live
    sandbox exists for this task (e.g. benchmark without sandboxes).
    """
    sandbox = sandbox_manager.get_sandbox(payload.task_id)
    if sandbox is None:
        logger.info(
            "persist-outputs: no live sandbox for task_id=%s, skipping publisher",
            payload.task_id,
        )
        return 0

    publisher = SandboxResourcePublisher(
        sandbox=sandbox,
        run_id=payload.run_id,
        task_execution_id=payload.execution_id,
    )

    synced = await publisher.sync()
    count = len(synced)
    if synced:
        logger.info(
            "persist-outputs: publisher.sync() created %d resource(s) for run_id=%s",
            count,
            payload.run_id,
        )

    return count
