"""Tests for :class:`SWEBenchAdapter` wired onto :class:`ReActWorker`.

Covers the two behaviours the SWE-Bench ReAct wiring must guarantee:

1. Before the ReAct loop, ``on_run_start`` runs ``spec.setup_env_script``
   and ``spec.install_repo_script`` against the sandbox registered on the
   singleton manager.
2. After the loop (even on failure), ``on_run_end`` extracts the patch
   via ``git diff HEAD`` from the workdir and ``transform_output``
   routes it through ``WorkerOutput.output``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_builtins.workers.baselines.adapters.swebench import SWEBenchAdapter
from ergon_builtins.workers.baselines.react_worker import ReActWorker
from ergon_core.api import BenchmarkTask, WorkerOutput
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager


@pytest.fixture(autouse=True)
def _reset_sandbox_singleton() -> None:
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}
    yield
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}


def _fake_task() -> BenchmarkTask:
    payload = {
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
    }
    return BenchmarkTask(
        task_slug="django__django-1",
        instance_key="default",
        description="Fix the thing",
        evaluator_binding_keys=("default",),
        task_payload=payload,
    )


def _ctx() -> WorkerContext:
    return WorkerContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sbx_test",
    )


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_runs_setup_scripts_before_react_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """setup_env_script and install_repo_script must run in the sandbox."""
    sandbox = MagicMock(name="AsyncSandbox")
    sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))

    ctx = _ctx()
    manager = MagicMock()
    manager.get_sandbox = MagicMock(return_value=sandbox)

    # Stub the ReAct loop so we do not spin up an LLM.
    async def _stub_run_agent(self, task) -> AsyncIterator:  # slopcop: ignore[no-typing-any]
        return
        yield

    monkeypatch.setattr(
        "ergon_builtins.workers.baselines.react_worker.ReActWorker._run_agent",
        _stub_run_agent,
    )

    fake_spec = MagicMock(
        setup_env_script="echo SETUP_ENV",
        install_repo_script="echo INSTALL_REPO",
        eval_script="echo EVAL",
    )

    with (
        patch(
            "ergon_builtins.workers.baselines.adapters.swebench.SWEBenchSandboxManager",
            return_value=manager,
        ),
        patch(
            "ergon_builtins.workers.baselines.adapters.swebench.make_test_spec",
            return_value=fake_spec,
        ),
    ):
        worker = ReActWorker(name="swebench-react", model=None, adapter=SWEBenchAdapter())
        async for _ in worker.execute(_fake_task(), context=ctx):
            pass

    invoked = [call.args[0] for call in sandbox.commands.run.call_args_list]
    assert any("SETUP_ENV" in c for c in invoked), invoked
    assert any("INSTALL_REPO" in c for c in invoked), invoked
    # The finally block also runs git diff — check it was wired.
    assert any("git diff HEAD" in c for c in invoked), invoked


@pytest.mark.asyncio
async def test_adapter_extracts_patch_via_git_diff() -> None:
    """_extract_patch should call git diff HEAD from the workdir."""
    sandbox = MagicMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="--- diff ---\n+foo", stderr="")
    )
    adapter = SWEBenchAdapter()
    adapter._sandbox = sandbox
    adapter._workdir = "/workspace/repo"

    output = await adapter._extract_patch()

    assert "--- diff ---" in output
    invoked = sandbox.commands.run.call_args.args[0]
    assert "git diff HEAD" in invoked
    assert "/workspace/repo" in invoked


@pytest.mark.asyncio
async def test_on_run_start_raises_when_no_sandbox_registered() -> None:
    """If the sandbox manager has no entry for task_id, on_run_start raises."""
    adapter = SWEBenchAdapter()
    ctx = _ctx()

    with pytest.raises(RuntimeError, match="requires a live sandbox"):
        await adapter.on_run_start(_fake_task(), ctx)


@pytest.mark.asyncio
async def test_on_run_start_raises_when_setup_env_script_fails() -> None:
    """If setup_env_script exits non-zero, on_run_start raises RuntimeError."""
    sandbox = MagicMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=1, stdout="boom", stderr="err")
    )

    manager = MagicMock()
    manager.get_sandbox = MagicMock(return_value=sandbox)

    fake_spec = MagicMock(
        setup_env_script="exit 1",
        install_repo_script="echo INSTALL_REPO",
        eval_script="echo EVAL",
    )

    with (
        patch(
            "ergon_builtins.workers.baselines.adapters.swebench.SWEBenchSandboxManager",
            return_value=manager,
        ),
        patch(
            "ergon_builtins.workers.baselines.adapters.swebench.make_test_spec",
            return_value=fake_spec,
        ),
    ):
        adapter = SWEBenchAdapter()
        with pytest.raises(RuntimeError, match="setup_env failed"):
            await adapter.on_run_start(_fake_task(), _ctx())


def test_transform_output_routes_patch_through_output_field() -> None:
    """transform_output should put self._patch into the output field and artifacts."""
    adapter = SWEBenchAdapter()
    adapter._patch = "--- a/foo\n+++ b/foo\n@@\n+bar\n"

    base = WorkerOutput(output="done", success=True, artifacts={})
    out = adapter.transform_output(_ctx(), base)
    assert out.output == adapter._patch
    assert out.artifacts["patch"] == adapter._patch
    assert out.success is True


def test_transform_output_marks_unsuccessful_when_patch_empty() -> None:
    """Empty / whitespace-only patch means the worker produced nothing."""
    adapter = SWEBenchAdapter()
    adapter._patch = "   \n"

    base = WorkerOutput(output="done", success=True, artifacts={})
    out = adapter.transform_output(_ctx(), base)
    assert out.success is False
