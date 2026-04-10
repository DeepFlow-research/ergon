"""Inngest child function: persist outputs from sandbox.

Downloads outputs from sandbox and registers them as RunResource rows.
"""

import logging
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from uuid import UUID

import inngest
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.ids import new_id
from ergon_core.core.persistence.telemetry.models import RunResource
from ergon_core.core.providers.sandbox.manager import (
    BaseSandboxManager,
    DefaultSandboxManager,
    DownloadedFiles,
)
from ergon_core.core.runtime.errors import ContractViolationError
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.child_function_payloads import PersistOutputsRequest
from ergon_core.core.runtime.services.inngest_function_results import PersistOutputsResult
from ergon_core.core.runtime.tracing import (
    CompletedSpan,
    get_trace_sink,
    persist_outputs_context,
)
from ergon_core.core.utils import get_mime_type, utcnow
from ergon_builtins.registry import SANDBOX_MANAGERS

logger = logging.getLogger(__name__)


@inngest_client.create_function(
    fn_id="persist-outputs",
    trigger=inngest.TriggerEvent(event="task/persist-outputs"),
    retries=1,
    output_type=PersistOutputsResult,
)
async def persist_outputs_fn(ctx: inngest.Context) -> PersistOutputsResult:
    """Download outputs from sandbox and register them as resources."""
    payload = PersistOutputsRequest.model_validate(ctx.event.data)
    run_id = payload.run_id
    task_id = payload.task_id
    execution_id = payload.execution_id
    span_start = datetime.now(UTC)
    output_dir = Path(payload.output_dir) if payload.output_dir else None
    sandbox_id = payload.sandbox_id

    logger.info(
        "persist-outputs run_id=%s task_id=%s sandbox_id=%s",
        run_id,
        task_id,
        sandbox_id,
    )

    if not sandbox_id or not output_dir:
        raise ContractViolationError(
            "persist-outputs invoked without sandbox_id or output_dir",
            run_id=run_id,
            task_id=task_id,
            sandbox_id=sandbox_id,
            output_dir=str(output_dir),
        )

    manager_cls = SANDBOX_MANAGERS.get(payload.benchmark_type, DefaultSandboxManager)
    sandbox_manager = manager_cls()

    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded: DownloadedFiles = await ctx.step.run(
        "download-outputs",
        partial(_download_outputs, task_id, output_dir, sandbox_manager),
        output_type=DownloadedFiles,
    )

    if not downloaded.files:
        return PersistOutputsResult()

    resource_ids: list[UUID] = []
    with get_session() as session:
        for file_info in downloaded.files:
            resource = RunResource(
                id=new_id(),
                run_id=run_id,
                task_execution_id=execution_id,
                kind="output",
                name=Path(file_info.local_path).name,
                mime_type=get_mime_type(file_info.local_path),
                file_path=file_info.local_path,
                size_bytes=file_info.size_bytes,
                created_at=utcnow(),
            )
            session.add(resource)
            resource_ids.append(resource.id)

        session.commit()

    logger.info(
        "persist-outputs registered %d resources for run_id=%s",
        len(resource_ids),
        run_id,
    )

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
                "outputs_count": len(resource_ids),
                "resource_ids": [str(rid) for rid in resource_ids],
            },
        )
    )

    return PersistOutputsResult(
        output_resource_ids=resource_ids,
        outputs_count=len(resource_ids),
    )


async def _download_outputs(
    task_id: UUID,
    output_dir: Path,
    sandbox_manager: BaseSandboxManager,
) -> DownloadedFiles:
    """Download all outputs from sandbox."""
    return await sandbox_manager.download_all_outputs(task_id, output_dir)
