"""Persist outputs child function.

Downloads outputs from sandbox and registers them as resources.
"""

from functools import partial
from pathlib import Path
from uuid import UUID

import inngest

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.registry import get_sandbox_manager
from h_arcane.core._internal.db.models import ResourceRecord
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    persist_outputs_context,
)
from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager, DownloadedFiles
from h_arcane.core._internal.task.requests import PersistOutputsRequest
from h_arcane.core._internal.task.results import PersistOutputsResult
from h_arcane.core._internal.utils import get_mime_type, require_not_none, utcnow
from h_arcane.core.dashboard import dashboard_emitter


@inngest_client.create_function(
    fn_id="persist-outputs",
    trigger=inngest.TriggerEvent(event=PersistOutputsRequest.name),
    retries=1,
    output_type=PersistOutputsResult,
)
async def persist_outputs_fn(ctx: inngest.Context) -> PersistOutputsResult:
    """
    Download outputs from sandbox and register them as resources.

    This child function:
    1. Downloads all outputs from sandbox
    2. Registers each file as a ResourceRecord
    3. Returns list of created resource IDs
    """
    payload = PersistOutputsRequest.model_validate(ctx.event.data)
    run_id = payload.run_id
    task_id = payload.task_id
    execution_id = payload.execution_id
    output_dir = Path(payload.output_dir)
    trace_sink = get_trace_sink()
    trace_context = persist_outputs_context(
        run_id,
        task_id,
        execution_id,
        attributes={"sandbox_id": payload.sandbox_id},
    )
    started_at = utcnow()

    # Get experiment to determine benchmark (inlined - pure reads)
    run = require_not_none(queries.runs.get(run_id), f"Run {run_id} not found")
    experiment = require_not_none(
        queries.experiments.get(run.experiment_id),
        f"Experiment {run.experiment_id} not found",
    )
    benchmark_name = BenchmarkName(experiment.benchmark_name)
    sandbox_manager = get_sandbox_manager(benchmark_name)

    # Download outputs from sandbox
    downloaded = await ctx.step.run(
        "download-outputs",
        partial(_download_outputs, task_id, output_dir, sandbox_manager),
        output_type=DownloadedFiles,
    )
    downloaded = require_not_none(downloaded, "download-outputs returned None")

    # Register each output as a resource (in parallel)
    source_ids = [str(rid) for rid in payload.input_resource_ids]

    if not downloaded.files:
        return PersistOutputsResult(output_resource_ids=[], outputs_count=0)

    # Keep as closure - dynamic parallel step needs closure capture for dynamic data
    def make_register_step(local_path: str, size_bytes: int):
        async def register_resource() -> ResourceRecord:
            resource = queries.resources.create(
                ResourceRecord(
                    run_id=run_id,
                    task_id=task_id,
                    task_execution_id=execution_id,
                    is_input=False,
                    name=Path(local_path).name,
                    mime_type=get_mime_type(local_path),
                    file_path=local_path,
                    size_bytes=size_bytes,
                    source_resource_ids=source_ids,
                )
            )

            # Emit dashboard resource published event
            await dashboard_emitter.resource_published(
                run_id=run_id,
                task_id=task_id,
                task_execution_id=execution_id,
                resource_id=resource.id,
                resource_name=resource.name,
                mime_type=resource.mime_type or "application/octet-stream",
                size_bytes=resource.size_bytes or 0,
                file_path=resource.file_path,
            )

            return resource

        return partial(
            ctx.step.run,
            f"register-resource-{Path(local_path).name}",
            register_resource,
            output_type=ResourceRecord,
        )

    # Run all registrations in parallel
    resources: tuple[ResourceRecord, ...] = await ctx.group.parallel(
        tuple(
            make_register_step(file_info.local_path, file_info.size_bytes)
            for file_info in downloaded.files
        )
    )

    output_resource_ids = [
        require_not_none(r, "register-resource returned None").id for r in resources
    ]

    trace_sink.emit_span(
        CompletedSpan(
            name="persist.outputs",
            context=trace_context,
            start_time=started_at,
            end_time=utcnow(),
            attributes={
                "sandbox_id": payload.sandbox_id,
                "outputs_count": len(output_resource_ids),
                "output_resource_ids": [str(resource_id) for resource_id in output_resource_ids],
            },
        )
    )

    return PersistOutputsResult(
        output_resource_ids=output_resource_ids,
        outputs_count=len(output_resource_ids),
    )


async def _download_outputs(
    task_id: UUID, output_dir: Path, sandbox_manager: BaseSandboxManager
) -> DownloadedFiles:
    """Download all outputs from sandbox."""
    return await sandbox_manager.download_all_outputs(task_id, output_dir)
