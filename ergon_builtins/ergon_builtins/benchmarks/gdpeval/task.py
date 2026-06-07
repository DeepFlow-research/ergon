"""GDPEval concrete task type."""

from ergon_core.api import Task

from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig


class GDPEvalTask(Task[GDPTaskConfig]):
    """Concrete Task subclass for GDPEval instances.

    Named so ``Task.from_definition`` can resolve the ``_type``
    discriminator as a plain module attribute.  The parameterized
    generic ``Task[GDPTaskConfig]`` cannot be looked up that way —
    its ``__qualname__`` includes ``[...]``.
    """


__all__ = ["GDPEvalTask"]
