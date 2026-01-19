"""Run a single GDPEval task with the new Task API.

This example demonstrates how to:
1. Load a GDPEval task using the Task facade
2. Execute it with execute_task()
3. Access the results

Usage:
    python examples/run_gdpeval_task.py [task_id]
"""

import asyncio
import sys

from h_arcane import execute_task
from h_arcane.benchmarks.common.workers import ReActWorker
from h_arcane.benchmarks.gdpeval.config import GDPEVAL_CONFIG
from h_arcane.benchmarks.gdpeval.loader import load_gdpeval_task


async def main(task_id: str = "task_001") -> None:
    """Run a single GDPEval task."""
    print(f"Loading task: {task_id}")

    # Create a worker with GDPEval configuration
    worker = ReActWorker(model="gpt-4o", config=GDPEVAL_CONFIG)

    # Load the task using the Task facade
    task = load_gdpeval_task(task_id, worker)

    print(f"Task name: {task.name}")
    print(f"Description: {task.description[:100]}...")
    print(f"Resources: {len(task.resources)} input files")
    print(f"Evaluator: {type(task.evaluator).__name__ if task.evaluator else 'None'}")
    print()

    # Execute the task
    print("Executing task...")
    result = await execute_task(task)

    # Print results
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Success: {result.success}")
    print(f"Run ID: {result.run_id}")
    print(f"Experiment ID: {result.experiment_id}")

    if hasattr(result, "score") and result.score is not None:
        print(f"Score: {result.score}")

    if result.task_results:
        for task_uuid, task_result in result.task_results.items():
            print(f"  Task {task_result.name}: {task_result.status}")

    if result.error:
        print(f"Error: {result.error}")


if __name__ == "__main__":
    # Get task ID from command line or use default
    task_id = sys.argv[1] if len(sys.argv) > 1 else "task_001"
    asyncio.run(main(task_id))
