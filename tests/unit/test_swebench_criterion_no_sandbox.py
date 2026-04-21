"""Integration test: SWEBenchTestCriterion.evaluate() uses runtime.ensure_sandbox().

After Task 0 (PR 2 of the criterion-runtime-di-container RFC), the criterion
must NOT construct ``SWEBenchSandboxManager`` directly.  It must instead call
``context.runtime.ensure_sandbox()`` and retrieve the sandbox via
``context.runtime.sandbox_manager.get_sandbox()``.

Refs: docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md (PR 2 of 2)
Closes: docs/bugs/open/2026-04-18-swebench-criterion-spawns-sandbox.md
"""

from __future__ import annotations

import ergon_builtins.benchmarks.swebench_verified.criterion as criterion_module
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.swebench_verified.criterion import SWEBenchTestCriterion
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import WorkerOutput
from ergon_core.api.task_types import BenchmarkTask


def _task_payload() -> dict:
    return {
        "instance_id": "swe-001",
        "repo": "django/django",
        "base_commit": "abc123",
        "version": "4.2",
        "problem_statement": "Fix the bug",
        "hints_text": "",
        "fail_to_pass": ["test_foo"],
        "pass_to_pass": [],
        "environment_setup_commit": "abc123",
        "test_patch": "diff --git a/test.py b/test.py\n+# test",
    }


def _task() -> BenchmarkTask:
    return BenchmarkTask(
        task_key="swe-001",
        instance_key="default",
        description="Fix the bug",
        task_payload=_task_payload(),
    )


@pytest.mark.asyncio
async def test_evaluate_calls_ensure_sandbox_not_spawn_eval_sandbox() -> None:
    """Criterion calls runtime.ensure_sandbox(), not the removed _spawn_eval_sandbox."""
    sandbox = AsyncMock()
    sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout="log", stderr=""))
    sandbox.files.write = AsyncMock()

    mock_runtime = MagicMock()
    mock_runtime.ensure_sandbox = AsyncMock()
    mock_runtime.sandbox_manager.get_sandbox.return_value = sandbox

    ctx = EvaluationContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        task=_task(),
        worker_result=WorkerOutput(
            output="diff --git a/foo.py b/foo.py\n+pass",
            success=True,
            artifacts={"patch": "diff --git a/foo.py b/foo.py\n+pass"},
        ),
        runtime=mock_runtime,
    )

    with (
        patch.object(
            criterion_module,
            "make_test_spec",
            return_value=MagicMock(
                install_repo_script="echo ok",
                eval_script="echo ok",
            ),
        ),
        patch.object(
            criterion_module,
            "get_eval_report",
            return_value={"swe-001": {"resolved": True, "tests_status": {}}},
        ),
    ):
        criterion = SWEBenchTestCriterion()
        await criterion.evaluate(ctx)

    mock_runtime.ensure_sandbox.assert_awaited_once()


def test_spawn_eval_sandbox_does_not_exist() -> None:
    """_spawn_eval_sandbox must be gone from criterion module after Task 0."""
    assert not hasattr(criterion_module, "_spawn_eval_sandbox"), (
        "_spawn_eval_sandbox must be removed — use runtime.ensure_sandbox() instead"
    )


def test_swebench_sandbox_manager_not_imported() -> None:
    """SWEBenchSandboxManager must not be importable from criterion module."""
    assert not hasattr(criterion_module, "SWEBenchSandboxManager"), (
        "SWEBenchSandboxManager must not be imported in criterion.py"
    )
