"""Tests for :class:`MiniF2FReActWorker`.

Covers the two behaviours the worker must guarantee before any model run:

1. ``execute`` raises a clear error when no sandbox is registered on the
   singleton manager for the given ``task_id`` (catches misconfigured runs
   early).
2. ``execute`` builds the MiniF2F toolkit against the live sandbox and
   populates ``self.tools`` *before* the ReAct loop begins.
"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.workers.baselines.minif2f_react_worker import (
    MiniF2FReActWorker,
    _make_run_skill,
    _noop_stakeholder,
    _read_final_proof,
)
from ergon_core.api.worker_context import WorkerContext
from ergon_core.api import BenchmarkTask
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager


@pytest.fixture(autouse=True)
def _reset_sandbox_singleton() -> None:
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}
    yield
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}


def _make_context(task_id: UUID | None = None) -> WorkerContext:
    return WorkerContext(
        run_id=uuid4(),
        task_id=task_id or uuid4(),
        execution_id=uuid4(),
        sandbox_id="sbx_test",
    )


def _make_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_key="mathd_algebra_123",
        instance_key="default",
        description="prove the theorem",
        evaluator_binding_keys=("default",),
        task_payload={},
    )


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_raises_when_no_sandbox_registered() -> None:
    worker = MiniF2FReActWorker(name="minif2f-react", model=None)
    ctx = _make_context()

    gen = worker.execute(_make_task(), context=ctx)
    with pytest.raises(RuntimeError, match="requires a live sandbox"):
        await gen.__anext__()


@pytest.mark.asyncio
async def test_execute_builds_toolkit_against_live_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker must populate self.tools before handing off to the ReAct loop."""
    fake_sandbox = MagicMock(name="AsyncSandbox")
    task_id = uuid4()

    # Seed the singleton: simulate what MiniF2FSandboxManager.create() would do.
    mgr = MiniF2FSandboxManager()
    mgr._sandboxes[task_id] = fake_sandbox

    # Stub out the ReActWorker.execute tail so we don't actually spin up an
    # LLM. This yields zero turns; we only care that self.tools was set by
    # the time super().execute() is called.
    captured: dict[str, object] = {}

    async def _stub_super_execute(
        self, task, *, context
    ) -> AsyncIterator:  # slopcop: ignore[no-typing-any]
        captured["tools"] = list(self.tools)
        return
        yield  # make this an async generator

    monkeypatch.setattr(
        "ergon_builtins.workers.baselines.react_worker.ReActWorker.execute",
        _stub_super_execute,
    )

    worker = MiniF2FReActWorker(name="minif2f-react", model=None)
    ctx = _make_context(task_id=task_id)

    async for _ in worker.execute(_make_task(), context=ctx):
        pass

    tools = captured["tools"]
    assert isinstance(tools, list)
    # Five tools: write/check/verify lean + search_lemmas + ask_stakeholder
    assert len(tools) == 5


@pytest.mark.asyncio
async def test_run_skill_writes_lean_file_to_sandbox() -> None:
    """The minimal run_skill helper routes write_lean_file to sandbox.files.write."""
    from ergon_builtins.benchmarks.minif2f.toolkit import WriteLeanResponse

    sandbox = MagicMock()
    sandbox.files.write = AsyncMock()
    run_skill = _make_run_skill(sandbox)

    result = await run_skill(
        uuid4(),
        "write_lean_file",
        WriteLeanResponse,
        file_path="/workspace/scratchpad/draft.lean",
        content="theorem foo : 1 = 1 := rfl\n",
    )

    assert isinstance(result, WriteLeanResponse)
    assert result.success is True
    assert result.filename == "/workspace/scratchpad/draft.lean"
    assert result.bytes_written == len("theorem foo : 1 = 1 := rfl\n".encode())
    sandbox.files.write.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_skill_rejects_unsupported_skill() -> None:
    run_skill = _make_run_skill(MagicMock())
    with pytest.raises(ValueError, match="does not support skill"):
        await run_skill(uuid4(), "some_other_skill", type("X", (), {}))


@pytest.mark.asyncio
async def test_noop_stakeholder_returns_usable_message() -> None:
    reply = await _noop_stakeholder("any question")
    assert "No stakeholder" in reply


@pytest.mark.asyncio
async def test_read_final_proof_returns_contents_when_file_present() -> None:
    sandbox = MagicMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(
            exit_code=0,
            stdout="theorem foo : 1 = 1 := rfl\n",
            stderr="",
        )
    )
    result = await _read_final_proof(sandbox)
    assert result == "theorem foo : 1 = 1 := rfl\n"


@pytest.mark.asyncio
async def test_read_final_proof_returns_none_when_file_missing() -> None:
    sandbox = MagicMock()
    # cat returns non-zero when the file is absent (with 2>/dev/null, stderr empty)
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=1, stdout="", stderr="")
    )
    result = await _read_final_proof(sandbox)
    assert result is None


@pytest.mark.asyncio
async def test_read_final_proof_tolerates_sandbox_exception() -> None:
    sandbox = MagicMock()
    sandbox.commands.run = AsyncMock(side_effect=RuntimeError("sandbox dead"))
    result = await _read_final_proof(sandbox)
    assert result is None


@pytest.mark.asyncio
async def test_execute_populates_artifacts_with_final_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After execute() finishes, get_output must surface the scraped proof."""
    fake_sandbox = MagicMock(name="AsyncSandbox")
    # Used by _read_final_proof at end-of-execute.
    fake_sandbox.commands.run = AsyncMock(
        return_value=MagicMock(
            exit_code=0,
            stdout="theorem t : 1 = 1 := rfl\n",
            stderr="",
        )
    )
    task_id = uuid4()
    mgr = MiniF2FSandboxManager()
    mgr._sandboxes[task_id] = fake_sandbox

    async def _stub_super_execute(self, task, *, context):  # slopcop: ignore[no-typing-any]
        return
        yield

    # Stub the ReAct loop itself and the sync get_output on the base class
    # so we don't need a live DB.
    monkeypatch.setattr(
        "ergon_builtins.workers.baselines.react_worker.ReActWorker.execute",
        _stub_super_execute,
    )
    from ergon_core.api import WorkerOutput

    def _stub_base_get_output(self, context):  # slopcop: ignore[no-typing-any]
        return WorkerOutput(output="done", success=True, artifacts={})

    monkeypatch.setattr(
        "ergon_builtins.workers.baselines.react_worker.ReActWorker.get_output",
        _stub_base_get_output,
    )

    worker = MiniF2FReActWorker(name="minif2f-react", model=None)
    ctx = _make_context(task_id=task_id)

    async for _ in worker.execute(_make_task(), context=ctx):
        pass

    out = worker.get_output(ctx)
    # Proof is shipped in both artifacts AND output — the runtime's evaluator
    # dispatch only carries output_text forward, so output is the critical path.
    assert out.artifacts["final_solution.lean"] == "theorem t : 1 = 1 := rfl\n"
    assert out.output == "theorem t : 1 = 1 := rfl\n"
    assert out.success is True


@pytest.mark.asyncio
async def test_get_output_returns_base_when_no_proof_captured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the agent never wrote final_solution.lean, artifacts stay empty."""
    from ergon_core.api import WorkerOutput

    worker = MiniF2FReActWorker(name="minif2f-react", model=None)
    # _final_proof stays None because execute() was never called.

    def _stub_base_get_output(self, context):  # slopcop: ignore[no-typing-any]
        return WorkerOutput(output="", success=False, artifacts={})

    monkeypatch.setattr(
        "ergon_builtins.workers.baselines.react_worker.ReActWorker.get_output",
        _stub_base_get_output,
    )
    ctx = _make_context()
    out = worker.get_output(ctx)
    assert out.artifacts == {}
