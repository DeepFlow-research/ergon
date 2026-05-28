"""ResearchRubrics source-loading helpers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any, cast

from datasets import load_dataset
from ergon_core.core.shared.settings import settings

from ergon_builtins.benchmarks.researchrubrics.task import (
    RESEARCH_RUBRICS_DATASET,
    _payload_from_row,
)
from ergon_builtins.benchmarks.researchrubrics.task_schemas import ResearchRubricsTaskPayload


def iter_researchrubrics_rows(
    *,
    dataset_name: str = RESEARCH_RUBRICS_DATASET,
    split: str = "train",
    limit: int | None = None,
) -> Iterator[ResearchRubricsTaskPayload]:
    yield from load_researchrubrics_rows(dataset_name=dataset_name, split=split, limit=limit)


def load_researchrubrics_rows(
    *,
    dataset_name: str = RESEARCH_RUBRICS_DATASET,
    split: str = "train",
    limit: int | None = None,
) -> Sequence[ResearchRubricsTaskPayload]:
    ds = load_dataset(dataset_name, token=settings.hf_api_key)
    split_ds = ds[split]
    if limit is not None:
        split_ds = split_ds.select(range(min(limit, len(split_ds))))
    return [
        _payload_from_row(cast(Mapping[str, Any], split_ds[idx])) for idx in range(len(split_ds))
    ]
