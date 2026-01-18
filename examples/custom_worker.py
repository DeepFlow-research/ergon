"""Implement a custom worker using the BaseWorker protocol.

This example demonstrates how to:
1. Create a custom worker that implements the BaseWorker protocol
2. Use the custom worker with the Task API
3. Return structured results from worker execution

Custom workers are useful for:
- Testing task execution without real AI models
- Implementing specialized execution logic
- Creating mock workers for unit tests

Usage:
    python examples/custom_worker.py
"""

import asyncio
from uuid import uuid4

from h_arcane import Task, execute_task
from h_arcane.core.worker import WorkerContext, WorkerResult


class DummyWorker:
    """A minimal worker that returns fixed responses for testing.

    This worker implements the BaseWorker protocol, which requires:
    - id: UUID identifying the worker
    - name: Human-readable name
    - model: Model identifier (can be empty for non-AI workers)
    - tools: List of tools (can be empty)
    - system_prompt: System prompt (can be empty)
    - execute(task, context) -> WorkerResult: The main execution method
    """

    def __init__(self, model: str = "dummy-v1"):
        """Initialize the dummy worker.

        Args:
            model: Model identifier for logging purposes
        """
        self.id = uuid4()
        self.name = "dummy_worker"
        self.model = model
        self.tools: list = []
        self.system_prompt = "You are a dummy worker for testing."

    async def execute(self, task: Task, context: WorkerContext) -> WorkerResult:
        """Execute the task and return a fixed response.

        In a real worker, this method would:
        1. Process the task description
        2. Use context.input_resources to access input files
        3. Perform the actual work (AI inference, API calls, etc.)
        4. Return structured results

        Args:
            task: The Task to execute
            context: Execution context with resources and metadata

        Returns:
            WorkerResult with success status and outputs
        """
        # Log what we're doing
        print(f"  Executing task: {task.name}")
        print(f"  Description: {task.description[:50]}...")
        print(f"  Input resources: {len(context.input_resources)}")

        # Simulate some work
        await asyncio.sleep(0.1)

        # Return a successful result
        return WorkerResult(
            success=True,
            actions=[],  # No actions logged
            outputs=[],  # No output files
            output_text=f"Dummy response for task: {task.name}\n"
            f"Processed {len(context.input_resources)} input resources.",
        )


class EchoWorker:
    """A worker that echoes the task description.

    This is slightly more sophisticated than DummyWorker - it actually
    processes the task description and returns it in the output.
    """

    def __init__(self, prefix: str = "Echo"):
        self.id = uuid4()
        self.name = "echo_worker"
        self.model = "echo-v1"
        self.tools: list = []
        self.system_prompt = "You echo the task description."
        self.prefix = prefix

    async def execute(self, task: Task, context: WorkerContext) -> WorkerResult:
        """Echo the task description."""
        output = f"[{self.prefix}] {task.description}"
        return WorkerResult(
            success=True,
            actions=[],
            outputs=[],
            output_text=output,
        )


async def main() -> None:
    """Demonstrate custom worker usage."""
    print("Custom Worker Example")
    print("=" * 60)
    print()

    # Example 1: DummyWorker
    print("1. DummyWorker")
    print("-" * 40)

    dummy_worker = DummyWorker(model="test-model")
    task1 = Task(
        name="Test Task",
        description="This is a test task for the dummy worker.",
        assigned_to=dummy_worker,
    )

    print(f"Worker: {dummy_worker.name} (id: {dummy_worker.id})")
    print(f"Task: {task1.name}")
    print()

    result1 = await execute_task(task1)
    print(f"Success: {result1.success}")
    print(f"Run ID: {result1.run_id}")
    print()

    # Example 2: EchoWorker
    print("2. EchoWorker")
    print("-" * 40)

    echo_worker = EchoWorker(prefix="ECHO")
    task2 = Task(
        name="Echo Task",
        description="Hello, World! This message will be echoed back.",
        assigned_to=echo_worker,
    )

    print(f"Worker: {echo_worker.name}")
    print(f"Task: {task2.name}")
    print()

    result2 = await execute_task(task2)
    print(f"Success: {result2.success}")
    print()

    # Example 3: Multiple tasks with different workers
    print("3. Multiple Workers in a Workflow")
    print("-" * 40)

    worker_a = DummyWorker(model="worker-a")
    worker_b = EchoWorker(prefix="B")

    task_a = Task(
        name="Task A",
        description="First task handled by worker A",
        assigned_to=worker_a,
    )
    task_b = Task(
        name="Task B",
        description="Second task that depends on A",
        assigned_to=worker_b,
        depends_on=[task_a],
    )

    workflow = Task(
        name="Multi-Worker Workflow",
        description="A workflow using multiple custom workers",
        assigned_to=worker_a,
        children=[task_a, task_b],
    )

    print(f"Workflow: {workflow.name}")
    print(f"  Task A: assigned to {worker_a.name}")
    print(f"  Task B: assigned to {worker_b.name}, depends on Task A")
    print()

    result3 = await execute_task(workflow)
    print(f"Workflow Success: {result3.success}")

    if result3.task_results:
        print("Task Results:")
        for tid, tr in result3.task_results.items():
            print(f"  - {tr.name}: {tr.status}")


if __name__ == "__main__":
    asyncio.run(main())
