"""Inngest job: terminate sandboxes after a task reaches terminal status.

The orchestrator (``execute_task``) used to release sandboxes inside a
``try/finally`` block.  That pattern is incompatible with Inngest's
step-replay model: each ``await ctx.step.invoke(...)`` raises a
``ResponseInterrupt`` (a ``BaseException``) to suspend the coroutine,
which fires the ``finally`` clause and terminates the sandbox **before**
the sub-function (worker_execute, evaluate_task_run) actually runs.

Instead, sandbox termination is owned by a sibling Inngest function
that listens for the terminal task events:

- ``task/completed`` — emitted by ``execute_task`` after all evaluators
  finish.  At this point every consumer of the sandbox is done.
- ``task/failed`` — emitted by ``execute_task`` on worker/evaluator
  failure or on prepare-error.  Evaluators don't run on the failure
  path, so the sandbox is safe to terminate immediately.
Terminal events carry ``sandbox_id`` when a sandbox was acquired.  The
cleanup function is idempotent: a second termination for the same sandbox_id is a no-op
(``terminate_external_sandbox`` returns ``NOT_FOUND_OR_ALREADY_CLOSED``).

The cleanup is gated on terminal events emitted **after** synchronous
evaluator fanout returns, so retry replay cannot terminate the sandbox
while evaluator workers are still running.
"""

import logging

import inngest

from ergon_core.core.application.events.task_events import (
    TaskCompletedEvent,
    TaskFailedEvent,
)
from ergon_core.core.infrastructure.sandbox.lifecycle import terminate_external_sandbox

logger = logging.getLogger(__name__)


async def run_sandbox_cleanup_on_completed(
    ctx: inngest.Context,
    payload: TaskCompletedEvent,
) -> str:
    """Terminate the sandbox after a successful task.

    Wraps ``terminate_external_sandbox`` in ``ctx.step.run`` so the cleanup
    happens exactly once even if the function is retried, and so the
    termination is observable in Inngest's step inspector.
    """
    sandbox_id = payload.sandbox_id
    if not sandbox_id:
        return "no_sandbox"

    return await ctx.step.run(
        "terminate-sandbox",
        lambda: _terminate(sandbox_id, reason="task/completed"),
    )


async def run_sandbox_cleanup_on_failed(
    ctx: inngest.Context,
    payload: TaskFailedEvent,
) -> str:
    """Terminate the sandbox after a failed task.

    ``TaskFailedEvent.sandbox_id`` is ``None`` when the task failed
    before ``sandbox_setup`` could create one (e.g. ``_prepare_execution``
    raised).  Skip cleanly in that case.
    """
    sandbox_id = payload.sandbox_id
    if not sandbox_id:
        return "no_sandbox"

    return await ctx.step.run(
        "terminate-sandbox",
        lambda: _terminate(sandbox_id, reason="task/failed"),
    )


async def _terminate(sandbox_id: str, *, reason: str) -> str:
    """Inner step body: terminate by sandbox_id, log, return reason."""
    result = await terminate_external_sandbox(sandbox_id)
    logger.info(
        "sandbox-cleanup sandbox_id=%s terminated=%s reason=%s trigger=%s",
        result.sandbox_id,
        result.terminated,
        result.reason,
        reason,
    )
    return str(result.reason)
