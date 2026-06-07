"""SWE-Bench Verified sample construction helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from ergon_core.api import Sample, Task
from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker

from ergon_builtins.benchmarks.swebench_verified.task import HF_DATASET_ID, HF_SPLIT, SweBenchTask
from ergon_builtins.benchmarks.swebench_verified.task_schemas import (
    SWEBenchInstance,
    SWEBenchTaskPayload,
)


def make_swebench_sample(
    row: SWEBenchInstance,
    *,
    environment_name: str,
    worker: Worker,
    evaluators: Sequence[Evaluator],
    sandbox: Sandbox,
    split: str = HF_SPLIT,
    dataset_id: str = HF_DATASET_ID,
) -> Sample:
    payload = SWEBenchTaskPayload.from_instance(row)
    task = SweBenchTask(
        task_slug=row.instance_id,
        instance_key="default",
        description=payload.build_worker_description(),
        task_payload=payload,
        worker=worker,
        sandbox=sandbox,
        evaluators=tuple(evaluators),
    )
    return Sample.from_tasks(
        name=f"{environment_name}:{row.instance_id}",
        sample_key=row.instance_id,
        environment_name=environment_name,
        sample_ref={
            "instance_id": row.instance_id,
            "repo": row.repo,
            "base_commit": row.base_commit,
            "split": split,
        },
        source_metadata={
            "provider": "ergon-builtin:swebench-verified",
            "dataset_id": dataset_id,
            "split": split,
        },
        tasks=[cast(Task, task)],
    )
