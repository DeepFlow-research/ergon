"""ResearchRubrics sample-producing environment."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from datasets import load_dataset
from ergon_core.api import Environment, Sample, Task
from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker
from ergon_core.core.shared.settings import settings
from pydantic import Field

from ergon_builtins.benchmarks.researchrubrics.benchmark import (
    ResearchRubricsBenchmark,
    ResearchRubricsTask,
    _default_research_sandbox,
    _payload_from_row,
)
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.task_schemas import ResearchRubricsTaskPayload
from ergon_builtins.benchmarks.researchrubrics.worker_factory import (
    make_research_rubric,
    make_research_worker,
)
from ergon_builtins.environments._resolve import (
    resolve_evaluators,
    resolve_sandbox,
    resolve_worker,
)


class ResearchRubricsRowLoader(Protocol):
    def iter_rows(self) -> Iterator[ResearchRubricsTaskPayload]: ...

    def load_rows(self) -> Sequence[ResearchRubricsTaskPayload]: ...


@dataclass(frozen=True)
class DefaultResearchRubricsRowLoader:
    dataset_name: str = ResearchRubricsBenchmark.dataset_name
    split: str = "train"
    limit: int | None = None

    def iter_rows(self) -> Iterator[ResearchRubricsTaskPayload]:
        yield from self.load_rows()

    def load_rows(self) -> Sequence[ResearchRubricsTaskPayload]:
        ds = load_dataset(self.dataset_name, token=settings.hf_api_key)
        split_ds = ds[self.split]
        if self.limit is not None:
            split_ds = split_ds.select(range(min(self.limit, len(split_ds))))
        return [_payload_from_row(split_ds[idx]) for idx in range(len(split_ds))]


class ResearchRubricsEnvironment(Environment):
    name: str = "researchrubrics"
    dataset_name: str = ResearchRubricsBenchmark.dataset_name
    split: str = "train"
    limit: int | None = None
    source_mode: Literal["materialized"] = "materialized"
    loader: Any | None = None
    worker: Worker | Callable[[ResearchRubricsTaskPayload], Worker] = Field(
        default_factory=make_research_worker
    )
    evaluators: (
        Sequence[Evaluator] | Callable[[ResearchRubricsTaskPayload], Sequence[Evaluator]]
    ) = Field(default_factory=lambda: (make_research_rubric(),))
    sandbox: Sandbox | Callable[[ResearchRubricsTaskPayload], Sandbox] = Field(
        default_factory=_default_research_sandbox
    )

    def iter_samples(self) -> Iterator[Sample]:
        for row in self._limit_rows(self._loader().iter_rows()):
            yield self._sample_from_row(row)

    def all_samples(self) -> Sequence[Sample]:
        if self.source_mode == "streaming":
            raise NotImplementedError("Streaming environments may not materialize all samples")
        return [self._sample_from_row(row) for row in self._limit_rows(self._loader().load_rows())]

    def _loader(self) -> ResearchRubricsRowLoader:
        return self.loader or DefaultResearchRubricsRowLoader(
            dataset_name=self.dataset_name,
            split=self.split,
            limit=self.limit,
        )

    def _limit_rows(
        self,
        rows: Sequence[ResearchRubricsTaskPayload] | Iterator[ResearchRubricsTaskPayload],
    ) -> Iterator[ResearchRubricsTaskPayload]:
        for index, row in enumerate(rows):
            if self.limit is not None and index >= self.limit:
                break
            yield row

    def _sample_from_row(self, row: ResearchRubricsTaskPayload | Mapping[str, Any]) -> Sample:
        payload = row if isinstance(row, ResearchRubricsTaskPayload) else _payload_from_row(row)
        evaluators = resolve_evaluators(self.evaluators, payload)
        evaluators = tuple(
            self._bind_payload_rubric(evaluator, payload) for evaluator in evaluators
        )
        task = ResearchRubricsTask(
            task_slug=payload.sample_id,
            instance_key="default",
            description=payload.prompt,
            task_payload=payload,
            worker=resolve_worker(self.worker, payload),
            sandbox=resolve_sandbox(self.sandbox, payload),
            evaluators=evaluators,
        )
        return Sample.from_tasks(
            name=f"{self.name}:{payload.sample_id}",
            sample_key=payload.sample_id,
            environment_name=self.name,
            sample_ref={
                "sample_id": payload.sample_id,
                "domain": payload.domain,
                "split": self.split,
            },
            source_metadata={
                "provider": "ergon-builtin:researchrubrics",
                "dataset_name": self.dataset_name,
                "split": self.split,
            },
            tasks=[cast(Task, task)],
        )

    @staticmethod
    def _bind_payload_rubric(
        evaluator: Evaluator,
        payload: ResearchRubricsTaskPayload,
    ) -> Evaluator:
        if isinstance(evaluator, ResearchRubricsRubric) and not evaluator.rubric_criteria:
            return ResearchRubricsRubric(
                name=evaluator.name,
                metadata=evaluator.metadata,
                rubric_criteria=tuple(payload.rubrics),
            )
        return evaluator
