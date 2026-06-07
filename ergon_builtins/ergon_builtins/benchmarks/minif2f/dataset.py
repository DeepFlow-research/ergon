"""MiniF2F source-loading helpers."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path

from huggingface_hub import hf_hub_download

from ergon_builtins.benchmarks.minif2f.task import HF_FILENAME, HF_REPO_ID
from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem


def iter_minif2f_rows(
    *,
    split: str = "validation",
    data_dir: Path | None = None,
    limit: int | None = None,
) -> Iterator[MiniF2FProblem]:
    del split
    yield from load_minif2f_rows(data_dir=data_dir, limit=limit)


def load_minif2f_rows(
    *,
    split: str = "validation",
    data_dir: Path | None = None,
    limit: int | None = None,
) -> Sequence[MiniF2FProblem]:
    del split
    cache_dir = str(data_dir) if data_dir else None
    jsonl_path = Path(
        hf_hub_download(
            repo_id=HF_REPO_ID,
            filename=HF_FILENAME,
            repo_type="dataset",
            cache_dir=cache_dir,
        )
    )
    rows: list[MiniF2FProblem] = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            raw = json.loads(stripped)
            rows.append(
                MiniF2FProblem(
                    name=raw["name"],
                    informal_statement=raw["informal_statement"],
                    formal_statement=raw["formal_statement"],
                    header=raw["header"],
                )
            )
            if limit is not None and len(rows) >= limit:
                break
    return rows
