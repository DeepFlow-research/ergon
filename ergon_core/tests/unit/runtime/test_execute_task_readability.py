"""Readability guard for the task execution orchestration phases."""

import inspect

from ergon_core.core.application.jobs import execute_task


def test_execute_task_module_exposes_named_phase_helpers() -> None:
    # The verbs distinguish Inngest primitives: `_run_`/`_invoke_`/`_emit_`
    # map to `ctx.step.run` / `ctx.step.invoke` / `inngest_client.send`
    # respectively. PR 4 renamed the helpers that wrap `ctx.step.invoke`
    # from action verbs (`_setup_sandbox`, `_run_worker`, `_persist_outputs`)
    # to the `_invoke_<child-fn>` convention so the orchestrator body is
    # self-documenting about which Inngest primitive it crosses.
    for name in (
        "_prepare_execution",
        "_invoke_sandbox_setup",
        "_invoke_worker_execute",
        "_invoke_persist_outputs",
        "_fan_out_evaluators",
        "_emit_task_completed",
        "_emit_task_failed",
    ):
        assert inspect.iscoroutinefunction(getattr(execute_task, name))
