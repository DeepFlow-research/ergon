"""Run a multi-step DAG workflow with the Task API.

This example demonstrates how to:
1. Create a workflow with multiple tasks and dependencies
2. Execute the entire workflow with execute_task()
3. Track progress through the DAG

The workflow demonstrates a simple research pipeline:
  research -> analyze -> report (sequential dependencies)

Usage:
    python examples/run_dag_workflow.py
"""

import asyncio

from h_arcane import Task, execute_task
from h_arcane.benchmarks.common.workers import ReActWorker
from h_arcane.benchmarks.gdpeval.config import GDPEVAL_CONFIG


async def main() -> None:
    """Run a multi-step DAG workflow."""
    print("Creating DAG workflow...")

    # Create a worker (all tasks use the same worker in this example)
    worker = ReActWorker(model="gpt-4o", config=GDPEVAL_CONFIG)

    # Define tasks with dependencies
    # Task 1: Research (no dependencies - can start immediately)
    research = Task(
        name="Research",
        description=(
            "Gather information about the current state of AI benchmarking. "
            "Identify key metrics, popular benchmarks, and recent trends. "
            "Save your findings to a file called research_notes.md"
        ),
        assigned_to=worker,
    )

    # Task 2: Analyze (depends on Research completing)
    analyze = Task(
        name="Analyze",
        description=(
            "Based on the research notes, analyze the strengths and weaknesses "
            "of current AI benchmarking approaches. Identify gaps in existing "
            "benchmarks. Save your analysis to analysis.md"
        ),
        assigned_to=worker,
        depends_on=[research],  # Waits for research to complete
    )

    # Task 3: Report (depends on Analyze completing)
    report = Task(
        name="Report",
        description=(
            "Write a 1-page executive summary of the analysis findings. "
            "Include key recommendations for improving AI benchmarking. "
            "Format the report professionally and save to report.md"
        ),
        assigned_to=worker,
        depends_on=[analyze],  # Waits for analysis to complete
    )

    # Create the parent workflow task
    workflow = Task(
        name="Research Workflow",
        description="End-to-end research workflow: research -> analyze -> report",
        assigned_to=worker,
        children=[research, analyze, report],  # Contains all subtasks
    )

    print(f"Workflow: {workflow.name}")
    print("Tasks:")
    print(f"  1. {research.name} (no dependencies)")
    print(f"  2. {analyze.name} (depends on: {research.name})")
    print(f"  3. {report.name} (depends on: {analyze.name})")
    print()

    # Execute the workflow
    print("Executing workflow...")
    print("=" * 60)

    result = await execute_task(workflow)

    # Print results
    print()
    print("=" * 60)
    print("WORKFLOW RESULTS")
    print("=" * 60)
    print(f"Success: {result.success}")
    print(f"Run ID: {result.run_id}")
    print()

    if result.task_results:
        print("Task Results:")
        for task_id, task_result in result.task_results.items():
            status_emoji = {
                "completed": "[ok]",
                "failed": "[fail]",
                "running": "[running]",
                "pending": "[pending]",
                "ready": "[ready]",
            }.get(task_result.status, "[?]")
            print(f"  {status_emoji} {task_result.name}: {task_result.status}")

    if result.error:
        print(f"\nWorkflow Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())
