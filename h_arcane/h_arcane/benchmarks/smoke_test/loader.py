"""Smoke test data loading using the Task facade.

This module provides functions to load smoke test tasks into the database
for pipeline validation.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel

from h_arcane.benchmarks.common.loader import load_benchmark_to_database
from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.core.task import Task

if TYPE_CHECKING:
    from h_arcane.core.worker import BaseWorker


class SmokeTestTask(BaseModel):
    """Simple task definition for smoke testing."""

    task_id: str
    description: str
    category: str


# Predefined smoke test tasks
SMOKE_TEST_TASKS = [
    SmokeTestTask(
        task_id="smoke_simple_001",
        description="Read the data file and summarize its contents. This is a basic single-step task.",
        category="simple",
    ),
    SmokeTestTask(
        task_id="smoke_analysis_001",
        description=(
            "Analyze the provided data and write a brief report of your findings. "
            "Focus on key patterns and insights."
        ),
        category="analysis",
    ),
    SmokeTestTask(
        task_id="smoke_multistep_001",
        description=(
            "Complete the following steps: "
            "1) Read the input file, "
            "2) Ask the stakeholder for clarification on the analysis scope, "
            "3) Analyze the data based on the response, "
            "4) Write the final output report."
        ),
        category="multistep",
    ),
    SmokeTestTask(
        task_id="smoke_qa_001",
        description=(
            "This task requires stakeholder interaction. "
            "Ask the stakeholder what format they want the output in, "
            "then produce a simple summary in that format."
        ),
        category="qa_interaction",
    ),
]


def _smoke_test_item_to_task(smoke_task: SmokeTestTask, worker: "BaseWorker") -> Task:
    """Convert a SmokeTestTask to a Task object."""
    return Task(
        name=smoke_task.task_id,
        description=smoke_task.description,
        assigned_to=worker,
        resources=[],  # Smoke test uses stub tools, no real resources needed
        evaluator=None,  # No evaluation for smoke test
    )


def load_smoke_test_to_database(
    limit: int | None = None,
    worker: "BaseWorker | None" = None,
) -> list[UUID]:
    """
    Load smoke test tasks into database using the Task facade.

    This function creates Task objects and uses the Task persistence layer
    to create Experiment, Run placeholder, and Resource records.

    Args:
        limit: Optional limit on number of tasks to load
        worker: The worker to assign to tasks (required)

    Returns:
        List of created experiment IDs

    Raises:
        ValueError: If worker is not provided

    Example:
        >>> from h_arcane.benchmarks.common.workers.react_worker import ReActWorker
        >>> from h_arcane.benchmarks.smoke_test.config import SMOKE_TEST_CONFIG
        >>> worker = ReActWorker(model="gpt-4o", config=SMOKE_TEST_CONFIG)
        >>> experiment_ids = load_smoke_test_to_database(worker=worker)
    """
    if worker is None:
        raise ValueError("worker is required for Task-based loading")

    tasks = SMOKE_TEST_TASKS[:limit] if limit else SMOKE_TEST_TASKS

    print(
        f"Loading {len(tasks)} smoke test tasks to database...",
        file=sys.stderr,
        flush=True,
    )

    return load_benchmark_to_database(
        items=iter(tasks),
        item_to_task=_smoke_test_item_to_task,
        benchmark_name=BenchmarkName.SMOKE_TEST.value,
        worker=worker,
        total=len(tasks),
    )


def get_smoke_test_tasks(limit: int | None = None) -> list[SmokeTestTask]:
    """Get smoke test task definitions (without loading to database).

    Args:
        limit: Optional limit on number of tasks to return

    Returns:
        List of SmokeTestTask objects
    """
    return SMOKE_TEST_TASKS[:limit] if limit else SMOKE_TEST_TASKS.copy()
