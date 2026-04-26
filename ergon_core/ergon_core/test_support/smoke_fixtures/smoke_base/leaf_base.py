"""Abstract smoke leaf worker.

``BaseSmokeLeafWorker`` is the common execution glue between the per-env
``SmokeSubworker`` implementations and the ``Worker`` ABC.  Subclasses
set ``type_slug`` and ``subworker_cls``; everything else is here.

Leaf execution:

  1. Attach to the leaf's sandbox via ``AsyncSandbox.connect``.
  2. Delegate the actual env-specific work to ``subworker_cls().work``.
  3. Post a one-line completion message to the shared
     ``smoke-completion`` thread so the driver can assert on message
     ordering + thread-FK integrity.
  4. Yield 2 ``GenerationTurn`` objects (attach → done).

Sad-path leaves (``AlwaysFailSubworker`` in Phase C) raise inside
``subworker.work()``, so they never reach ``_send_completion_message``
— driver asserts 8 messages on sad runs vs 9 on happy runs.

See docs/superpowers/plans/test-refactor/01-fixtures.md §2.4.
"""

from collections.abc import AsyncGenerator
from typing import ClassVar
from uuid import UUID

from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn, TextPart
from ergon_core.api.results import WorkerOutput
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.providers.sandbox.instrumentation import InstrumentedSandbox
from ergon_core.core.settings import settings
from ergon_core.core.runtime.services.communication_schemas import CreateMessageRequest
from ergon_core.core.runtime.services.communication_service import (
    communication_service,
)

from ergon_core.test_support.smoke_fixtures.smoke_base.subworker import (
    SmokeSubworker,
    SubworkerResult,
)
from ergon_core.test_support.smoke_fixtures.sandbox import SmokeSandboxManager


class BaseSmokeLeafWorker(Worker):
    """Abstract leaf.  Subclasses set ``type_slug`` and ``subworker_cls``."""

    # Subclasses bind a concrete SmokeSubworker implementation here.  The
    # leaf's ``execute`` instantiates ``subworker_cls()`` and delegates.
    subworker_cls: ClassVar[type[SmokeSubworker]]

    # Driver asserts per-leaf GenerationTurn count against this constant.
    # Sad-path leaves that raise inside subworker.work() emit fewer turns
    # (only the first 'attaching' turn) and are skipped from the strict
    # equality check on the sad run.
    LEAF_TURN_COUNT: ClassVar[int] = 2

    def __init__(
        self,
        *,
        name: str,
        model: str | None,
        task_id: UUID,
        sandbox_id: str,
    ) -> None:
        super().__init__(name=name, model=model, task_id=task_id, sandbox_id=sandbox_id)
        self._last_result: SubworkerResult | None = None

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        node_hex = context.node_id.hex[:8] if context.node_id else "unknown"

        # --- Turn 1: attaching + starting ---------------------------------
        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        f"{type(self).__name__}: attaching to sandbox "
                        f"{context.sandbox_id} for node={node_hex}"
                    ),
                ),
            ],
        )

        raw_sandbox = await SmokeSandboxManager().reconnect(context.sandbox_id)
        sandbox = InstrumentedSandbox(
            raw_sandbox,
            SmokeSandboxManager._event_sink,
            context.run_id,
            context.node_id or context.execution_id,
            settings.otel_stdout_stderr_max_length,
        )
        result = await self.subworker_cls().work(node_id=node_hex, sandbox=sandbox)
        self._last_result = result

        # Post a one-line completion message to the shared
        # ``smoke-completion`` thread.  Every happy-path leaf sends exactly
        # one message; sad-path leaves that raise inside ``subworker.work``
        # never reach this call — driver asserts on that shape.
        await self._send_completion_message(context, result)

        # --- Turn 2: done + result summary --------------------------------
        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        f"{type(self).__name__}: done node={node_hex} "
                        f"file={result.file_path} probe_exit={result.probe_exit_code}"
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

    async def _send_completion_message(
        self,
        context: WorkerContext,
        result: SubworkerResult,
    ) -> None:
        """Post one ThreadMessage on the ``smoke-completion`` thread.

        Structure asserted by ``_assert_thread_messages_ordered`` in the
        driver:

        - Thread topic: ``"smoke-completion"``
        - ``from_agent_id``: ``f"leaf-{task_slug}"`` — looked up from
          ``RunGraphNode.task_slug`` by ``context.node_id``
        - ``to_agent_id``: ``"parent"``
        - 9 messages per happy run, sequence_num 1..9 per-thread-monotonic
        - 8 messages per sad run (l_2 suppresses this call; l_3 still runs)
        """
        task_slug = self._lookup_task_slug(context.node_id)
        await communication_service.save_message(
            CreateMessageRequest(
                run_id=context.run_id,
                task_execution_id=context.execution_id,
                from_agent_id=f"leaf-{task_slug}",
                to_agent_id="parent",
                thread_topic="smoke-completion",
                content=(
                    f"{task_slug}: done exit={result.probe_exit_code} file={result.file_path}"
                ),
            ),
        )

    @staticmethod
    def _lookup_task_slug(node_id: UUID | None) -> str:
        """Resolve the leaf's ``task_slug`` from its ``RunGraphNode``.

        ``WorkerContext`` exposes ``node_id`` but not ``task_slug``; the
        leaf's message needs the slug so observers can identify which
        leaf sent it without joining back to the graph table.  Fallback
        for the rare ``node_id is None`` case is a readable placeholder
        so messages still land rather than raising from test scaffolding.
        """
        if node_id is None:
            return "unknown"
        with get_session() as session:
            node = session.get(RunGraphNode, node_id)
        return node.task_slug if node is not None else f"node-{node_id.hex[:8]}"


__all__ = ["BaseSmokeLeafWorker"]
