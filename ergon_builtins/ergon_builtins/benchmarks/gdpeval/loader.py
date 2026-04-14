"""GDPEval data loading helpers — backed by HuggingFace Hub.

All data is fetched from cm2435-new/gdpval_preference_rubrics and cached
locally in ~/.cache/huggingface/hub/ on first access.  Subsequent calls
within the same process (or across processes) hit the local cache for free.
"""

import functools
import json
from pathlib import Path
from typing import Any

HF_REPO_ID = "cm2435-new/gdpval_preference_rubrics"
_HF_REPO_TYPE = "dataset"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _rubric_filename(split: str) -> str:
    """Map split name to HF repo filename."""
    if split == "train":
        return "rubrics/train_rubrics.jsonl"
    if split == "eval":
        return "rubrics/eval_rubrics.jsonl"
    if split == "full":
        return "rubrics/staged_rubrics.jsonl"
    raise ValueError(f"Unknown split {split!r} — expected 'train', 'eval', or 'full'")


@functools.lru_cache(maxsize=4)
def _load_parquet(repo_id: str) -> Any:  # slopcop: ignore[no-typing-any]
    """Download gdpeval.parquet from HF and cache the DataFrame in-process."""
    # Deferred: optional dependency
    import pandas as pd

    # Deferred: optional dependency
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        repo_id=repo_id,
        filename="gdpeval.parquet",
        repo_type=_HF_REPO_TYPE,
    )
    return pd.read_parquet(path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_task_description(
    task_id: str,
    repo_id: str = HF_REPO_ID,
) -> str:
    """Return the task prompt for *task_id* from the HF parquet."""
    df = _load_parquet(repo_id)
    row = df[df["task_id"] == task_id]
    if row.empty:
        raise ValueError(f"Task {task_id!r} not found in parquet ({repo_id})")
    return str(row.iloc[0]["prompt"])


def find_reference_files(
    task_id: str,
    repo_id: str = HF_REPO_ID,
) -> list[Path]:
    """Download and return local paths to reference files for *task_id*.

    Files are fetched from ``reference_files/{task_id}/`` in the HF repo and
    cached in ``~/.cache/huggingface/hub/``.  Only this task's files are
    downloaded — not the full 1.5 GB corpus.
    """
    # Deferred: optional dependency
    from huggingface_hub import snapshot_download

    local_dir = snapshot_download(
        repo_id=repo_id,
        repo_type=_HF_REPO_TYPE,
        allow_patterns=[f"reference_files/{task_id}/*"],
    )
    task_dir = Path(local_dir) / "reference_files" / task_id
    if not task_dir.exists():
        return []
    return sorted(p for p in task_dir.iterdir() if p.is_file())


def load_task_ids(
    split: str = "train",
    repo_id: str = HF_REPO_ID,
    *,
    limit: int | None = None,
) -> list[str]:
    """Read task IDs from the HF rubric JSONL for *split*.

    Args:
        split:   One of ``"train"`` (176), ``"eval"`` (44), or ``"full"`` (220).
        repo_id: HF dataset repo to pull from.
        limit:   If set, return at most this many IDs.
    """
    # Deferred: optional dependency
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        repo_id=repo_id,
        filename=_rubric_filename(split),
        repo_type=_HF_REPO_TYPE,
    )
    ids: list[str] = []
    with open(path) as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break
            ids.append(json.loads(line)["task_id"])
    return ids


def load_rubric_data(
    split: str = "train",
    repo_id: str = HF_REPO_ID,
) -> dict[str, dict]:  # slopcop: ignore[no-typing-any]
    """Load all rubrics from HF into ``{task_id: raw_dict}`` for *split*."""
    # Deferred: optional dependency
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        repo_id=repo_id,
        filename=_rubric_filename(split),
        repo_type=_HF_REPO_TYPE,
    )
    rubrics: dict[str, dict] = {}  # slopcop: ignore[no-typing-any]
    with open(path) as f:
        for line in f:
            data = json.loads(line)
            rubrics[data["task_id"]] = data
    return rubrics


def load_single_rubric(
    task_id: str,
    split: str = "train",
    repo_id: str = HF_REPO_ID,
) -> dict:  # slopcop: ignore[no-typing-any]
    """Load the rubric dict for a single *task_id* from *split*."""
    rubrics = load_rubric_data(split, repo_id)
    if task_id not in rubrics:
        raise ValueError(f"Task {task_id!r} not found in {split!r} split ({repo_id})")
    return rubrics[task_id]
