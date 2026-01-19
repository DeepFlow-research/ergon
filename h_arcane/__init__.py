"""
H-ARCANE: Task and workflow execution for AI research.

Usage:
    from h_arcane import Task, execute_task, BaseWorker, Resource

    # Create a worker
    worker = ReactWorker(model="gpt-4o", tools=[...])

    # Define a task with worker assignment
    task = Task(
        name="Analyze Data",
        description="Process the quarterly report",
        assigned_to=worker,
        resources=[Resource(path="data/report.xlsx", name="Quarterly Report")],
    )

    # Run - worker is already on the task
    result = await execute_task(task)
    print(f"Success: {result.success}, Score: {result.score}")

For workflows (DAGs):
    a = Task(name="Research", description="...", assigned_to=researcher)
    b = Task(name="Write", description="...", assigned_to=writer, depends_on=[a])
    workflow = Task(name="Report", description="...", assigned_to=writer, children=[a, b])
    result = await execute_task(workflow)

For benchmark tasks:
    from h_arcane import load_gdpeval_task, load_minif2f_task, load_researchrubrics_task

    # Load a single benchmark task
    task = load_gdpeval_task("task_001", worker)
    result = await execute_task(task)
"""

__version__ = "0.1.0"

# Public API - Task definition
from h_arcane.core.status import TaskStatus
from h_arcane.core.task import Resource, Task

# Public API - Worker protocol
from h_arcane.core.worker import (
    BaseWorker,
    NamedTool,
    Tool,
    WorkerContext,
    WorkerResult,
    QAExchange,
)

# Re-export Action from internal for worker implementations
from h_arcane.core._internal.db.models import Action

# Public API - Execution
from h_arcane.core.runner import ExecutionResult, TaskResult, execute_task

# Benchmark task loaders
from h_arcane.benchmarks.gdpeval.loader import load_gdpeval_task
from h_arcane.benchmarks.minif2f.loader import load_minif2f_task
from h_arcane.benchmarks.researchrubrics.loader import load_researchrubrics_task

# Rebuild Task model to resolve forward references (BaseWorker)
# AnyRubric is optional - will be resolved lazily when benchmarks are used
Task.model_rebuild(_types_namespace={"BaseWorker": BaseWorker})

__all__ = [
    # Task definition
    "Task",
    "TaskStatus",
    "Resource",
    # Worker protocol
    "BaseWorker",
    "WorkerContext",
    "WorkerResult",
    "QAExchange",
    "Action",
    "Tool",
    "NamedTool",
    # Execution
    "execute_task",
    "ExecutionResult",
    "TaskResult",
    # Benchmark task loaders
    "load_gdpeval_task",
    "load_minif2f_task",
    "load_researchrubrics_task",
]
