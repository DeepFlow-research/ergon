"""Sandbox setup child function.

Creates and configures a sandbox for task execution.
"""

from functools import partial
from pathlib import Path
from uuid import UUID

import inngest

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.registry import get_sandbox_manager, get_skills_dir
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager
from h_arcane.core._internal.task.requests import SandboxSetupRequest
from h_arcane.core._internal.task.results import SandboxReadyResult
from h_arcane.core.settings import settings


@inngest_client.create_function(
    fn_id="sandbox-setup",
    trigger=inngest.TriggerEvent(event=SandboxSetupRequest.name),
    retries=1,
    output_type=SandboxReadyResult,
)
async def sandbox_setup_fn(ctx: inngest.Context) -> SandboxReadyResult:
    """
    Create and configure a sandbox for task execution.

    This child function:
    1. Creates sandbox via benchmark-specific manager
    2. Saves sandbox ID to run record
    3. Returns sandbox info for worker execution
    """
    payload = SandboxSetupRequest.model_validate(ctx.event.data)
    run_id = payload.run_id
    task_id = payload.task_id
    benchmark_name = BenchmarkName(payload.benchmark_name)

    # Get benchmark-specific sandbox manager
    sandbox_manager = get_sandbox_manager(benchmark_name)
    skills_dir = get_skills_dir(benchmark_name)

    # Setup output directory
    output_dir = settings.runs_dir / str(run_id) / "tasks" / str(task_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create sandbox
    result = await ctx.step.run(
        "create-sandbox",
        partial(
            _create_sandbox,
            run_id,
            task_id,
            sandbox_manager,
            skills_dir,
            output_dir,
            payload.envs,
        ),
        output_type=SandboxReadyResult,
    )
    if result is None:
        raise ValueError("create-sandbox step returned None")

    return result


async def _create_sandbox(
    run_id: UUID,
    task_id: UUID,
    sandbox_manager: BaseSandboxManager,
    skills_dir: Path | None,
    output_dir: Path,
    envs: dict[str, str] | None,
) -> SandboxReadyResult:
    """Create sandbox via manager and save ID to run record."""
    sandbox_id = await sandbox_manager.create(
        task_id,
        skills_dir=skills_dir,
        timeout_minutes=30,
        envs=envs,
        run_id=run_id,
    )

    # Save sandbox ID to run record
    run = queries.runs.get(run_id)
    if run and not run.e2b_sandbox_id:
        updated = run.model_copy(update={"e2b_sandbox_id": sandbox_id})
        queries.runs.update(updated)

    return SandboxReadyResult(
        sandbox_id=sandbox_id,
        output_dir=str(output_dir),
    )
