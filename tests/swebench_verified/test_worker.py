"""Tests for :class:`SWEBenchReActWorker`.

Covers the two behaviours the worker must guarantee:

1. Before the ReAct loop, it runs ``spec.setup_env_script`` and
   ``spec.install_repo_script`` against the sandbox registered on the
   singleton manager.
2. After the loop (even on failure), it extracts the patch via
   ``git diff HEAD`` from the workdir.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_core.api import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

from ergon_builtins.workers.baselines.swebench_worker import SWEBenchReActWorker


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

    # Wire the sandbox onto the singleton manager keyed by the test task_id.
    ctx = _ctx()
    # Stub the manager construction to hand back our controlled instance.
    manager = MagicMock()
    manager.get_sandbox = MagicMock(return_value=sandbox)

    # Stub the ReAct tail so we do not spin up an LLM.
    async def _stub_super_execute(
        self, task, *, context
    ) -> AsyncIterator:  # slopcop: ignore[no-typing-any]
        return
        yield  # make this an async generator

    monkeypatch.setattr(
        "ergon_builtins.workers.baselines.react_worker.ReActWorker.execute",
        _stub_super_execute,
    )

    fake_spec = MagicMock(
        setup_env_script="echo SETUP_ENV",
        install_repo_script="echo INSTALL_REPO",
        eval_script="echo EVAL",
    )

    with (
        patch(
            "ergon_builtins.workers.baselines.swebench_worker.SWEBenchSandboxManager",
            return_value=manager,
        ),
        patch(
            "ergon_builtins.workers.baselines.swebench_worker.make_test_spec",
            return_value=fake_spec,
        ),
    ):
        worker = SWEBenchReActWorker(name="swebench-react", model=None)
        async for _ in worker.execute(_fake_task(), context=ctx):
            pass

    invoked = [call.args[0] for call in sandbox.commands.run.call_args_list]
    assert any("SETUP_ENV" in c for c in invoked), invoked
    assert any("INSTALL_REPO" in c for c in invoked), invoked
    # The finally block also runs git diff — check it was wired.
    assert any("git diff HEAD" in c for c in invoked), invoked


@pytest.mark.asyncio
async def test_worker_extracts_patch_via_git_diff_on_output() -> None:
    """_extract_patch should call git diff HEAD from the workdir."""
    sandbox = MagicMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="--- diff ---\n+foo", stderr="")
    )
    worker = SWEBenchReActWorker(name="swebench-react", model=None)
    worker._sandbox = sandbox
    worker._workdir = "/workspace/repo"

    output = await worker._extract_patch()

    assert "--- diff ---" in output
    invoked = sandbox.commands.run.call_args.args[0]
    assert "git diff HEAD" in invoked
    assert "/workspace/repo" in invoked


@pytest.mark.asyncio
async def test_execute_raises_when_no_sandbox_registered() -> None:
    """If the sandbox manager has no entry for task_id, execute raises."""
    worker = SWEBenchReActWorker(name="swebench-react", model=None)
    ctx = _ctx()

    gen = worker.execute(_fake_task(), context=ctx)
    with pytest.raises(RuntimeError, match="requires a live sandbox"):
        await gen.__anext__()


@pytest.mark.asyncio
async def test_setup_raises_when_setup_env_script_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If setup_env_script exits non-zero, _run_setup raises RuntimeError."""
    sandbox = MagicMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=1, stdout="boom", stderr="err")
    )

    manager = MagicMock()
    manager.get_sandbox = MagicMock(return_value=sandbox)

    async def _stub_super_execute(self, task, *, context):  # slopcop: ignore[no-typing-any]
        return
        yield

    monkeypatch.setattr(
        "ergon_builtins.workers.baselines.react_worker.ReActWorker.execute",
        _stub_super_execute,
    )
    fake_spec = MagicMock(
        setup_env_script="exit 1",
        install_repo_script="echo INSTALL_REPO",
        eval_script="echo EVAL",
    )

    with (
        patch(
            "ergon_builtins.workers.baselines.swebench_worker.SWEBenchSandboxManager",
            return_value=manager,
        ),
        patch(
            "ergon_builtins.workers.baselines.swebench_worker.make_test_spec",
            return_value=fake_spec,
        ),
    ):
        worker = SWEBenchReActWorker(name="swebench-react", model=None)
        gen = worker.execute(_fake_task(), context=_ctx())
        with pytest.raises(RuntimeError, match="setup_env failed"):
            await gen.__anext__()


@pytest.mark.asyncio
async def test_get_output_routes_patch_through_output_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_output should put self._patch into the output field and artifacts."""
    from ergon_core.api import WorkerOutput

    worker = SWEBenchReActWorker(name="swebench-react", model=None)
    worker._patch = "--- a/foo\n+++ b/foo\n@@\n+bar\n"

    def _stub_base_get_output(self, context):  # slopcop: ignore[no-typing-any]
        return WorkerOutput(output="done", success=True, artifacts={})

    monkeypatch.setattr(
        "ergon_builtins.workers.baselines.react_worker.ReActWorker.get_output",
        _stub_base_get_output,
    )

    out = worker.get_output(_ctx())
    assert out.output == worker._patch
    assert out.artifacts["patch"] == worker._patch
    assert out.success is True


@pytest.mark.asyncio
async def test_get_output_marks_unsuccessful_when_patch_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty / whitespace-only patch means the worker produced nothing."""
    from ergon_core.api import WorkerOutput

    worker = SWEBenchReActWorker(name="swebench-react", model=None)
    worker._patch = "   \n"

    def _stub_base_get_output(self, context):  # slopcop: ignore[no-typing-any]
        return WorkerOutput(output="done", success=True, artifacts={})

    monkeypatch.setattr(
        "ergon_builtins.workers.baselines.react_worker.ReActWorker.get_output",
        _stub_base_get_output,
    )

    out = worker.get_output(_ctx())
    assert out.success is False
