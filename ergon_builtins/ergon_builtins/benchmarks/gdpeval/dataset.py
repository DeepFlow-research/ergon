"""GDPEval source-loading helpers."""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from ergon_builtins.benchmarks.gdpeval.loader import (
    HF_REPO_ID,
    find_reference_files,
    load_task_ids,
)
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig


def iter_gdpeval_rows(
    *,
    dataset_repo: str = HF_REPO_ID,
    split: str = "train",
    limit: int | None = None,
) -> Iterator[GDPTaskConfig]:
    yield from load_gdpeval_rows(dataset_repo=dataset_repo, split=split, limit=limit)


def load_gdpeval_rows(
    *,
    dataset_repo: str = HF_REPO_ID,
    split: str = "train",
    limit: int | None = None,
) -> Sequence[GDPTaskConfig]:
    configs: list[GDPTaskConfig] = []
    for task_id in load_task_ids(split=split, repo_id=dataset_repo, limit=limit):
        ref_files = find_reference_files(task_id, repo_id=dataset_repo)
        configs.append(
            GDPTaskConfig(
                task_id=task_id,
                workflow_type="document_processing",
                reference_files=[str(path) for path in ref_files],
            )
        )
    return configs
