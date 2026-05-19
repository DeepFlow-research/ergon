"""Inngest child function: sandbox setup."""

import logging
from datetime import UTC, datetime
from functools import partial

from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.application.jobs.models import SandboxReadyResult, SandboxSetupRequest
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    sandbox_setup_context,
)
from typing import Any

logger = logging.getLogger(__name__)


async def run_sandbox_setup_job(ctx: Any, payload: SandboxSetupRequest) -> SandboxReadyResult:
    """Create and configure a sandbox for task execution."""
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

    with get_session() as session:
        view = await WorkflowGraphRepository().node(
            session,
            run_id=run_id,
            task_id=task_id,
        )

    result = await ctx.step.run(
        "provision-public-sandbox",
        partial(_provision_public_sandbox, view.task.sandbox),
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
                "sandbox_id": result.sandbox_id,
                "input_resource_count": len(payload.input_resource_ids),
            },
        )
    )
    return result


async def _provision_public_sandbox(sandbox: Any) -> SandboxReadyResult:
    await sandbox.provision()
    return SandboxReadyResult(
        sandbox_id=sandbox.sandbox_id,
        output_dir=sandbox.output_path,
    )
