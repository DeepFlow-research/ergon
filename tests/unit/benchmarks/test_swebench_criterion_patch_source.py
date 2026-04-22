"""SWE-Bench criterion computes its own patch via runtime.run_command.

The pre-RFC-2026-04-22 path read ``worker.artifacts["patch"]`` with a
fallback to ``worker.output``. Neither carries across the durable
Inngest boundary, so the criterion must extract the patch itself by
running ``git add -A && git diff HEAD`` against the task sandbox.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.swebench_verified.criterion import SWEBenchTestCriterion
from ergon_core.api import WorkerOutput
from ergon_core.api.criterion_runtime import CommandResult
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.task_types import BenchmarkTask


def _fake_run(cmd: str, timeout: int = 30) -> CommandResult:
    """Return a non-empty patch for ``git diff HEAD``; benign otherwise."""
    if "git diff HEAD" in cmd:
        return CommandResult(
            stdout="diff --git a/x b/x\n-old\n+new\n",
            stderr="",
            exit_code=0,
        )
    return CommandResult(stdout="", stderr="", exit_code=0)


@pytest.mark.asyncio
async def test_criterion_computes_patch_via_run_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion must NOT read worker.artifacts or worker.output for the patch."""
    runtime = MagicMock()
    runtime.run_command = AsyncMock(side_effect=_fake_run)
    runtime.ensure_sandbox = AsyncMock()

    sandbox = MagicMock()
    sandbox.files.write = AsyncMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="PASSED", stderr="")
    )
    runtime.sandbox_manager = MagicMock()
    runtime.sandbox_manager.get_sandbox = MagicMock(return_value=sandbox)

    payload = {
        "instance_id": "django__django-1",
        "repo": "django/django",
        "base_commit": "abc",
        "version": "4.2",
        "problem_statement": "x",
        "fail_to_pass": ["tests.t"],
        "pass_to_pass": [],
        "environment_setup_commit": "setup",
        "test_patch": "",
        "hints_text": "",
    }

    # Worker produces NO artifacts and empty output; criterion must still
    # derive the patch from the sandbox.
    run_id = uuid4()
    context = EvaluationContext(
        run_id=run_id,
        task_id=uuid4(),
        execution_id=uuid4(),
        task=BenchmarkTask(
            task_slug="django-1",
            instance_key="default",
            description="d",
            task_payload=payload,
        ),
        worker_result=WorkerOutput(output="", success=True),
        sandbox_id="sbx-abc",
        runtime=runtime,
    )

    # Skip the heavy harness-grading path with a monkeypatch so the test
    # doesn't try to import swebench or run the real eval script.
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.criterion.get_eval_report",
        lambda **kwargs: {payload["instance_id"]: {"resolved": True, "tests_status": {}}},
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.criterion.make_test_spec",
        lambda row: MagicMock(install_repo_script=":", eval_script=":"),
    )

    criterion = SWEBenchTestCriterion()
    result = await criterion.evaluate(context)

    # At least one call to run_command must have been `git diff HEAD`.
    git_diff_calls = [
        call for call in runtime.run_command.await_args_list if "git diff HEAD" in call.args[0]
    ]
    assert git_diff_calls, (
        "criterion must compute its own patch via runtime.run_command('... git diff HEAD ...')"
    )
    assert result.passed is True  # matches the monkeypatched harness report


@pytest.mark.asyncio
async def test_criterion_short_circuits_on_empty_patch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty ``git diff`` still produces a 0-score criterion result."""

    async def _empty_diff(cmd: str, timeout: int = 30) -> CommandResult:
        return CommandResult(stdout="", stderr="", exit_code=0)

    runtime = MagicMock()
    runtime.run_command = AsyncMock(side_effect=_empty_diff)
    runtime.ensure_sandbox = AsyncMock()
    runtime.sandbox_manager = MagicMock()

    payload = {
        "instance_id": "django__django-1",
        "repo": "django/django",
        "base_commit": "abc",
        "version": "4.2",
        "problem_statement": "x",
        "fail_to_pass": ["tests.t"],
        "pass_to_pass": [],
        "environment_setup_commit": "setup",
        "test_patch": "",
        "hints_text": "",
    }

    context = EvaluationContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        task=BenchmarkTask(
            task_slug="django-1",
            instance_key="default",
            description="d",
            task_payload=payload,
        ),
        # artifacts["patch"] is populated but must be ignored now.
        worker_result=WorkerOutput(
            output="", success=True, artifacts={"patch": "diff --git a/x b/x\n"}
        ),
        sandbox_id="sbx-abc",
        runtime=runtime,
    )

    # Even if the criterion regresses and tries the old make_test_spec path,
    # monkeypatch so the test doesn't depend on the real swebench harness.
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.criterion.get_eval_report",
        lambda **kwargs: {payload["instance_id"]: {"resolved": False, "tests_status": {}}},
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.criterion.make_test_spec",
        lambda row: MagicMock(install_repo_script=":", eval_script=":"),
    )

    criterion = SWEBenchTestCriterion()
    result = await criterion.evaluate(context)
    assert result.passed is False
    assert result.score == 0.0
    assert "Empty patch" in (result.feedback or "")
