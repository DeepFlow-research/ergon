"""Tests for SWEBenchTestCriterion."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import WorkerOutput
from ergon_core.api.task_types import BenchmarkTask

from ergon_builtins.benchmarks.swebench_verified.criterion import (
    SWEBenchTestCriterion,
)


def _task() -> BenchmarkTask:
    return BenchmarkTask(
        task_key="django__django-1",
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


def _mock_runtime(sandbox: object | None = None) -> MagicMock:
    """Return a mock CriterionRuntime with sandbox_manager wired up."""
    mock_sandbox = sandbox or _mock_sandbox()
    runtime = MagicMock()
    runtime.ensure_sandbox = AsyncMock()
    runtime.sandbox_manager = MagicMock()
    runtime.sandbox_manager.get_sandbox.return_value = mock_sandbox
    return runtime


def _mock_sandbox() -> AsyncMock:
    sb = AsyncMock()
    sb.commands.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout="log", stderr=""))
    sb.files.write = AsyncMock()
    return sb


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
    crit = SWEBenchTestCriterion(name="test-resolution", weight=1.0)
    ctx = _ctx(output="", artifacts={"patch": ""})
    result = await crit.evaluate(ctx)
    assert result.score == 0.0
    assert result.passed is False
    assert "empty patch" in (result.feedback or "").lower()


@pytest.mark.asyncio
async def test_criterion_scores_1_when_report_resolved() -> None:
    sandbox = _mock_sandbox()
    runtime = _mock_runtime(sandbox)

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
    sandbox = _mock_sandbox()
    runtime = _mock_runtime(sandbox)

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
    sandbox = _mock_sandbox()
    runtime = _mock_runtime(sandbox)

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

    # Two files were written to the sandbox: /tmp/test.patch and /tmp/agent.patch,
    # in that order.
    written_paths = [call.args[0] for call in sandbox.files.write.call_args_list]
    assert "/tmp/test.patch" in written_paths
    assert "/tmp/agent.patch" in written_paths
    assert written_paths.index("/tmp/test.patch") < written_paths.index("/tmp/agent.patch")
    # And the patch content bytes passed
    written_contents = {call.args[0]: call.args[1] for call in sandbox.files.write.call_args_list}
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
async def test_criterion_returns_sandbox_unavailable_when_get_sandbox_returns_none() -> None:
    """If runtime.sandbox_manager.get_sandbox returns None, criterion returns error result."""
    runtime = MagicMock()
    runtime.ensure_sandbox = AsyncMock()
    runtime.sandbox_manager.get_sandbox.return_value = None

    with patch(
        "ergon_builtins.benchmarks.swebench_verified.criterion.make_test_spec",
        return_value=MagicMock(install_repo_script="echo", eval_script="echo"),
    ):
        crit = SWEBenchTestCriterion(name="test-resolution", weight=1.0)
        result = await crit.evaluate(_ctx(runtime=runtime))

    assert result.score == 0.0
    assert result.passed is False
    assert "sandbox_unavailable" in str(result.metadata)
