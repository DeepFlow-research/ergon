"""GDPEval sample-producing environment."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from ergon_core.api import Environment, Sample, Task
from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker
from pydantic import Field

from ergon_builtins.benchmarks.gdpeval.benchmark import (
    GDPEvalTask,
    _default_gdpeval_sandbox,
)
from ergon_builtins.benchmarks.gdpeval.loader import (
    HF_REPO_ID,
    extract_task_description,
    find_reference_files,
    load_task_ids,
)
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig
from ergon_builtins.benchmarks.gdpeval.worker_factory import (
    make_gdpeval_rubric,
    make_gdpeval_worker,
)
from ergon_builtins.environments._resolve import (
    resolve_evaluators,
    resolve_sandbox,
    resolve_worker,
)


class GDPEvalRowLoader(Protocol):
    def iter_rows(self) -> Iterator[GDPTaskConfig]: ...

    def load_rows(self) -> Sequence[GDPTaskConfig]: ...


@dataclass(frozen=True)
class DefaultGDPEvalRowLoader:
    dataset_repo: str = HF_REPO_ID
    split: str = "train"
    limit: int | None = None

    def iter_rows(self) -> Iterator[GDPTaskConfig]:
        yield from self.load_rows()

    def load_rows(self) -> Sequence[GDPTaskConfig]:
        configs: list[GDPTaskConfig] = []
        for task_id in load_task_ids(split=self.split, repo_id=self.dataset_repo, limit=self.limit):
            ref_files = find_reference_files(task_id, repo_id=self.dataset_repo)
            configs.append(
                GDPTaskConfig(
                    task_id=task_id,
                    workflow_type="document_processing",
                    reference_files=[str(path) for path in ref_files],
                )
            )
        return configs


class GDPEvalEnvironment(Environment):
    name: str = "gdpeval"
    dataset_repo: str = HF_REPO_ID
    split: str = "train"
    limit: int | None = None
    source_mode: Literal["materialized"] = "materialized"
    loader: Any | None = None
    task_description: Callable[[GDPTaskConfig], str] | None = None
    worker: Worker | Callable[[GDPTaskConfig], Worker] = Field(default_factory=make_gdpeval_worker)
    evaluators: Sequence[Evaluator] | Callable[[GDPTaskConfig], Sequence[Evaluator]] = Field(
        default_factory=lambda: (make_gdpeval_rubric(),)
    )
    sandbox: Sandbox | Callable[[GDPTaskConfig], Sandbox] = Field(
        default_factory=_default_gdpeval_sandbox
    )

    def iter_samples(self) -> Iterator[Sample]:
        for row in self._limit_rows(self._loader().iter_rows()):
            yield self._sample_from_row(row)

    def all_samples(self) -> Sequence[Sample]:
        if self.source_mode == "streaming":
            raise NotImplementedError("Streaming environments may not materialize all samples")
        return [self._sample_from_row(row) for row in self._limit_rows(self._loader().load_rows())]

    def _loader(self) -> GDPEvalRowLoader:
        return self.loader or DefaultGDPEvalRowLoader(
            dataset_repo=self.dataset_repo,
            split=self.split,
            limit=self.limit,
        )

    def _limit_rows(
        self,
        rows: Sequence[GDPTaskConfig] | Iterator[GDPTaskConfig],
    ) -> Iterator[GDPTaskConfig]:
        for index, row in enumerate(rows):
            if self.limit is not None and index >= self.limit:
                break
            yield row

    def _sample_from_row(self, row: GDPTaskConfig) -> Sample:
        task = GDPEvalTask(
            task_slug=row.task_id,
            instance_key="default",
            description=self._description_for(row),
            task_payload=row,
            worker=resolve_worker(self.worker, row),
            sandbox=resolve_sandbox(self.sandbox, row),
            evaluators=resolve_evaluators(self.evaluators, row),
        )
        return Sample.from_tasks(
            name=f"{self.name}:{row.task_id}",
            sample_key=row.task_id,
            environment_name=self.name,
            sample_ref={"task_id": row.task_id, "split": self.split},
            source_metadata={
                "provider": "ergon-builtin:gdpeval",
                "dataset_repo": self.dataset_repo,
                "split": self.split,
            },
            tasks=[cast(Task, task)],
        )

    def _description_for(self, row: GDPTaskConfig) -> str:
        if self.task_description is not None:
            return self.task_description(row)
        return extract_task_description(row.task_id, repo_id=self.dataset_repo)
