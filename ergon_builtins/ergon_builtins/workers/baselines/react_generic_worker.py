"""Generic ReAct worker that composes its toolkit per benchmark from metadata.

Reads `ctx.metadata["toolkit_benchmark"]` at execute() time, opens the
sandbox, calls `compose_benchmark_toolkit(...)`, stashes the result on
`self.tools`, and delegates to `super().execute()`.

Intended for the real-LLM debug harness; validates that `ReActWorker` +
the three composed toolkits behave correctly end-to-end against a real
model, without us having to maintain per-benchmark specialised workers.
"""

from collections.abc import AsyncGenerator

from e2b_code_interpreter import AsyncSandbox

from ergon_core.api import BenchmarkTask, WorkerContext
from ergon_core.api.generation import GenerationTurn

from ergon_builtins.tools.benchmark_toolkit_composer import compose_benchmark_toolkit
from ergon_builtins.workers.baselines.react_worker import ReActWorker


class ReActGenericWorker(ReActWorker):
    """ReAct worker that composes its toolkit from ctx.metadata['toolkit_benchmark'].

    Delegates all tool-augmented generation to the base ReActWorker after
    wiring up the benchmark-specific tools at execute() time.
    """

    type_slug = "react-generic"

    def _benchmark_slug(self, ctx: WorkerContext) -> str:
        slug = ctx.metadata.get("toolkit_benchmark") if ctx.metadata else None
        if not isinstance(slug, str) or not slug:
            raise ValueError("ReActGenericWorker requires ctx.metadata['toolkit_benchmark']")
        return slug

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        slug = self._benchmark_slug(context)
        sandbox = await AsyncSandbox.connect(context.sandbox_id)

        # For researchrubrics we'd also need run_skill + publisher_sync; leave
        # None-default and let the composer raise if that branch is hit without
        # them being wired at a higher layer. PR 2 adds the wiring.
        self.tools = compose_benchmark_toolkit(
            benchmark_slug=slug,
            ctx=context,
            sandbox=sandbox,
        )

        async for turn in super().execute(task, context=context):
            yield turn
