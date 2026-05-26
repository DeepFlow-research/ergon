"""MiniF2F sample-producing environment."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from ergon_core.api import Environment, Sample, Task
from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker
from huggingface_hub import hf_hub_download
from pydantic import Field

from ergon_builtins.benchmarks.minif2f.benchmark import HF_FILENAME, HF_REPO_ID, MiniF2FTask
from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem, MiniF2FTaskPayload
from ergon_builtins.benchmarks.minif2f.worker_factory import (
    make_minif2f_rubric,
    make_minif2f_worker,
)
from ergon_builtins.environments._resolve import (
    resolve_evaluators,
    resolve_sandbox,
    resolve_worker,
)


class MiniF2FRowLoader(Protocol):
    def iter_rows(self) -> Iterator[MiniF2FProblem]: ...

    def load_rows(self) -> Sequence[MiniF2FProblem]: ...


@dataclass(frozen=True)
class DefaultMiniF2FRowLoader:
    data_dir: Path | None = None
    limit: int | None = None

    def iter_rows(self) -> Iterator[MiniF2FProblem]:
        yield from self.load_rows()

    def load_rows(self) -> Sequence[MiniF2FProblem]:
        cache_dir = str(self.data_dir) if self.data_dir else None
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
                if self.limit is not None and len(rows) >= self.limit:
                    break
        return rows


class MiniF2FEnvironment(Environment):
    name: str = "minif2f"
    split: str = "validation"
    limit: int | None = None
    source_mode: Literal["materialized"] = "materialized"
    data_dir: Path | None = None
    loader: Any | None = None
    worker: Worker | Callable[[MiniF2FProblem], Worker] = Field(default_factory=make_minif2f_worker)
    evaluators: Sequence[Evaluator] | Callable[[MiniF2FProblem], Sequence[Evaluator]] = Field(
        default_factory=lambda: (make_minif2f_rubric(),)
    )
    sandbox: Sandbox | Callable[[MiniF2FProblem], Sandbox] = Field(default_factory=LeanSandbox)

    def iter_samples(self) -> Iterator[Sample]:
        for row in self._limit_rows(self._loader().iter_rows()):
            yield self._sample_from_row(row)

    def all_samples(self) -> Sequence[Sample]:
        if self.source_mode == "streaming":
            raise NotImplementedError("Streaming environments may not materialize all samples")
        return [self._sample_from_row(row) for row in self._limit_rows(self._loader().load_rows())]

    def _loader(self) -> MiniF2FRowLoader:
        return self.loader or DefaultMiniF2FRowLoader(data_dir=self.data_dir, limit=self.limit)

    def _limit_rows(
        self,
        rows: Sequence[MiniF2FProblem] | Iterator[MiniF2FProblem],
    ) -> Iterator[MiniF2FProblem]:
        for index, row in enumerate(rows):
            if self.limit is not None and index >= self.limit:
                break
            yield row

    def _sample_from_row(self, row: MiniF2FProblem) -> Sample:
        payload = MiniF2FTaskPayload(
            name=row.name,
            informal_statement=row.informal_statement,
            formal_statement=row.formal_statement,
            header=row.header,
        )
        task = MiniF2FTask(
            task_slug=row.name,
            instance_key="default",
            description=(
                f"{row.informal_statement}\n\n"
                f"Your task: prove the following theorem in Lean 4.\n\n"
                f"{row.header}\n{row.formal_statement}"
            ),
            task_payload=payload,
            worker=resolve_worker(self.worker, row),
            sandbox=resolve_sandbox(self.sandbox, row),
            evaluators=resolve_evaluators(self.evaluators, row),
        )
        return Sample.from_tasks(
            name=f"{self.name}:{row.name}",
            sample_key=row.name,
            environment_name=self.name,
            sample_ref={"problem_id": row.name, "split": self.split},
            source_metadata={"provider": "ergon-builtin:minif2f", "split": self.split},
            tasks=[cast(Task, task)],
        )
