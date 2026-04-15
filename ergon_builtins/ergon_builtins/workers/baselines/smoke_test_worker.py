"""Smoke-test worker: writes a marker file to the E2B sandbox.

Used for CI / E2E integration tests. Proves the worker -> sandbox -> evaluator
round-trip works by writing a known file that the SandboxFileCheckCriterion
can later verify.
"""

from collections.abc import AsyncGenerator

from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn, TextPart

MARKER_PATH = "/outputs/ci_marker.txt"
MARKER_CONTENT = "smoke-test-marker"


class SmokeTestWorker(Worker):
    type_slug = "smoke-test-worker"

    def __init__(self, *, name: str = "smoke-test", model: str | None = None) -> None:
        super().__init__(name=name, model=model)

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        try:
            # Deferred: optional dependency
            from e2b_code_interpreter import AsyncSandbox
        except ImportError:
            yield GenerationTurn(
                response_parts=[
                    TextPart(content=f"e2b not available — stub output for {task.task_key}")
                ],
            )
            return

        sandbox = await AsyncSandbox.connect(
            sandbox_id=context.sandbox_id,
        )
        await sandbox.files.write(MARKER_PATH, MARKER_CONTENT)

        yield GenerationTurn(
            response_parts=[
                TextPart(content=f"Wrote {MARKER_PATH} to sandbox {context.sandbox_id}")
            ],
        )
