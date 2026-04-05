"""GDPEval data loading using the Task facade.

This module provides two main functions:
- load_gdpeval_task(): Load a single GDPEval task as a Task object
- load_gdpeval_to_database(): Bulk load tasks using the Task persistence layer
"""

from __future__ import annotations

import functools
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import pandas as pd

from h_arcane.benchmarks.common.loader import load_benchmark_to_database
from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.gdpeval.rubric import GDPEvalStagedRubric, GDPEvalTask
from h_arcane.core.settings import settings
from h_arcane.core.task import Resource, Task

if TYPE_CHECKING:
    from h_arcane.core.worker import BaseWorker


def get_data_dir() -> Path:
    """Get the data directory path from settings."""
    return settings.data_dir


@functools.lru_cache(maxsize=1)
def _load_parquet() -> pd.DataFrame:
    """Load parquet file (cached)."""
    parquet_path = get_data_dir() / "raw" / "gdpeval.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"GDPEval parquet file not found at {parquet_path}. "
            "Please copy data from manager_agent_gym/curation/gdpeval/data to data/"
        )
    return pd.read_parquet(parquet_path)


def extract_task_description(task_id: str) -> str:
    """Extract task description from gdpeval.parquet."""
    tasks_df = _load_parquet()
    task_row = tasks_df[tasks_df["task_id"] == task_id]
    if task_row.empty:
        raise ValueError(f"Task {task_id} not found in gdpeval.parquet")

    # The parquet file uses 'prompt' column
    row = task_row.iloc[0]
    if "prompt" not in row:
        raise ValueError(f"Column 'prompt' not found in gdpeval.parquet for task {task_id}")
    return row["prompt"]


def find_reference_files(task_id: str, reference_dir: Path) -> list[Path]:
    """Find reference files for a task.

    Checks multiple locations:
    1. Subdirectory named exactly {task_id}/
    2. Files with {task_id}* prefix in root (legacy format)
    """
    if not reference_dir.exists():
        return []

    task_files = []

    # Strategy 1: Check for subdirectory named exactly {task_id}
    task_subdir = reference_dir / task_id
    if task_subdir.exists() and task_subdir.is_dir():
        for file_path in task_subdir.iterdir():
            if file_path.is_file():
                task_files.append(file_path)

    # Strategy 2: Check for files with {task_id}* prefix in root (legacy format)
    for file_path in reference_dir.glob(f"{task_id}*"):
        if file_path.is_file():
            task_files.append(file_path)

    return sorted(task_files)


def _load_rubric_data(
    rubric_file: Path,
) -> dict[str, GDPEvalStagedRubric]:
    """Load all rubrics from JSONL file into a lookup dict."""
    rubrics: dict[str, GDPEvalStagedRubric] = {}
    with open(rubric_file) as f:
        for line in f:
            data = json.loads(line)
            staged_rubric = GDPEvalStagedRubric(**data)
            rubrics[staged_rubric.task_id] = staged_rubric
    return rubrics


def load_gdpeval_task(
    task_id: str,
    worker: "BaseWorker",
    rubric_file: Path | None = None,
    reference_dir: Path | None = None,
) -> Task:
    """
    Load a single GDPEval task as a Task object.

    This function returns a Task that is NOT yet persisted - the caller
    decides whether to execute it immediately or persist it first.

    Args:
        task_id: The GDPEval task ID (e.g., "task_001")
        worker: The worker to assign to this task
        rubric_file: Optional path to staged rubrics JSONL file
        reference_dir: Optional path to reference files directory

    Returns:
        A Task object ready for execution or persistence

    Example:
        >>> worker = ReActWorker(model="gpt-4o", config=GDPEVAL_CONFIG)
        >>> task = load_gdpeval_task("task_001", worker)
        >>> result = await execute_task(task)
    """
    if rubric_file is None:
        rubric_file = get_data_dir() / "generated" / "staged_v2" / "staged_rubrics.jsonl"
    if reference_dir is None:
        reference_dir = get_data_dir() / "raw" / "reference_files"

    if not rubric_file.exists():
        raise FileNotFoundError(
            f"Rubric file not found at {rubric_file}. "
            "Please copy data from manager_agent_gym/curation/gdpeval/data to data/"
        )

    # Load rubrics and find the specific one
    rubrics = _load_rubric_data(rubric_file)
    if task_id not in rubrics:
        raise ValueError(f"Task {task_id} not found in rubric file")

    staged_rubric = rubrics[task_id]

    # Get task description
    task_description = extract_task_description(task_id)

    # Get reference files
    reference_files = find_reference_files(task_id, reference_dir)

    # Create SDK Resources
    resources = [Resource(path=str(f), name=f.name) for f in reference_files]

    # Create and return Task
    return Task(
        name=task_id,
        description=task_description,
        assigned_to=worker,
        resources=resources,
        evaluator=staged_rubric.rubric,
    )


def load_gdpeval_tasks(
    rubric_file: Path | None = None,
    reference_dir: Path | None = None,
    limit: int | None = None,
) -> list[GDPEvalTask]:
    """Load GDPEval tasks with their staged rubrics (legacy format)."""
    if rubric_file is None:
        rubric_file = get_data_dir() / "generated" / "staged_v2" / "staged_rubrics.jsonl"
    if reference_dir is None:
        reference_dir = get_data_dir() / "raw" / "reference_files"

    if not rubric_file.exists():
        raise FileNotFoundError(
            f"Rubric file not found at {rubric_file}. "
            "Please copy data from manager_agent_gym/curation/gdpeval/data to data/"
        )

    tasks = []
    total_lines = sum(1 for _ in open(rubric_file)) if limit else None
    current_limit = limit or total_lines or 0

    print(f"Loading tasks from {rubric_file.name}...", file=sys.stderr)

    with open(rubric_file) as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break

            # Show progress
            if (i + 1) % 5 == 0 or (i + 1) == current_limit:
                print(f"   Loaded {i + 1}/{current_limit} tasks...", file=sys.stderr, end="\r")

            data = json.loads(line)
            staged_rubric = GDPEvalStagedRubric(**data)

            task = GDPEvalTask(
                task_id=staged_rubric.task_id,
                task_description=extract_task_description(staged_rubric.task_id),
                reference_files=find_reference_files(staged_rubric.task_id, reference_dir),
                rubric=staged_rubric.rubric,
                category=staged_rubric.rubric.category_name.split(" – ")[0],
            )
            tasks.append(task)

    print(f"   Loaded {len(tasks)} tasks", file=sys.stderr)
    return tasks


def _gdpeval_item_to_task(gdp_task: GDPEvalTask, worker: "BaseWorker") -> Task:
    """Convert a GDPEvalTask to a Task object."""
    sdk_resources = [Resource(path=str(f), name=f.name) for f in gdp_task.reference_files]
    return Task(
        name=gdp_task.task_id,
        description=gdp_task.task_description,
        assigned_to=worker,
        resources=sdk_resources,
        evaluator=gdp_task.rubric,
    )


def load_gdpeval_to_database(
    rubric_file: Path | None = None,
    reference_dir: Path | None = None,
    limit: int | None = None,
    worker: "BaseWorker | None" = None,
) -> list[UUID]:
    """
    Load GDPEval tasks into database using the Task facade.

    This function creates Task objects and uses the Task persistence layer
    to create Experiment, Run placeholder, and Resource records.

    Args:
        rubric_file: Optional path to staged rubrics JSONL file
        reference_dir: Optional path to reference files directory
        limit: Optional limit on number of tasks to load
        worker: The worker to assign to tasks (required for Task-based loading)

    Returns:
        List of created experiment IDs

    Raises:
        ValueError: If worker is not provided

    Example:
        >>> worker = ReActWorker(model="gpt-4o", config=GDPEVAL_CONFIG)
        >>> experiment_ids = load_gdpeval_to_database(worker=worker, limit=10)
    """
    if worker is None:
        raise ValueError("worker is required for Task-based loading")

    if rubric_file is None:
        rubric_file = get_data_dir() / "generated" / "staged_v2" / "staged_rubrics.jsonl"
    if reference_dir is None:
        reference_dir = get_data_dir() / "raw" / "reference_files"

    # Load legacy tasks for compatibility with existing data structures
    legacy_tasks = load_gdpeval_tasks(
        rubric_file=rubric_file,
        reference_dir=reference_dir,
        limit=limit,
    )

    print(
        f"Saving {len(legacy_tasks)} tasks to database using Task facade...",
        file=sys.stderr,
        flush=True,
    )

    return load_benchmark_to_database(
        items=iter(legacy_tasks),
        item_to_task=_gdpeval_item_to_task,
        benchmark_name=BenchmarkName.GDPEVAL.value,
        worker=worker,
        total=len(legacy_tasks),
    )
