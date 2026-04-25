"""SWE-Bench Verified benchmark loader.

Pulls the ``princeton-nlp/SWE-bench_Verified`` HuggingFace dataset and yields
one ``BenchmarkTask`` per instance. The worker only sees the problem
statement; the evaluator receives ``test_patch`` via the task payload.
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from datasets import load_dataset

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.benchmark_deps import BenchmarkDeps
from ergon_core.api.task_types import BenchmarkTask

from ergon_builtins.benchmarks.swebench_verified.task_schemas import (
    SWEBenchInstance,
    SWEBenchTaskPayload,
)

logger = logging.getLogger(__name__)

HF_DATASET_ID = "princeton-nlp/SWE-bench_Verified"
HF_SPLIT = "test"


class SweBenchVerifiedBenchmark(Benchmark):
    """Benchmark backed by SWE-Bench Verified (500 curated instances)."""

    type_slug: ClassVar[str] = "swebench-verified"
    task_payload_model: ClassVar[type[SWEBenchTaskPayload]] = SWEBenchTaskPayload
    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(
        e2b=True,
        extras=("ergon-builtins[data]",),
    )

    def __init__(
        self,
        *,
        limit: int | None = None,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            name=name or "swebench-verified",
            description=description or "SWE-Bench Verified GitHub issue-fix benchmark",
            metadata=metadata,
        )
        self.limit = limit

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask[SWEBenchTaskPayload]]]:
        rows = _load_rows(limit=self.limit)
        tasks: list[BenchmarkTask[SWEBenchTaskPayload]] = []
        for row in rows:
            instance = SWEBenchInstance.from_raw(row)
            payload = SWEBenchTaskPayload.from_instance(instance)
            tasks.append(
                BenchmarkTask[SWEBenchTaskPayload](
                    task_slug=instance.instance_id,
                    instance_key="default",
                    description=payload.build_worker_description(),
                    evaluator_binding_keys=("default",),
                    task_payload=payload,
                )
            )
        logger.info("Loaded %d SWE-Bench Verified instances", len(tasks))
        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ("default",)


def _load_rows(
    *, limit: int | None = None
) -> list[dict[str, Any]]:  # slopcop: ignore[no-typing-any]
    """Load rows from the HF dataset. Isolated for testability."""
    ds = load_dataset(HF_DATASET_ID, split=HF_SPLIT)
    if limit is not None:
        ds = ds.select(range(min(limit, len(ds))))
    return [dict(row) for row in ds]
