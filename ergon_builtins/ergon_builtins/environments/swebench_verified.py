"""SWE-Bench Verified sample-producing environment."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from datasets import load_dataset
from ergon_core.api import Environment, Sample, Task
from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker
from pydantic import Field, model_validator

from ergon_builtins.benchmarks.swebench_verified.benchmark import (
    HF_DATASET_ID,
    HF_SPLIT,
    SweBenchTask,
    _default_swebench_sandbox,
)
from ergon_builtins.benchmarks.swebench_verified.task_schemas import (
    SWEBenchInstance,
    SWEBenchTaskPayload,
)
from ergon_builtins.benchmarks.swebench_verified.worker_factory import (
    make_swebench_rubric,
    make_swebench_worker,
)
from ergon_builtins.environments._resolve import (
    resolve_evaluators,
    resolve_sandbox,
    resolve_worker,
)


class SweBenchVerifiedRowLoader(Protocol):
    def iter_rows(self) -> Iterator[SWEBenchInstance]: ...

    def load_rows(self) -> Sequence[SWEBenchInstance]: ...


@dataclass(frozen=True)
class DefaultSweBenchVerifiedRowLoader:
    dataset_id: str = HF_DATASET_ID
    split: str = HF_SPLIT
    limit: int | None = None
    streaming: bool = False

    def iter_rows(self) -> Iterator[SWEBenchInstance]:
        ds = load_dataset(self.dataset_id, split=self.split, streaming=self.streaming)
        for index, row in enumerate(ds):
            if self.limit is not None and index >= self.limit:
                break
            yield SWEBenchInstance.from_raw(row)

    def load_rows(self) -> Sequence[SWEBenchInstance]:
        ds = load_dataset(self.dataset_id, split=self.split)
        if self.limit is not None:
            ds = ds.select(range(min(self.limit, len(ds))))
        return [SWEBenchInstance.from_raw(row) for row in ds]


class SweBenchVerifiedEnvironment(Environment):
    name: str = "swebench-verified"
    split: str = HF_SPLIT
    dataset_id: str = HF_DATASET_ID
    limit: int | None = None
    source_mode: Literal["materialized", "streaming"] = "materialized"
    streaming: bool = False
    loader: Any | None = None
    worker: Worker | Callable[[SWEBenchInstance], Worker] = Field(
        default_factory=make_swebench_worker
    )
    evaluators: Sequence[Evaluator] | Callable[[SWEBenchInstance], Sequence[Evaluator]] = Field(
        default_factory=lambda: (make_swebench_rubric(),)
    )
    sandbox: Sandbox | Callable[[SWEBenchInstance], Sandbox] = Field(
        default_factory=_default_swebench_sandbox
    )

    @model_validator(mode="after")
    def _sync_streaming_flag(self) -> "SweBenchVerifiedEnvironment":
        if self.streaming:
            self.source_mode = "streaming"
        elif self.source_mode == "streaming":
            self.streaming = True
        return self

    def iter_samples(self) -> Iterator[Sample]:
        for row in self._limit_rows(self._loader().iter_rows()):
            yield self._sample_from_row(row)

    def all_samples(self) -> Sequence[Sample]:
        if self.source_mode == "streaming":
            raise NotImplementedError("Streaming environments may not materialize all samples")
        return [self._sample_from_row(row) for row in self._limit_rows(self._loader().load_rows())]

    def _loader(self) -> SweBenchVerifiedRowLoader:
        return self.loader or DefaultSweBenchVerifiedRowLoader(
            dataset_id=self.dataset_id,
            split=self.split,
            limit=self.limit,
            streaming=self.source_mode == "streaming",
        )

    def _limit_rows(
        self,
        rows: Sequence[SWEBenchInstance] | Iterator[SWEBenchInstance],
    ) -> Iterator[SWEBenchInstance]:
        for index, row in enumerate(rows):
            if self.limit is not None and index >= self.limit:
                break
            yield row

    def _sample_from_row(self, row: SWEBenchInstance) -> Sample:
        payload = SWEBenchTaskPayload.from_instance(row)
        task = SweBenchTask(
            task_slug=row.instance_id,
            instance_key="default",
            description=payload.build_worker_description(),
            task_payload=payload,
            worker=resolve_worker(self.worker, row),
            sandbox=resolve_sandbox(self.sandbox, row),
            evaluators=resolve_evaluators(self.evaluators, row),
        )
        return Sample.from_tasks(
            name=f"{self.name}:{row.instance_id}",
            sample_key=row.instance_id,
            environment_name=self.name,
            sample_ref={
                "instance_id": row.instance_id,
                "repo": row.repo,
                "base_commit": row.base_commit,
                "split": self.split,
            },
            source_metadata={
                "provider": "ergon-builtin:swebench-verified",
                "dataset_id": self.dataset_id,
                "split": self.split,
            },
            tasks=[cast(Task, task)],
        )
