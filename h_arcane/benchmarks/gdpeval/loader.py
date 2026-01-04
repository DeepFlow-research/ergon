"""GDPEval data loading."""

import json
import mimetypes
import sys
import traceback
from pathlib import Path
from uuid import UUID
import pandas as pd

from sqlmodel import Session, select

from h_arcane.core.db.connection import get_engine
from h_arcane.core.db.models import Experiment, Resource
from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.gdpeval.rubric import GDPEvalStagedRubric, GDPEvalTask

# Default paths relative to project root
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"

# Cache for parquet data to avoid reloading
_parquet_cache: pd.DataFrame | None = None


def _load_parquet_cache() -> pd.DataFrame:
    """Load and cache parquet file."""
    global _parquet_cache
    if _parquet_cache is None:
        parquet_path = DATA_DIR / "raw" / "gdpeval.parquet"
        if not parquet_path.exists():
            raise FileNotFoundError(
                f"GDPEval parquet file not found at {parquet_path}. "
                "Please copy data from manager_agent_gym/curation/gdpeval/data to data/"
            )
        _parquet_cache = pd.read_parquet(parquet_path)
    return _parquet_cache


def extract_task_description(task_id: str) -> str:
    """Extract task description from gdpeval.parquet."""
    tasks_df = _load_parquet_cache()
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


def get_mime_type(file_path: Path) -> str:
    """Get MIME type from file extension using standard library."""
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "application/octet-stream"


def load_gdpeval_tasks(
    rubric_file: Path | None = None,
    reference_dir: Path | None = None,
    limit: int | None = None,
) -> list[GDPEvalTask]:
    """Load GDPEval tasks with their staged rubrics."""
    if rubric_file is None:
        rubric_file = DATA_DIR / "generated" / "staged_v2" / "staged_rubrics.jsonl"
    if reference_dir is None:
        reference_dir = DATA_DIR / "raw" / "reference_files"

    if not rubric_file.exists():
        raise FileNotFoundError(
            f"Rubric file not found at {rubric_file}. "
            "Please copy data from manager_agent_gym/curation/gdpeval/data to data/"
        )

    tasks = []
    total_lines = sum(1 for _ in open(rubric_file)) if limit else None
    current_limit = limit or total_lines or 0

    print(f"📂 Loading tasks from {rubric_file.name}...", file=sys.stderr)

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

    print(f"   ✅ Loaded {len(tasks)} tasks", file=sys.stderr)
    return tasks


def load_gdpeval_to_database(
    rubric_file: Path | None = None,
    reference_dir: Path | None = None,
    limit: int | None = None,
) -> list[UUID]:
    """Load GDPEval tasks into database."""
    tasks = load_gdpeval_tasks(rubric_file=rubric_file, reference_dir=reference_dir, limit=limit)
    return _load_to_database(tasks)


def _load_to_database(tasks: list[GDPEvalTask]) -> list[UUID]:
    """Load tasks into experiments table and create input Resource records."""
    experiment_ids = []
    total = len(tasks)

    print(f"💾 Saving {total} tasks to database...", file=sys.stderr, flush=True)

    # Create session directly (not using generator pattern with 'with')
    engine = get_engine()
    session = Session(engine)

    try:
        for idx, task in enumerate(tasks, 1):
            # Show progress
            print(
                f"   Processing task {idx}/{total}: {task.task_id[:8]}...",
                file=sys.stderr,
                flush=True,
            )

            # Check if experiment already exists
            existing_experiment = session.exec(
                select(Experiment).where(
                    Experiment.benchmark_name == BenchmarkName.GDPEVAL,
                    Experiment.task_id == task.task_id,
                )
            ).first()

            if existing_experiment:
                print(
                    f"      ⚠️  Experiment already exists (ID: {existing_experiment.id})",
                    file=sys.stderr,
                    flush=True,
                )
                experiment_ids.append(existing_experiment.id)

                # Check if resources exist for this experiment
                existing_resources = session.exec(
                    select(Resource).where(Resource.experiment_id == existing_experiment.id)
                ).all()

                if existing_resources:
                    print(
                        f"      ✅ Experiment already has {len(existing_resources)} resources, skipping",
                        file=sys.stderr,
                        flush=True,
                    )
                    continue
                else:
                    # Backfill: create resources for existing experiment
                    print(
                        f"      🔄 No resources found, creating {len(task.reference_files)} resources...",
                        file=sys.stderr,
                        flush=True,
                    )
                    experiment = existing_experiment
            else:
                # Create new experiment
                print("      Serializing rubric...", file=sys.stderr, flush=True)
                rubric_dict = task.rubric.model_dump()
                print(
                    f"      Rubric serialized ({len(str(rubric_dict))} chars)",
                    file=sys.stderr,
                    flush=True,
                )

                print("      Creating Experiment object...", file=sys.stderr, flush=True)
                experiment = Experiment(
                    benchmark_name=BenchmarkName.GDPEVAL,
                    task_id=task.task_id,
                    task_description=task.task_description,
                    ground_truth_rubric=rubric_dict,
                    benchmark_specific_data={},  # GDPEval doesn't need extra data
                    category=task.category,
                )
                print("      Adding experiment to session...", file=sys.stderr, flush=True)
                session.add(experiment)
                print("      Flushing to get ID...", file=sys.stderr, flush=True)
                session.flush()  # Flush to get the ID without committing
                print(f"      Got experiment ID: {experiment.id}", file=sys.stderr, flush=True)
                experiment_ids.append(experiment.id)

            # Create Resource records for input files (not JSON)
            print(
                f"      Processing {len(task.reference_files)} reference files...",
                file=sys.stderr,
                flush=True,
            )
            for ref_idx, ref_file in enumerate(task.reference_files, 1):
                print(
                    f"         File {ref_idx}/{len(task.reference_files)}: {ref_file.name}",
                    file=sys.stderr,
                    flush=True,
                )

                # Store path relative to DATA_DIR for portability between local and Docker
                # ref_file is already relative to reference_dir, which is DATA_DIR / "raw" / "reference_files"
                # So we need to get the path relative to DATA_DIR
                try:
                    # Try to make path relative to DATA_DIR
                    file_path_relative = ref_file.relative_to(DATA_DIR)
                    file_path_str = str(file_path_relative)
                except ValueError:
                    # If ref_file is not relative to DATA_DIR, store as absolute (fallback)
                    file_path_str = str(ref_file.absolute())

                resource = Resource(
                    experiment_id=experiment.id,
                    run_id=None,  # Input files don't belong to a run
                    name=ref_file.name,
                    mime_type=get_mime_type(ref_file),
                    file_path=file_path_str,
                    size_bytes=ref_file.stat().st_size,
                )
                session.add(resource)
            print(f"      ✅ Task {idx} processed", file=sys.stderr, flush=True)

        # Commit all at once
        print("   Committing all changes...", file=sys.stderr, flush=True)
        session.commit()
        print("   ✅ Commit successful!", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"   ❌ Error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        session.rollback()
        traceback.print_exc(file=sys.stderr)
        raise
    finally:
        session.close()

    print(f"   ✅ Saved {total} experiments to database", file=sys.stderr, flush=True)
    return experiment_ids
