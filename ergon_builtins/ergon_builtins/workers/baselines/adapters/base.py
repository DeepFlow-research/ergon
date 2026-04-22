"""Abstract adapter interface for per-benchmark ReAct wiring.

The unified :class:`ReActWorker` delegates benchmark-specific concerns to
a :class:`BenchmarkAdapter`:

* building the tool list (``build_tools``),
* optional setup before the ReAct loop (``on_run_start``),
* optional teardown / artifact capture after the loop (``on_run_end``),
* routing captured artifacts back into :class:`WorkerOutput`
  (``transform_output``).

Adapters own the system prompt and the default ``max_iterations`` for
the benchmarks they model; the worker honors them unless the caller
passes explicit overrides.
"""

from abc import ABC, abstractmethod
from typing import Any

from ergon_core.api import BenchmarkTask, WorkerContext, WorkerOutput


class BenchmarkAdapter(ABC):
    """Per-benchmark plumbing plugged into :class:`ReActWorker`.

    Concrete adapters override :meth:`build_tools` and typically set
    ``system_prompt`` / ``max_iterations`` at class level. The other
    hooks are optional no-ops by default.
    """

    # Class-level defaults — override in subclasses.
    system_prompt: str | None = None
    max_iterations: int = 10

    @abstractmethod
    async def build_tools(
        self,
        task: BenchmarkTask,
        context: WorkerContext,
    ) -> list[Any]:  # slopcop: ignore[no-typing-any]
        """Return the list of pydantic-ai tools the ReAct agent will use.

        Called once per ``execute`` after :meth:`on_run_start`. The adapter
        is responsible for opening whatever handles (sandbox, clients) the
        toolkit needs.
        """

    async def on_run_start(
        self,
        task: BenchmarkTask,
        context: WorkerContext,
    ) -> None:
        """Optional hook before the ReAct loop begins. Default: no-op.

        Use for per-task setup that cannot be expressed as a tool — e.g.
        running benchmark-specific environment bootstrap scripts.
        """
        return None

    async def on_run_end(
        self,
        task: BenchmarkTask,
        context: WorkerContext,
    ) -> None:
        """Optional hook after the ReAct loop ends. Runs in ``finally``.

        Use for capturing artifacts produced inside the sandbox (final
        files, diffs, logs). Runs even if the loop raises or is cancelled,
        so implementations should tolerate partial state.
        """
        return None

    def transform_output(
        self,
        context: WorkerContext,
        base: WorkerOutput,
    ) -> WorkerOutput:
        """Optionally rewrite the final :class:`WorkerOutput`. Default: passthrough.

        Used when a benchmark needs the captured artifact routed through
        the ``output`` field (the runtime's evaluator dispatch drops
        ``artifacts`` in some paths, so benchmarks that score on an
        artifact ship it as the output text too).
        """
        return base
