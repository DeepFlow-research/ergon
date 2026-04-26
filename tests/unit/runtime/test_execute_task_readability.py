"""Readability guard for the task execution orchestration phases."""

import inspect

from ergon_core.core.runtime.inngest import execute_task


def test_execute_task_module_exposes_named_phase_helpers() -> None:
    for name in (
        "_prepare_execution",
        "_setup_sandbox",
        "_run_worker",
        "_persist_outputs",
        "_emit_task_completed",
        "_emit_task_failed",
    ):
        assert inspect.iscoroutinefunction(getattr(execute_task, name))
