"""Inert stub of the legacy `check_evaluators` Inngest function.

**Status:** unregistered with Inngest (see
`core/infrastructure/inngest/registry.py`), zero production callers.
The file only exists so in-flight worktrees from before PR 4 can
still `import` it without `ImportError` while they rebase.

**Why it was retired.** Pre-PR-4 this job listened on `task/completed`
and did two things: (1) invoked `evaluate_task_run` once per evaluator
(fire-and-forget) and (2) called `terminate_sandbox_by_id`. Step 2
ran in a *sibling* Inngest function from the one that acquired the
sandbox, so under retry replay the sandbox could be terminated while
eval workers were still running against it — the v1 lifecycle leak.
PR 4 fixes that by moving both responsibilities into
`execute_task.py`'s single `try/finally`:

  * fanout: `_fan_out_evaluators` → `ctx.step.invoke` + `asyncio.gather`
  * release: `terminate_sandbox_by_id` in the orchestrator's `finally`

External sandbox lifetime is now bounded by the same function that
acquired the sandbox, end of story.

**Deletion gate.** PR 11 (see RFC `09-implementation-plan` Δ.7
deletion list) deletes this file along with `EvaluateTaskRunRequest`
(the legacy multi-field payload), the `CriterionExecutor` Protocol,
and `terminate_sandbox_by_id`. No new code should land that touches
this module — if you find yourself wanting to import from it, route
through the orchestrator instead.
"""

from typing import Any

from ergon_core.core.application.events.task_events import TaskCompletedEvent
from ergon_core.core.application.jobs.models import EvaluatorsResult


# TODO(PR 11): delete the file (and the matching Inngest handler module
# under `core/infrastructure/inngest/handlers/`).
async def run_check_evaluators_job(
    ctx: Any,
    payload: TaskCompletedEvent,
    *,
    evaluate_task_run_function: Any,
) -> EvaluatorsResult:
    """Returns a zero-evaluator result without doing anything.

    Reached only by ad-hoc tests/imports during the PR 4 → PR 11
    transition — the Inngest dispatcher will never call this because
    the function is not in `ALL_FUNCTIONS`. Returning a real value
    (instead of raising) keeps stale callers green so the deletion
    in PR 11 is purely mechanical.
    """

    del ctx, evaluate_task_run_function
    return EvaluatorsResult(
        task_id=payload.task_id,
        evaluators_found=0,
        evaluators_run=0,
    )
