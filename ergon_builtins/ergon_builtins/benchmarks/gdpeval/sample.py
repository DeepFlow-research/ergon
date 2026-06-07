"""GDPEval sample construction helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import cast

from ergon_core.api import Sample, Task
from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker

from ergon_builtins.benchmarks.gdpeval.loader import HF_REPO_ID, extract_task_description
from ergon_builtins.benchmarks.gdpeval.task import GDPEvalTask
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig


def make_gdpeval_sample(
    row: GDPTaskConfig,
    *,
    environment_name: str,
    worker: Worker,
    evaluators: Sequence[Evaluator],
    sandbox: Sandbox,
    split: str = "train",
    dataset_repo: str = HF_REPO_ID,
    task_description: Callable[[GDPTaskConfig], str] | None = None,
) -> Sample:
    description = (
        task_description(row)
        if task_description is not None
        else extract_task_description(row.task_id, repo_id=dataset_repo)
    )
    task = GDPEvalTask(
        task_slug=row.task_id,
        instance_key="default",
        description=description,
        task_payload=row,
        worker=worker,
        sandbox=sandbox,
        evaluators=tuple(evaluators),
    )
    return Sample.from_tasks(
        name=f"{environment_name}:{row.task_id}",
        sample_key=row.task_id,
        environment_name=environment_name,
        sample_ref={"task_id": row.task_id, "split": split},
        source_metadata={
            "provider": "ergon-builtin:gdpeval",
            "dataset_repo": dataset_repo,
            "split": split,
        },
        tasks=[cast(Task, task)],
    )
