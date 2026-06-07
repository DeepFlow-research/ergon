"""SWE-Bench Verified source-loading helpers."""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from datasets import load_dataset

from ergon_builtins.benchmarks.swebench_verified.task import HF_DATASET_ID, HF_SPLIT
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchInstance


def iter_swebench_rows(
    *,
    dataset_id: str = HF_DATASET_ID,
    split: str = HF_SPLIT,
    limit: int | None = None,
    streaming: bool = False,
) -> Iterator[SWEBenchInstance]:
    ds = load_dataset(dataset_id, split=split, streaming=streaming)
    for index, row in enumerate(ds):
        if limit is not None and index >= limit:
            break
        yield SWEBenchInstance.from_raw(row)


def load_swebench_rows(
    *,
    dataset_id: str = HF_DATASET_ID,
    split: str = HF_SPLIT,
    limit: int | None = None,
) -> Sequence[SWEBenchInstance]:
    ds = load_dataset(dataset_id, split=split)
    if limit is not None:
        ds = ds.select(range(min(limit, len(ds))))
    return [SWEBenchInstance.from_raw(row) for row in ds]
