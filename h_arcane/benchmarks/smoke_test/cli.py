"""CLI for smoke test benchmark.

Usage:
    # List available workflows
    python -m h_arcane.benchmarks.smoke_test.cli list

    # Run a specific workflow
    python -m h_arcane.benchmarks.smoke_test.cli run --workflow single
    python -m h_arcane.benchmarks.smoke_test.cli run --workflow linear
    python -m h_arcane.benchmarks.smoke_test.cli run --workflow parallel
    python -m h_arcane.benchmarks.smoke_test.cli run --workflow nested

    # Run all workflows
    python -m h_arcane.benchmarks.smoke_test.cli run --all

    # Run with custom model
    python -m h_arcane.benchmarks.smoke_test.cli run --workflow single --model gpt-4o-mini
"""

import asyncio
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

import inngest
import typer
from rich.console import Console
from rich.table import Table

from h_arcane.benchmarks.smoke_test.workflows import (
    WORKFLOW_FACTORIES,
    list_workflows,
)
from h_arcane.core._internal.db.models import RunStatus
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.events import BenchmarkRunRequest
from h_arcane.core.runner import ExecutionResult
from h_arcane.core.task import TaskStatus

app = typer.Typer(
    name="smoke-test",
    help="Smoke test benchmark CLI for h_arcane pipeline validation.",
)
console = Console()


@app.command("list")
def list_cmd():
    """List available smoke test workflows."""
    table = Table(title="Smoke Test Workflows")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="green")

    workflow_descriptions = {
        "single": "Single atomic task - simplest test case",
        "linear": "A -> B -> C: Sequential task chain",
        "parallel": "A -> [B, C] -> D: Fan-out and fan-in",
        "nested": "L1 -> L2 -> L3: Hierarchical subtasks",
    }

    for name in list_workflows():
        description = workflow_descriptions.get(name, "No description")
        table.add_row(name, description)

    console.print(table)


@app.command("run")
def run_cmd(
    workflow: str = typer.Option(
        None,
        "--workflow",
        "-w",
        help="Workflow name to run (single, linear, parallel, nested)",
    ),
    all_workflows: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Run all workflows",
    ),
    model: str = typer.Option(
        "gpt-4o",
        "--model",
        "-m",
        help="LLM model to use",
    ),
    timeout: int = typer.Option(
        300,
        "--timeout",
        "-t",
        help="Timeout in seconds",
    ),
):
    """Run smoke test workflow(s)."""
    if not workflow and not all_workflows:
        console.print("[red]Error: Specify --workflow NAME or --all[/red]")
        raise typer.Exit(1)

    workflows_to_run = list_workflows() if all_workflows else [workflow]

    # Validate workflow names
    for w in workflows_to_run:
        if w not in WORKFLOW_FACTORIES:
            available = ", ".join(WORKFLOW_FACTORIES.keys())
            console.print(f"[red]Error: Unknown workflow '{w}'. Available: {available}[/red]")
            raise typer.Exit(1)

    # Run workflows
    results = asyncio.run(_run_workflows(workflows_to_run, model, timeout))

    # Summary
    console.print("\n[bold]Summary[/bold]")
    all_success = True
    for name, result in results.items():
        status = "[green]PASS[/green]" if result.success else "[red]FAIL[/red]"
        console.print(f"  {name}: {status} ({result.duration_seconds:.1f}s)")
        if not result.success:
            all_success = False
            if result.error:
                console.print(f"    Error: {result.error}")

    if all_success:
        console.print("\n[green bold]All smoke tests passed![/green bold]")
    else:
        console.print("\n[red bold]Some smoke tests failed![/red bold]")
        raise typer.Exit(1)


async def _run_workflows(
    workflow_names: list[str],
    model: str,
    timeout: int,
) -> dict:
    """Run workflows by emitting Inngest events and polling for completion."""
    results: dict[str, ExecutionResult] = {}

    for name in workflow_names:
        console.print(f"\n[bold cyan]Running workflow: {name}[/bold cyan]")
        started_at = datetime.now(timezone.utc)

        try:
            result = await _run_single_workflow(name, model, timeout, started_at)
            results[name] = result

            if result.success:
                console.print("  [green]Status: COMPLETED[/green]")
                console.print(f"  Duration: {result.duration_seconds:.1f}s")
                if result.run_id:
                    console.print(f"  Run ID: {result.run_id}")
            else:
                console.print("  [red]Status: FAILED[/red]")
                if result.error:
                    console.print(f"  Error: {result.error}")

        except Exception as e:
            console.print(f"  [red]Exception: {e}[/red]")
            results[name] = ExecutionResult(
                success=False,
                status=TaskStatus.FAILED,
                error=str(e),
                started_at=started_at,
                duration_seconds=0.0,
            )

    return results


async def _run_single_workflow(
    workflow_name: str,
    model: str,
    timeout: int,
    started_at: datetime,
) -> ExecutionResult:
    """Run a single workflow via Inngest event and poll for completion."""
    # Generate unique request ID to track this run
    request_id = str(uuid4())

    console.print(f"  Workflow: {workflow_name}")
    console.print(f"  Request ID: {request_id[:8]}...")

    # Create and send the event
    event = BenchmarkRunRequest(
        request_id=request_id,
        benchmark_name="smoke_test",
        workflow_name=workflow_name,
        model=model,
        timeout_seconds=timeout,
        max_questions=10,
    )

    console.print("  Sending event to Inngest...")
    await inngest_client.send(
        inngest.Event(name=BenchmarkRunRequest.name, data=event.model_dump())
    )

    # Poll for run creation (wait for benchmark_run_start to create the Run)
    console.print("  Waiting for run to be created...")
    run_id = await _poll_for_run_creation(request_id, timeout)

    if run_id is None:
        return ExecutionResult(
            success=False,
            status=TaskStatus.FAILED,
            error="Timeout waiting for run to be created",
            started_at=started_at,
            duration_seconds=(datetime.now(timezone.utc) - started_at).total_seconds(),
        )

    console.print(f"  Run created: {run_id}")

    # Poll for completion
    console.print("  Waiting for completion...")
    return await _poll_for_completion(run_id, timeout, started_at)


async def _poll_for_run_creation(
    request_id: str,
    timeout: int,
    poll_interval: float = 1.0,
) -> UUID | None:
    """Poll database for a run with matching request_id."""
    start_time = time.time()

    while (time.time() - start_time) < timeout:
        # Query for runs with matching cli_request_id in metadata
        # Note: This is a simple approach - queries all recent runs
        # A more efficient approach would add a dedicated index
        runs = queries.runs.get_recent(limit=10)

        for run in runs:
            if run.cli_request_id() == request_id:
                return run.id

        await asyncio.sleep(poll_interval)

    return None


async def _poll_for_completion(
    run_id: UUID,
    timeout: int,
    started_at: datetime,
    poll_interval: float = 1.0,
) -> ExecutionResult:
    """Poll database until run completes or times out."""
    start_time = time.time()
    terminal_statuses = {RunStatus.COMPLETED, RunStatus.FAILED}

    while True:
        run = queries.runs.get(run_id)
        if run is None:
            return ExecutionResult(
                success=False,
                status=TaskStatus.FAILED,
                error=f"Run {run_id} not found",
                started_at=started_at,
                duration_seconds=(datetime.now(timezone.utc) - started_at).total_seconds(),
                run_id=run_id,
            )

        # Check if terminal state
        if run.status in terminal_statuses:
            # Deserialize precomputed ExecutionResult from run
            parsed_result = run.parsed_execution_result()
            if parsed_result:
                return parsed_result

            # Fallback if execution_result not set
            completed_at = datetime.now(timezone.utc)
            return ExecutionResult(
                success=run.status == RunStatus.COMPLETED,
                status=TaskStatus.COMPLETED if run.status == RunStatus.COMPLETED else TaskStatus.FAILED,
                error=run.error_message,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=(completed_at - started_at).total_seconds(),
                run_id=run_id,
            )

        # Check timeout
        if (time.time() - start_time) > timeout:
            return ExecutionResult(
                success=False,
                status=TaskStatus.FAILED,
                error=f"Workflow timed out after {timeout} seconds",
                started_at=started_at,
                duration_seconds=(datetime.now(timezone.utc) - started_at).total_seconds(),
                run_id=run_id,
            )

        await asyncio.sleep(poll_interval)


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
