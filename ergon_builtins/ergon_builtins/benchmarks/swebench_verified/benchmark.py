"""SWE-Bench Verified benchmark loader.

Pulls the ``princeton-nlp/SWE-bench_Verified`` HuggingFace dataset and yields
one ``Task`` per instance. The worker only sees the problem statement; the
evaluator receives ``test_patch`` via the task payload.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar

from datasets import load_dataset
from ergon_core.api import Benchmark, BenchmarkRequirements, Task
from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker

from ergon_builtins.benchmarks.swebench_verified.sandbox import SWEBenchSandbox
from ergon_builtins.benchmarks.swebench_verified.task_schemas import (
    SWEBenchInstance,
    SWEBenchTaskPayload,
)
from ergon_builtins.benchmarks.swebench_verified.workers import (
    make_swebench_rubric,
    make_swebench_worker,
)

logger = logging.getLogger(__name__)

HF_DATASET_ID = "princeton-nlp/SWE-bench_Verified"
HF_SPLIT = "test"


def _default_swebench_sandbox() -> Sandbox:
    return SWEBenchSandbox()


class SweBenchTask(Task[SWEBenchTaskPayload]):
    """Concrete Task subclass for SWE-Bench Verified instances.

    Named so ``Task.from_definition`` can resolve the ``_type``
    discriminator as a plain module attribute.  The parameterized
    generic ``Task[SWEBenchTaskPayload]`` cannot be looked up that
    way — its ``__qualname__`` includes ``[...]``.
    """


class SweBenchVerifiedBenchmark(Benchmark):
    """Benchmark backed by SWE-Bench Verified (500 curated instances)."""

    type_slug: ClassVar[str] = "swebench-verified"
    task_payload_model: ClassVar[type[SWEBenchTaskPayload]] = SWEBenchTaskPayload
    onboarding_deps: ClassVar[BenchmarkRequirements] = BenchmarkRequirements(
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
        worker_factory: Callable[[], Worker] = make_swebench_worker,
        sandbox_factory: Callable[[], Sandbox] = _default_swebench_sandbox,
        evaluator_factory: Callable[[], Evaluator] = make_swebench_rubric,
    ) -> None:
        super().__init__(
            name=name or "swebench-verified",
            description=description or "SWE-Bench Verified GitHub issue-fix benchmark",
            metadata=metadata,
        )
        self.limit = limit
        self._worker_factory = worker_factory
        self._sandbox_factory = sandbox_factory
        self._evaluator_factory = evaluator_factory

    def build_instances(self) -> Mapping[str, Sequence[Task[SWEBenchTaskPayload]]]:
        instances = _load_rows(limit=self.limit)
        tasks: list[Task[SWEBenchTaskPayload]] = []
        for instance in instances:
            payload = SWEBenchTaskPayload.from_instance(instance)
            tasks.append(
                SweBenchTask(
                    task_slug=instance.instance_id,
                    instance_key="default",
                    description=payload.build_worker_description(),
                    task_payload=payload,
                    worker=self._worker_factory(),
                    sandbox=self._sandbox_factory(),
                    evaluators=(self._evaluator_factory(),),
                )
            )
        logger.info("Loaded %d SWE-Bench Verified instances", len(tasks))
        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ()


def _load_rows(*, limit: int | None = None) -> list[SWEBenchInstance]:
    """Load and validate SWE-Bench instances from HuggingFace."""
    ds = load_dataset(HF_DATASET_ID, split=HF_SPLIT)
    if limit is not None:
        ds = ds.select(range(min(limit, len(ds))))
    return [SWEBenchInstance.from_raw(row) for row in ds]
