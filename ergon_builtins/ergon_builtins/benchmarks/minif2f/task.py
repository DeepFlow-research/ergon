"""MiniF2F concrete task type and dataset constants."""

from ergon_core.api import Task

from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem, MiniF2FTaskPayload

HF_REPO_ID = "roozbeh-yz/miniF2F_v2"
HF_FILENAME = "miniF2F_v2c.jsonl"


class MiniF2FTask(Task[MiniF2FTaskPayload]):
    """Concrete Task subclass for MiniF2F instances.

    Named so ``Task.from_definition`` can resolve the ``_type``
    discriminator as a plain module attribute. The parameterized
    generic ``Task[MiniF2FTaskPayload]`` cannot be looked up that way.
    """


__all__ = ["HF_FILENAME", "HF_REPO_ID", "MiniF2FProblem", "MiniF2FTask", "MiniF2FTaskPayload"]
