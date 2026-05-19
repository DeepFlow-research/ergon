"""Inngest child function: sandbox setup.

The child step remains the acquisition retry boundary. For object-bound
snapshots it provisions the public ``Task.sandbox`` and returns that
sandbox's identity/output path. A manager-backed fallback remains only
for legacy TaskSpec snapshots until PR 11.
"""

import logging
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from uuid import UUID

from ergon_core.api.registry import registry
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunResource
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager, DefaultSandboxManager
from ergon_core.core.infrastructure.inngest.errors import DataIntegrityError
from ergon_core.core.application.jobs.models import SandboxReadyResult, SandboxSetupRequest
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    sandbox_setup_context,
)
from ergon_core.core.shared.settings import settings
from sqlmodel import col, select
from typing import Any

logger = logging.getLogger(__name__)


async def run_sandbox_setup_job(ctx: Any, payload: SandboxSetupRequest) -> SandboxReadyResult:
    """Create and configure a sandbox for task execution."""
    run_id = payload.run_id
    task_id = payload.task_id
    benchmark_type = payload.benchmark_type
    manager_slug = _sandbox_manager_slug(payload)
    span_start = datetime.now(UTC)

    logger.info(
        "sandbox-setup run_id=%s task_id=%s benchmark=%s sandbox=%s",
        run_id,
        task_id,
        benchmark_type,
        manager_slug,
    )

    with get_session() as session:
        view = await WorkflowGraphRepository().node(
            session,
            run_id=run_id,
            task_id=task_id,
        )

    if view.task.sandbox is not None:
        result = await ctx.step.run(
            "provision-public-sandbox",
            partial(_provision_public_sandbox, view.task.sandbox),
            output_type=SandboxReadyResult,
        )
    else:
        # TODO(PR 11): delete manager fallback once TaskSpec snapshots no
        # longer reach runtime jobs.
        manager_cls = registry.sandbox_managers.get(manager_slug, DefaultSandboxManager)
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
                "sandbox_slug": manager_slug,
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


def _sandbox_manager_slug(payload: SandboxSetupRequest) -> str:
    return payload.sandbox_slug or payload.benchmark_type


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
        display_task_id=task_id,
    )

    if input_resource_ids:
        session = get_session()
        try:
            stmt = select(RunResource).where(col(RunResource.id).in_(input_resource_ids))
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
