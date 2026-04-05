"""ResearchRubrics data loading using the Task facade.

This module provides functions to load ResearchRubrics samples from HuggingFace:
- load_researchrubrics_task(): Load a single sample as a Task object
- load_researchrubrics_to_database(): Bulk load samples using the Task persistence layer
"""

from __future__ import annotations

import functools
import sys
from typing import TYPE_CHECKING, Any
from uuid import UUID

from datasets import Dataset, load_dataset
from huggingface_hub import HfApi

from h_arcane.benchmarks.common.loader import load_benchmark_to_database
from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from h_arcane.benchmarks.researchrubrics.schemas import RubricCriterion
from h_arcane.core.task import Task

if TYPE_CHECKING:
    from h_arcane.core.worker import BaseWorker


def get_ablated_dataset_name() -> str:
    """Get ablated dataset name from HuggingFace credentials.

    Returns:
        Dataset name in format "{username}/researchrubrics-ablated"

    Raises:
        RuntimeError: If not logged in to HuggingFace
    """
    api = HfApi()
    try:
        user_info = api.whoami()
        username = user_info["name"]
        return f"{username}/researchrubrics-ablated"
    except Exception as e:
        raise RuntimeError(
            "Could not determine HuggingFace username. "
            "Please run 'huggingface-cli login' or provide ablated_dataset_name explicitly."
        ) from e


@functools.lru_cache(maxsize=4)
def _load_dataset_cached(ablated_dataset_name: str) -> Dataset:
    """Load dataset with caching to avoid repeated downloads."""
    print(f"Loading dataset from HuggingFace: {ablated_dataset_name}...", file=sys.stderr)
    ds_dict = load_dataset(ablated_dataset_name)
    return ds_dict["train"]  # type: ignore[return-value]


def _find_sample_by_id(ds: Dataset, sample_id: str) -> dict[str, Any] | None:
    """Find a sample by its ID in the dataset."""
    for idx in range(len(ds)):
        row: dict[str, Any] = ds[idx]  # type: ignore[index]
        if row["sample_id"] == sample_id:
            return row
    return None


def load_researchrubrics_task(
    sample_id: str,
    worker: "BaseWorker",
    ablated_dataset_name: str | None = None,
) -> Task:
    """
    Load a single ResearchRubrics sample as a Task object.

    This function returns a Task that is NOT yet persisted - the caller
    decides whether to execute it immediately or persist it first.

    Args:
        sample_id: The ResearchRubrics sample ID
        worker: The worker to assign to this task
        ablated_dataset_name: Optional HuggingFace dataset name

    Returns:
        A Task object ready for execution or persistence

    Example:
        >>> worker = ReActWorker(model="gpt-4o", config=RESEARCHRUBRICS_CONFIG)
        >>> task = load_researchrubrics_task("sample_001", worker)
        >>> result = await execute_task(task)
    """
    # Auto-detect dataset name if not provided
    if ablated_dataset_name is None:
        ablated_dataset_name = get_ablated_dataset_name()

    # Load dataset
    ds = _load_dataset_cached(ablated_dataset_name)

    # Find the specific sample
    row = _find_sample_by_id(ds, sample_id)
    if row is None:
        raise ValueError(f"Sample {sample_id} not found in dataset {ablated_dataset_name}")

    # Parse rubrics into RubricCriterion objects
    rubric_criteria = [
        RubricCriterion(
            criterion=r["criterion"],
            axis=r["axis"],
            weight=r["weight"],
        )
        for r in row["rubrics"]
    ]

    # Create rubric evaluator
    rubric = ResearchRubricsRubric(
        benchmark="researchrubrics",
        rubric_criteria=rubric_criteria,
    )

    # ResearchRubrics has no input files - just the ablated prompt
    return Task(
        name=sample_id,
        description=row["ablated_prompt"],
        assigned_to=worker,
        resources=[],  # ResearchRubrics samples don't have input files
        evaluator=rubric,
    )


def _researchrubrics_item_to_task(row: dict[str, Any], worker: "BaseWorker") -> Task:
    """Convert a ResearchRubrics dataset row to a Task object."""
    # Parse rubrics into RubricCriterion objects
    rubric_criteria = [
        RubricCriterion(
            criterion=r["criterion"],
            axis=r["axis"],
            weight=r["weight"],
        )
        for r in row["rubrics"]
    ]

    # Create rubric evaluator
    rubric = ResearchRubricsRubric(
        benchmark="researchrubrics",
        rubric_criteria=rubric_criteria,
    )

    return Task(
        name=row["sample_id"],
        description=row["ablated_prompt"],
        assigned_to=worker,
        resources=[],  # ResearchRubrics samples don't have input files
        evaluator=rubric,
    )


def load_researchrubrics_to_database(
    ablated_dataset_name: str | None = None,
    limit: int | None = None,
    worker: "BaseWorker | None" = None,
) -> list[UUID]:
    """
    Load ResearchRubrics from HuggingFace dataset into database using Task facade.

    This function creates Task objects and uses the Task persistence layer
    to create Experiment, Run placeholder, and Resource records.

    Args:
        ablated_dataset_name: HuggingFace dataset name for ablated dataset
                             (e.g., "{username}/researchrubrics-ablated").
                             If None, auto-detects from HuggingFace credentials.
        limit: Optional limit on number of tasks to load
        worker: The worker to assign to tasks (required for Task-based loading)

    Returns:
        List of created experiment IDs

    Raises:
        ValueError: If worker is not provided

    Example:
        >>> worker = ReActWorker(model="gpt-4o", config=RESEARCHRUBRICS_CONFIG)
        >>> experiment_ids = load_researchrubrics_to_database(worker=worker, limit=10)
    """
    if worker is None:
        raise ValueError("worker is required for Task-based loading")

    # Auto-detect dataset name if not provided
    if ablated_dataset_name is None:
        ablated_dataset_name = get_ablated_dataset_name()
        print(f"Using ablated dataset: {ablated_dataset_name}", file=sys.stderr)

    # Load dataset
    ds = _load_dataset_cached(ablated_dataset_name)

    if limit:
        ds = ds.select(range(min(limit, len(ds))))
        print(f"   Limited to {len(ds)} samples", file=sys.stderr)

    # Convert dataset to list of dicts for the generic loader
    rows = [ds[idx] for idx in range(len(ds))]

    print(f"Saving {len(rows)} tasks to database using Task facade...", file=sys.stderr, flush=True)

    return load_benchmark_to_database(
        items=iter(rows),
        item_to_task=_researchrubrics_item_to_task,
        benchmark_name=BenchmarkName.RESEARCHRUBRICS.value,
        worker=worker,
        total=len(rows),
    )
