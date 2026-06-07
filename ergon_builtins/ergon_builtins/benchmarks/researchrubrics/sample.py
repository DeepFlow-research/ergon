"""ResearchRubrics sample construction helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from ergon_core.api import Sample, Task
from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker

from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.task import (
    RESEARCH_RUBRICS_DATASET,
    ResearchRubricsTask,
    _payload_from_row,
)
from ergon_builtins.benchmarks.researchrubrics.task_schemas import ResearchRubricsTaskPayload


def make_researchrubrics_sample(
    row: ResearchRubricsTaskPayload | Mapping[str, Any],
    *,
    environment_name: str,
    worker: Worker,
    evaluators: Sequence[Evaluator],
    sandbox: Sandbox,
    split: str = "train",
    dataset_name: str = RESEARCH_RUBRICS_DATASET,
) -> Sample:
    payload = row if isinstance(row, ResearchRubricsTaskPayload) else _payload_from_row(row)
    bound_evaluators = tuple(_bind_payload_rubric(evaluator, payload) for evaluator in evaluators)
    task = ResearchRubricsTask(
        task_slug=payload.sample_id,
        instance_key="default",
        description=payload.prompt,
        task_payload=payload,
        worker=worker,
        sandbox=sandbox,
        evaluators=bound_evaluators,
    )
    return Sample.from_tasks(
        name=f"{environment_name}:{payload.sample_id}",
        sample_key=payload.sample_id,
        environment_name=environment_name,
        sample_ref={
            "sample_id": payload.sample_id,
            "domain": payload.domain,
            "split": split,
        },
        source_metadata={
            "provider": "ergon-builtin:researchrubrics",
            "dataset_name": dataset_name,
            "split": split,
        },
        tasks=[cast(Task, task)],
    )


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
