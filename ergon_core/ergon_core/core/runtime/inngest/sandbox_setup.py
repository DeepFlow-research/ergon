"""Inngest child function: sandbox setup.

Creates and configures a sandbox for task execution.
Resolves the sandbox manager from SANDBOX_MANAGERS registry by benchmark_type.
"""

import logging
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from uuid import UUID

import inngest
from ergon_builtins.registry import SANDBOX_MANAGERS
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunResource
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager, DefaultSandboxManager
from ergon_core.core.runtime.errors import DataIntegrityError
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.child_function_payloads import SandboxSetupRequest
from ergon_core.core.runtime.services.inngest_function_results import SandboxReadyResult
from ergon_core.core.runtime.tracing import (
    CompletedSpan,
    get_trace_sink,
    sandbox_setup_context,
)
from ergon_core.core.settings import settings
from sqlmodel import select

logger = logging.getLogger(__name__)


@inngest_client.create_function(
    fn_id="sandbox-setup",
    trigger=inngest.TriggerEvent(event="task/sandbox-setup"),
    retries=1,
    output_type=SandboxReadyResult,
)
async def sandbox_setup_fn(ctx: inngest.Context) -> SandboxReadyResult:
    """Create and configure a sandbox for task execution."""
    payload = SandboxSetupRequest.model_validate(ctx.event.data)
    run_id = payload.run_id
    task_id = payload.task_id
    benchmark_type = payload.benchmark_type
    span_start = datetime.now(UTC)

    logger.info(
        "sandbox-setup run_id=%s task_id=%s benchmark=%s",
        run_id,
        task_id,
        benchmark_type,
    )

    # Resolved on demand by benchmark_type (already in payload and
    # definition row). Benchmarks not listed get DefaultSandboxManager.
    manager_cls = SANDBOX_MANAGERS.get(benchmark_type, DefaultSandboxManager)
    sandbox_manager = manager_cls()

    output_dir = settings.runs_dir / str(run_id) / "tasks" / str(task_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = await ctx.step.run(
        "create-sandbox",
        partial(
            _create_sandbox,
            run_id,
            task_id,
            sandbox_manager,
            output_dir,
            payload.input_resource_ids,
            payload.envs,
        ),
        output_type=SandboxReadyResult,
    )

    get_trace_sink().emit_span(
        CompletedSpan(
            name="sandbox.setup",
            context=sandbox_setup_context(run_id, task_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(run_id),
                "task_id": str(task_id),
                "benchmark_type": benchmark_type,
                "sandbox_id": result.sandbox_id or "",
                "input_resource_count": len(payload.input_resource_ids),
            },
        )
    )
    return result


async def _create_sandbox(
    run_id: UUID,
    task_id: UUID,
    sandbox_manager: BaseSandboxManager,
    output_dir: Path,
    input_resource_ids: list[UUID],
    envs: dict[str, str] | None,
) -> SandboxReadyResult:
    """Create sandbox via manager."""
    sandbox_id = await sandbox_manager.create(
        task_id,
        run_id=run_id,
        timeout_minutes=30,
        envs=envs,
    )

    if input_resource_ids:
        session = get_session()
        try:
            stmt = select(RunResource).where(
                RunResource.id.in_(input_resource_ids)  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
            )
            resources = list(session.exec(stmt).all())
        finally:
            session.close()

        if len(resources) != len(input_resource_ids):
            found_ids = {r.id for r in resources}
            missing = [str(rid) for rid in input_resource_ids if rid not in found_ids]
            raise DataIntegrityError(
                "RunResource",
                f"[{', '.join(missing)}]",
                run_id=run_id,
                task_id=task_id,
            )

        await sandbox_manager.upload_inputs(task_id, resources)

    return SandboxReadyResult(
        sandbox_id=sandbox_id,
        output_dir=str(output_dir),
    )
