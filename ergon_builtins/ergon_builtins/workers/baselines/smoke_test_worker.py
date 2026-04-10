"""Smoke-test worker: writes a marker file to the E2B sandbox.

Used for CI / E2E integration tests. Proves the worker -> sandbox -> evaluator
round-trip works by writing a known file that the SandboxFileCheckCriterion
can later verify.
"""

from ergon_core.api import BenchmarkTask, Worker, WorkerContext, WorkerResult

MARKER_PATH = "/outputs/ci_marker.txt"
MARKER_CONTENT = "smoke-test-marker"


class SmokeTestWorker(Worker):
    type_slug = "smoke-test-worker"

    def __init__(self, *, name: str = "smoke-test", model: str | None = None) -> None:
        self.name = name
        self.model = model

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> WorkerResult:
        try:
            # Deferred: optional dependency
            from e2b_code_interpreter import AsyncSandbox
        except ImportError:
            return WorkerResult(
                output=f"e2b not available — stub output for {task.task_key}",
                success=True,
                metadata={"task_key": task.task_key, "sandbox_write": False},
            )

        sandbox = await AsyncSandbox.connect(
            sandbox_id=context.sandbox_id,
        )
        await sandbox.files.write(MARKER_PATH, MARKER_CONTENT)

        return WorkerResult(
            output=f"Wrote {MARKER_PATH} to sandbox {context.sandbox_id}",
            success=True,
            metadata={
                "task_key": task.task_key,
                "sandbox_id": context.sandbox_id,
                "marker_path": MARKER_PATH,
                "sandbox_write": True,
            },
        )
