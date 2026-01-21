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

import typer
from rich.console import Console
from rich.table import Table

from h_arcane.benchmarks.smoke_test.config import SMOKE_TEST_CONFIG
from h_arcane.benchmarks.smoke_test.workflows import (
    WORKFLOW_FACTORIES,
    create_workflow,
    list_workflows,
)
from h_arcane.benchmarks.common.workers.react_worker import ReActWorker
from h_arcane.core.runner import execute_task

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
    """Run workflows and collect results."""
    from h_arcane.core.runner import ExecutionResult

    results: dict[str, ExecutionResult] = {}

    for name in workflow_names:
        console.print(f"\n[bold cyan]Running workflow: {name}[/bold cyan]")

        # Create worker with smoke test config
        worker = ReActWorker(model=model, config=SMOKE_TEST_CONFIG)

        # Create workflow
        task = create_workflow(name, worker)

        console.print(f"  Task: {task.name}")
        console.print(f"  Description: {task.description[:60]}...")

        # Execute
        try:
            result = await execute_task(
                task,
                timeout_seconds=timeout,
                benchmark_name="smoke_test",
            )
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
            # Create a failed result for the summary
            from datetime import datetime, timezone

            from h_arcane.core.task import TaskStatus

            results[name] = ExecutionResult(
                success=False,
                status=TaskStatus.FAILED,
                error=str(e),
                started_at=datetime.now(timezone.utc),
                duration_seconds=0.0,
            )

    return results


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
