"""SWE-Bench Verified concrete task type and dataset constants."""

from ergon_core.api import Task

from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchTaskPayload

HF_DATASET_ID = "princeton-nlp/SWE-bench_Verified"
HF_SPLIT = "test"


class SweBenchTask(Task[SWEBenchTaskPayload]):
    """Concrete Task subclass for SWE-Bench Verified instances.

    Named so ``Task.from_definition`` can resolve the ``_type``
    discriminator as a plain module attribute.  The parameterized
    generic ``Task[SWEBenchTaskPayload]`` cannot be looked up that
    way — its ``__qualname__`` includes ``[...]``.
    """


__all__ = ["HF_DATASET_ID", "HF_SPLIT", "SweBenchTask"]
