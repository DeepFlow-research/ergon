"""Legacy ``check_evaluators`` handler. Replaced by synchronous fanout
in PR 4.

Pre-PR-4, this function listened on ``task/completed`` and (a) invoked
``evaluate_task_run`` per evaluator and (b) terminated the sandbox.
Both responsibilities have moved into ``execute_task.py``'s
``try/finally`` so the sandbox is released by the same job that
acquired it.

The module stays importable until PR 11 deletes it so worktrees that
have not yet rebased can still load it without ImportError. The
Inngest function is no longer registered with ``ALL_FUNCTIONS`` (see
``core/infrastructure/inngest/registry.py``).

TODO(PR 11): delete this file. PR 4 unhooks the Inngest registration
and migrates every behavior; PR 11 drops the source.
"""

from typing import Any

from ergon_core.core.application.jobs.models import EvaluatorsResult
from ergon_core.core.application.events.task_events import TaskCompletedEvent


async def run_check_evaluators_job(  # slopcop: ignore[no-broad-except]
    ctx: Any,
    payload: TaskCompletedEvent,
    *,
    evaluate_task_run_function: Any,
) -> EvaluatorsResult:
    """Inert stub. The synchronous fanout in ``execute_task`` makes
    this dispatch obsolete; callers should not reach this path because
    the function is unregistered with Inngest.

    Kept as a callable so ad-hoc imports/tests don't fail loudly during
    the PR 4 → PR 11 transition.
    """

    del ctx, evaluate_task_run_function
    return EvaluatorsResult(
        task_id=payload.task_id,
        evaluators_found=0,
        evaluators_run=0,
    )
