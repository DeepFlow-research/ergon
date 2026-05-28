"""MiniF2F sample construction helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from ergon_core.api import Sample, Task
from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker

from ergon_builtins.benchmarks.minif2f.task import MiniF2FTask
from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem, MiniF2FTaskPayload


def make_minif2f_sample(
    row: MiniF2FProblem,
    *,
    environment_name: str,
    worker: Worker,
    evaluators: Sequence[Evaluator],
    sandbox: Sandbox,
    split: str = "validation",
) -> Sample:
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
        worker=worker,
        sandbox=sandbox,
        evaluators=tuple(evaluators),
    )
    return Sample.from_tasks(
        name=f"{environment_name}:{row.name}",
        sample_key=row.name,
        environment_name=environment_name,
        sample_ref={"problem_id": row.name, "split": split},
        source_metadata={"provider": "ergon-builtin:minif2f", "split": split},
        tasks=[cast(Task, task)],
    )
