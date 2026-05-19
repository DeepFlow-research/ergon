"""Legacy GDPEval worker bridge — DELETED IN PR 11.

This file exists solely so the ``"gdpeval-react"`` registry slug
still resolves for experiments persisted before PR 10c.  Once PR 11
retires the legacy registry fallback chain, delete this entire
file along with ``sandbox_manager.py``.

Do NOT import from this file in new code.  v2 callers use
``workers.make_gdpeval_worker()``.
"""

from collections.abc import AsyncGenerator
from typing import ClassVar

from ergon_core.api import Task, WorkerContext, WorkerStreamItem

from ergon_builtins.shared.workers.react_worker import ReActWorker


_GDPEVAL_SYSTEM_PROMPT = """You are a GDPEval document-processing agent.

Use the provided tools to inspect input documents, transform data, run Python
when useful, and write final artifacts under /workspace/final_output. Keep a
short final answer that names the produced files and any assumptions.
"""


# TODO(PR 11): delete ``GDPEvalReactWorker`` entirely.  It only exists so
# the ``"gdpeval-react"`` slug in the worker registry keeps resolving for
# experiments persisted before PR 10c.  Once PR 11 retires the legacy
# worker fallback chain and ``TaskSpec``, this class has no callers.
class GDPEvalReactWorker(ReActWorker):
    """ReAct worker for GDPEval document-processing tasks.

    Legacy (v1) worker used by the registry and any experiments defined
    before PR 10c.  New experiments use plain ``ReActWorker`` with
    ``toolkit=GDPEvalToolkit()`` embedded in the Task.  This class
    stays alive until PR 11 deletes the registry bridge.
    """

    type_slug: ClassVar[str] = "gdpeval-react"
    system_prompt: str | None = _GDPEVAL_SYSTEM_PROMPT
    max_iterations: int = 40

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        # Legacy bridge: defers to the parent ReActWorker.execute which
        # builds tools from any attached toolkit.  The v1 dispatch path
        # is preserved here only to satisfy the registry slug; no
        # production caller exercises this body after PR 10c.
        async for item in super().execute(task, context=context):
            yield item
