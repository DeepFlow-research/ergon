"""SWE-Bench Verified benchmark loader.

Pulls the ``princeton-nlp/SWE-bench_Verified`` HuggingFace dataset and yields
one ``BenchmarkTask`` per instance. The worker only sees the problem
statement; the evaluator receives ``test_patch`` via the task payload.
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from datasets import load_dataset
from ergon_core.api import Evaluator, Sandbox, Task, Worker
from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements

from ergon_builtins.benchmarks.swebench_verified.rubric import SWEBenchRubric
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import SWEBenchSandbox
from ergon_builtins.benchmarks.swebench_verified.task_schemas import (
    SWEBenchInstance,
    SWEBenchTaskPayload,
)
from ergon_builtins.benchmarks.swebench_verified.worker_factory import make_swebench_react_worker

logger = logging.getLogger(__name__)

HF_DATASET_ID = "princeton-nlp/SWE-bench_Verified"
HF_SPLIT = "test"


class SweBenchVerifiedBenchmark(Benchmark):
    """Benchmark backed by SWE-Bench Verified (500 curated instances)."""

    type_slug: ClassVar[str] = "swebench-verified"
    task_payload_model: ClassVar[type[SWEBenchTaskPayload]] = SWEBenchTaskPayload
    onboarding_deps: ClassVar[BenchmarkRequirements] = BenchmarkRequirements(
        e2b=True,
        extras=("ergon-builtins[data]",),
    )

    limit: int | None = None
    worker: Worker
    sandbox: Sandbox
    evaluators: tuple[Evaluator, ...]

    def __init__(
        self,
        *,
        limit: int | None = None,
        worker: Worker | None = None,
        sandbox: Sandbox | None = None,
        evaluators: tuple[Evaluator, ...] | None = None,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            name=name or "swebench-verified",
            description=description or "SWE-Bench Verified GitHub issue-fix benchmark",
            metadata=dict(metadata or {}),
            limit=limit,
            worker=worker or make_swebench_react_worker(name="default", model=None),
            sandbox=sandbox or SWEBenchSandbox(),
            evaluators=evaluators or (SWEBenchRubric(name="default"),),
        )

    def build_instances(self) -> Mapping[str, Sequence[Task[SWEBenchTaskPayload]]]:
        instances = _load_rows(limit=self.limit)
        tasks: list[Task[SWEBenchTaskPayload]] = []
        for instance in instances:
            payload = SWEBenchTaskPayload.from_instance(instance)
            tasks.append(
                Task[SWEBenchTaskPayload](
                    task_slug=instance.instance_id,
                    instance_key="default",
                    description=payload.build_worker_description(),
                    worker=self.worker.model_copy(deep=True),
                    sandbox=self.sandbox.model_copy(deep=True),
                    evaluators=tuple(e.model_copy(deep=True) for e in self.evaluators),
                    task_payload=payload,
                )
            )
        logger.info("Loaded %d SWE-Bench Verified instances", len(tasks))
        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ("default",)


def _load_rows(*, limit: int | None = None) -> list[SWEBenchInstance]:
    """Load and validate SWE-Bench instances from HuggingFace."""
    ds = load_dataset(HF_DATASET_ID, split=HF_SPLIT)
    if limit is not None:
        ds = ds.select(range(min(limit, len(ds))))
    return [SWEBenchInstance.from_raw(row) for row in ds]
