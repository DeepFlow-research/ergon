"""GDPEval data loading and seeding helpers.

Reads the GDP parquet dataset and staged rubric JSONL to produce task
descriptions, reference file lists, and rubric payloads.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Parquet helpers
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=4)
def _load_parquet(parquet_path: str) -> Any:
    """Load and cache a parquet file.  Returns a ``pandas.DataFrame``."""
    import pandas as pd  # deferred so the module can be imported w/o pandas

    path = Path(parquet_path)
    if not path.exists():
        raise FileNotFoundError(
            f"GDPEval parquet not found at {path}.  "
            "Copy data from the curation pipeline into your data directory."
        )
    return pd.read_parquet(path)


def extract_task_description(
    task_id: str,
    parquet_path: Path | None = None,
) -> str:
    """Return the task prompt / description for *task_id*."""
    if parquet_path is None:
        raise ValueError("parquet_path is required")

    df = _load_parquet(str(parquet_path))
    row = df[df["task_id"] == task_id]
    if row.empty:
        raise ValueError(f"Task {task_id!r} not found in {parquet_path}")
    return str(row.iloc[0]["prompt"])


# ---------------------------------------------------------------------------
# Reference files
# ---------------------------------------------------------------------------


def find_reference_files(task_id: str, reference_dir: Path) -> list[Path]:
    """Locate reference / input files for *task_id*.

    Checks two locations:
      1. ``reference_dir/{task_id}/`` sub-directory
      2. Files matching ``{task_id}*`` in the root (legacy layout)
    """
    if not reference_dir.exists():
        return []

    files: list[Path] = []

    task_subdir = reference_dir / task_id
    if task_subdir.is_dir():
        files.extend(p for p in task_subdir.iterdir() if p.is_file())

    for p in reference_dir.glob(f"{task_id}*"):
        if p.is_file() and p not in files:
            files.append(p)

    return sorted(files)


# ---------------------------------------------------------------------------
# Rubric JSONL helpers
# ---------------------------------------------------------------------------


def load_task_ids(
    rubric_file: Path,
    *,
    limit: int | None = None,
) -> list[str]:
    """Read task IDs from the staged rubric JSONL file.

    Each line is a JSON object with at least a ``task_id`` key.
    """
    if not rubric_file.exists():
        raise FileNotFoundError(
            f"Rubric file not found at {rubric_file}.  "
            "Copy data from the curation pipeline into your data directory."
        )

    ids: list[str] = []
    with open(rubric_file) as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break
            data = json.loads(line)
            ids.append(data["task_id"])
    return ids


def load_rubric_data(
    rubric_file: Path,
) -> dict[str, dict]:
    """Load all rubrics from JSONL into ``{task_id: raw_dict}``."""
    if not rubric_file.exists():
        raise FileNotFoundError(f"Rubric file not found at {rubric_file}")

    rubrics: dict[str, dict] = {}
    with open(rubric_file) as f:
        for line in f:
            data = json.loads(line)
            rubrics[data["task_id"]] = data
    return rubrics


def load_single_rubric(
    task_id: str,
    rubric_file: Path,
) -> dict:
    """Load the rubric dict for a single *task_id*."""
    rubrics = load_rubric_data(rubric_file)
    if task_id not in rubrics:
        raise ValueError(f"Task {task_id!r} not found in {rubric_file}")
    return rubrics[task_id]
