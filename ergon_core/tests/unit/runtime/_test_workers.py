"""Minimal EchoWorker and EchoSandbox for unit tests.

Reused across PR 5+ unit tests that need a concrete Worker/Sandbox pair
without pulling in any real builtins or external SDK dependencies.
"""

from typing import AsyncGenerator, ClassVar

from ergon_core.api.sandbox.sandbox import Sandbox
from ergon_core.api.worker.worker import Worker, WorkerStreamItem
from ergon_core.api.worker.context import WorkerContext
from ergon_core.api.worker.results import WorkerOutput
from ergon_core.api.benchmark.task import Task


class EchoSandbox(Sandbox):
    """No-op sandbox: provision and bind are instant no-ops."""

    async def provision(self) -> None:
        pass

    async def _bind_runtime(self, sandbox_id: str) -> None:
        pass


class EchoWorker(Worker):
    """Yields a single WorkerOutput with ``final_text='ok'``."""

    type_slug: ClassVar[str] = "echo"
    requires_sandbox: ClassVar[type[Sandbox]] = Sandbox

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(final_text="ok")
