"""Shared glue between any SmokeSubworker and the Ergon Worker ABC.

Subclasses set ``type_slug`` and ``subworker_cls``. The base class handles
sandbox attach, delegation to the subworker, and reporting success/failure via
``get_output``. Output files land under ``/workspace/final_output/`` where the
runtime's persist_outputs step creates RunResource rows for them.
"""

from collections.abc import AsyncGenerator
from typing import ClassVar

from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]
from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn, TextPart
from ergon_core.api.results import WorkerOutput

from ergon_builtins.workers.stubs.smoke_subworker import (
    SmokeSubworker,
    SubworkerResult,
)


class BaseSmokeLeafWorker(Worker):
    """Abstract base. Subclasses set `subworker_cls: type[SmokeSubworker]`."""

    subworker_cls: ClassVar[type[SmokeSubworker]]

    def __init__(self, *, name: str, model: str | None) -> None:
        super().__init__(name=name, model=model)
        self._last_result: SubworkerResult | None = None

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        sandbox = await AsyncSandbox.connect(sandbox_id=context.sandbox_id)
        node_hex = context.node_id.hex[:8] if context.node_id else "unknown"
        subworker = self.subworker_cls()
        result = await subworker.work(node_id=node_hex, sandbox=sandbox)
        self._last_result = result

        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        f"smoke-leaf node={node_hex} "
                        f"file={result.file_path} "
                        f"probe_exit={result.probe_exit_code}"
                    ),
                ),
            ],
        )

    def get_output(self, context: WorkerContext) -> WorkerOutput:
        r = self._last_result
        if r is None:
            return WorkerOutput(output="", success=False, metadata={"error": "no_result"})
        return WorkerOutput(
            output=r.probe_stdout,
            success=r.probe_exit_code == 0,
            metadata={
                "probe_exit_code": r.probe_exit_code,
                "file_path": r.file_path,
            },
        )
