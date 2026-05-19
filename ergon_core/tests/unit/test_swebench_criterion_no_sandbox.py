"""SWEBenchTestCriterion.evaluate() uses the object-bound task sandbox."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import ergon_builtins.benchmarks.swebench_verified.criterion as criterion_module
import pytest
from ergon_builtins.benchmarks.swebench_verified.criterion import SWEBenchTestCriterion
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchTaskPayload
from ergon_core.api.criterion import CriterionContext
from ergon_core.api.worker import WorkerOutput
from ergon_core.api.benchmark import Task
from ergon_core.api.sandbox.runtime import CommandResult
from ergon_core.test_support.task_factory import task_with_id


def _task_payload() -> SWEBenchTaskPayload:
    return SWEBenchTaskPayload(
        instance_id="swe-001",
        repo="django/django",
        base_commit="abc123",
        version="4.2",
        problem_statement="Fix the bug",
        hints_text="",
        fail_to_pass=["test_foo"],
        pass_to_pass=[],
        environment_setup_commit="abc123",
        test_patch="diff --git a/test.py b/test.py\n+# test",
    )


def _task() -> Task[SWEBenchTaskPayload]:
    return task_with_id(
        uuid4(),
        cls=Task[SWEBenchTaskPayload],
        task_slug="swe-001",
        instance_key="default",
        description="Fix the bug",
        task_payload=_task_payload(),
    )


@pytest.mark.asyncio
async def test_evaluate_calls_ensure_sandbox_not_spawn_eval_sandbox() -> None:
    """Criterion calls runtime.ensure_sandbox(), not the removed _spawn_eval_sandbox.

    reason: RFC 2026-04-22 §3 — all sandbox ops go through Protocol methods
    (``run_command``, ``write_file``); the concrete ``sandbox_manager``
    attribute is never touched.
    """
    sandbox = MagicMock()
    sandbox.write_file = AsyncMock()
    # Criterion extracts the patch, runs install_repo, applies patches, and runs
    # the eval script via the object-bound sandbox. A single benign success
    # return value is enough to drive the happy-path harness shape.
    sandbox.run_command = AsyncMock(
        return_value=CommandResult(
            stdout="diff --git a/foo.py b/foo.py\n+pass\n",
            stderr="",
            exit_code=0,
        )
    )
    task = _task()
    task.sandbox = sandbox

    ctx = CriterionContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        task=task,
        worker_result=WorkerOutput(output="", success=True),
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

    assert sandbox.run_command.await_count >= 1


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
