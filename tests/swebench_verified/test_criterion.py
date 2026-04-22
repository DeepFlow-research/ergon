"""Tests for SWEBenchTestCriterion."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_core.api.criterion_runtime import CommandResult
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import WorkerOutput
from ergon_core.api.task_types import BenchmarkTask

from ergon_builtins.benchmarks.swebench_verified.criterion import (
    SWEBenchTestCriterion,
)


def _task() -> BenchmarkTask:
    return BenchmarkTask(
        task_slug="django__django-1",
        instance_key="default",
        description="Fix the thing",
        evaluator_binding_keys=("default",),
        task_payload={
            "instance_id": "django__django-1",
            "repo": "django/django",
            "base_commit": "aaa",
            "version": "3.0",
            "problem_statement": "p",
            "hints_text": "",
            "fail_to_pass": ["t1"],
            "pass_to_pass": ["t0"],
            "environment_setup_commit": "aaa",
            "test_patch": "TP",
        },
    )


def _mock_runtime(
    *,
    patch_text: str = "PATCH",
    patch_exit_code: int = 0,
    install_exit_code: int = 0,
    eval_stdout: str = "log",
) -> MagicMock:
    """Return a mock ``CriterionRuntime`` wired via Protocol ops only.

    The criterion post-RFC-2026-04-22 uses ``runtime.run_command`` and
    ``runtime.write_file`` exclusively — no reach-through to
    ``sandbox_manager``. This mock routes ``run_command`` on command
    content: the ``git diff HEAD`` extraction returns ``patch_text``
    with ``patch_exit_code``; the ``install_repo`` bash script returns
    ``install_exit_code``; every other command (``git apply``, the eval
    script) returns a benign success with ``eval_stdout``.
    """
    runtime = MagicMock()
    runtime.ensure_sandbox = AsyncMock()
    runtime.write_file = AsyncMock()

    async def _dispatch(cmd: str, timeout: int = 30) -> CommandResult:
        if "git diff HEAD" in cmd:
            return CommandResult(stdout=patch_text, stderr="", exit_code=patch_exit_code)
        if "install" in cmd.lower() or "INSTALL" in cmd:
            return CommandResult(stdout=eval_stdout, stderr="", exit_code=install_exit_code)
        return CommandResult(stdout=eval_stdout, stderr="", exit_code=0)

    runtime.run_command = AsyncMock(side_effect=_dispatch)
    return runtime


def _ctx(
    *,
    output: str = "PATCH",
    artifacts: dict[str, object] | None = None,
    runtime: object | None = None,
) -> EvaluationContext:
    run_id = uuid4()
    return EvaluationContext(
        run_id=run_id,
        task_id=uuid4(),
        execution_id=uuid4(),
        task=_task(),
        worker_result=WorkerOutput(
            output=output,
            success=True,
            artifacts=artifacts if artifacts is not None else {"patch": output},
        ),
        runtime=runtime,
    )


@pytest.mark.asyncio
async def test_criterion_returns_score_0_for_empty_patch() -> None:
    """When ``git diff HEAD`` returns an empty tree, score is 0."""
    runtime = _mock_runtime(patch_text="")
    crit = SWEBenchTestCriterion(name="test-resolution", weight=1.0)
    ctx = _ctx(output="", artifacts={"patch": ""}, runtime=runtime)
    result = await crit.evaluate(ctx)
    assert result.score == 0.0
    assert result.passed is False
    assert "empty patch" in (result.feedback or "").lower()


@pytest.mark.asyncio
async def test_criterion_scores_1_when_report_resolved() -> None:
    runtime = _mock_runtime()

    with (
        patch(
            "ergon_builtins.benchmarks.swebench_verified.criterion.make_test_spec",
            return_value=MagicMock(
                install_repo_script="echo INSTALL",
                eval_script="echo EVAL",
            ),
        ),
        patch(
            "ergon_builtins.benchmarks.swebench_verified.criterion.get_eval_report",
            return_value={
                "django__django-1": {
                    "resolved": True,
                    "tests_status": {
                        "FAIL_TO_PASS": {"success": ["t1"], "failure": []},
                        "PASS_TO_PASS": {"success": ["t0"], "failure": []},
                    },
                }
            },
        ),
    ):
        crit = SWEBenchTestCriterion(name="test-resolution", weight=1.0)
        result = await crit.evaluate(_ctx(runtime=runtime))

    assert result.score == 1.0
    assert result.passed is True
    runtime.ensure_sandbox.assert_awaited_once()


@pytest.mark.asyncio
async def test_criterion_scores_0_when_report_unresolved() -> None:
    runtime = _mock_runtime()

    with (
        patch(
            "ergon_builtins.benchmarks.swebench_verified.criterion.make_test_spec",
            return_value=MagicMock(
                install_repo_script="echo INSTALL",
                eval_script="echo EVAL",
            ),
        ),
        patch(
            "ergon_builtins.benchmarks.swebench_verified.criterion.get_eval_report",
            return_value={
                "django__django-1": {
                    "resolved": False,
                    "tests_status": {
                        "FAIL_TO_PASS": {"success": [], "failure": ["t1"]},
                        "PASS_TO_PASS": {"success": ["t0"], "failure": []},
                    },
                }
            },
        ),
    ):
        crit = SWEBenchTestCriterion(name="test-resolution", weight=1.0)
        result = await crit.evaluate(_ctx(runtime=runtime))

    assert result.score == 0.0
    assert result.passed is False


@pytest.mark.asyncio
async def test_criterion_applies_test_patch_then_agent_patch() -> None:
    runtime = _mock_runtime()

    with (
        patch(
            "ergon_builtins.benchmarks.swebench_verified.criterion.make_test_spec",
            return_value=MagicMock(
                install_repo_script="INSTALL",
                eval_script="EVAL",
            ),
        ),
        patch(
            "ergon_builtins.benchmarks.swebench_verified.criterion.get_eval_report",
            return_value={"django__django-1": {"resolved": True, "tests_status": {}}},
        ),
    ):
        crit = SWEBenchTestCriterion(name="test-resolution", weight=1.0)
        await crit.evaluate(_ctx(runtime=runtime))

    # reason: RFC 2026-04-22 §3 — post-refactor the criterion writes files via
    # the `CriterionRuntime.write_file` Protocol op, not
    # `sandbox.files.write`. Two files must be written in order:
    # /tmp/test.patch then /tmp/agent.patch.
    written_paths = [call.args[0] for call in runtime.write_file.call_args_list]
    assert "/tmp/test.patch" in written_paths
    assert "/tmp/agent.patch" in written_paths
    assert written_paths.index("/tmp/test.patch") < written_paths.index("/tmp/agent.patch")
    # And the patch content bytes passed
    written_contents = {call.args[0]: call.args[1] for call in runtime.write_file.call_args_list}
    assert b"TP" in written_contents["/tmp/test.patch"]
    assert b"PATCH" in written_contents["/tmp/agent.patch"]


@pytest.mark.asyncio
async def test_criterion_raises_when_no_runtime_injected() -> None:
    """Without a runtime, evaluate raises RuntimeError (not AttributeError)."""
    crit = SWEBenchTestCriterion(name="test-resolution", weight=1.0)
    ctx = _ctx(output="some patch text", runtime=None)
    with (
        patch(
            "ergon_builtins.benchmarks.swebench_verified.criterion.make_test_spec",
            return_value=MagicMock(install_repo_script="echo", eval_script="echo"),
        ),
        pytest.raises(RuntimeError, match="CriterionRuntime"),
    ):
        await crit.evaluate(ctx)


@pytest.mark.asyncio
async def test_criterion_returns_error_when_install_repo_fails() -> None:
    """If install_repo_script exits non-zero, criterion returns error result.

    reason: RFC 2026-04-22 §3 replaced the ``sandbox_manager.get_sandbox``
    reach-through with Protocol-only ops, so the old ``sandbox_unavailable``
    error path no longer exists. The remaining early-exit on this code path
    is install-script failure, which this test now covers.
    """
    runtime = _mock_runtime(install_exit_code=1, eval_stdout="install blew up")

    with patch(
        "ergon_builtins.benchmarks.swebench_verified.criterion.make_test_spec",
        return_value=MagicMock(install_repo_script="echo INSTALL", eval_script="echo EVAL"),
    ):
        crit = SWEBenchTestCriterion(name="test-resolution", weight=1.0)
        result = await crit.evaluate(_ctx(runtime=runtime))

    assert result.score == 0.0
    assert result.passed is False
    assert "install_repo" in str(result.metadata)
