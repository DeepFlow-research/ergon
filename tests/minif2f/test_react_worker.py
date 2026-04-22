"""Tests for :class:`MiniF2FAdapter` wired onto :class:`ReActWorker`.

Covers the behaviours the MiniF2F ReAct wiring must guarantee before any
model run:

1. ``build_tools`` raises a clear error when no sandbox is registered on
   the singleton manager for the given ``task_id`` (catches misconfigured
   runs early).
2. ``build_tools`` populates the tool list against the live sandbox.
3. ``on_run_end`` scrapes the final proof off the sandbox, and
   ``transform_output`` routes it through ``WorkerOutput.output`` so the
   criterion can read it.
"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.workers.baselines.adapters.minif2f import (
    MiniF2FAdapter,
    _make_run_skill,
    _read_final_proof,
)
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


def _make_context(task_id: UUID | None = None) -> WorkerContext:
    return WorkerContext(
        run_id=uuid4(),
        task_id=task_id or uuid4(),
        execution_id=uuid4(),
        sandbox_id="sbx_test",
    )


def _make_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_slug="mathd_algebra_123",
        instance_key="default",
        description="prove the theorem",
        evaluator_binding_keys=("default",),
        task_payload={},
    )


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_tools_raises_when_no_sandbox_registered() -> None:
    adapter = MiniF2FAdapter()
    ctx = _make_context()

    with pytest.raises(RuntimeError, match="requires a live sandbox"):
        await adapter.build_tools(_make_task(), ctx)


@pytest.mark.asyncio
async def test_build_tools_returns_toolkit_tools_against_live_sandbox() -> None:
    """Adapter must return the MiniF2F toolkit's tools against the live sandbox."""
    fake_sandbox = MagicMock(name="AsyncSandbox")
    task_id = uuid4()

    # Seed the singleton: simulate what MiniF2FSandboxManager.create() would do.
    mgr = MiniF2FSandboxManager()
    mgr._sandboxes[task_id] = fake_sandbox

    adapter = MiniF2FAdapter()
    tools = await adapter.build_tools(_make_task(), _make_context(task_id=task_id))

    assert isinstance(tools, list)
    # Four tools: write/check/verify lean + search_lemmas (no stakeholder in autonomous mode)
    assert len(tools) == 4


@pytest.mark.asyncio
async def test_react_worker_with_minif2f_adapter_populates_tools_before_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Composed worker must hand the adapter's tools to the ReAct loop."""
    fake_sandbox = MagicMock(name="AsyncSandbox")
    # _read_final_proof runs in on_run_end; set up a clean exit here.
    fake_sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=1, stdout="", stderr=""))
    task_id = uuid4()

    mgr = MiniF2FSandboxManager()
    mgr._sandboxes[task_id] = fake_sandbox

    captured: dict[str, object] = {}

    async def _stub_run_agent(self, task) -> AsyncIterator:  # slopcop: ignore[no-typing-any]
        captured["tools"] = list(self.tools)
        return
        yield  # async generator

    monkeypatch.setattr(
        "ergon_builtins.workers.baselines.react_worker.ReActWorker._run_agent",
        _stub_run_agent,
    )

    worker = ReActWorker(name="minif2f-react", model=None, adapter=MiniF2FAdapter())
    ctx = _make_context(task_id=task_id)

    async for _ in worker.execute(_make_task(), context=ctx):
        pass

    tools = captured["tools"]
    assert isinstance(tools, list)
    assert len(tools) == 4


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
    sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=1, stdout="", stderr=""))
    result = await _read_final_proof(sandbox)
    assert result is None


@pytest.mark.asyncio
async def test_read_final_proof_tolerates_sandbox_exception() -> None:
    sandbox = MagicMock()
    sandbox.commands.run = AsyncMock(side_effect=RuntimeError("sandbox dead"))
    result = await _read_final_proof(sandbox)
    assert result is None


@pytest.mark.asyncio
async def test_on_run_end_captures_proof_and_transform_output_routes_it() -> None:
    """After on_run_end runs, transform_output must surface the scraped proof."""
    fake_sandbox = MagicMock(name="AsyncSandbox")
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

    ctx = _make_context(task_id=task_id)
    adapter = MiniF2FAdapter()

    # Simulate the worker's call sequence: build_tools opens the sandbox,
    # then on_run_end scrapes the proof.
    await adapter.build_tools(_make_task(), ctx)
    await adapter.on_run_end(_make_task(), ctx)

    base = WorkerOutput(output="done", success=True, artifacts={})
    out = adapter.transform_output(ctx, base)

    # Proof is shipped in both artifacts AND output — the runtime's evaluator
    # dispatch only carries output_text forward, so output is the critical path.
    assert out.artifacts["final_solution.lean"] == "theorem t : 1 = 1 := rfl\n"
    assert out.output == "theorem t : 1 = 1 := rfl\n"
    assert out.success is True


def test_transform_output_passes_through_when_no_proof_captured() -> None:
    """If the agent never wrote final_solution.lean, artifacts stay empty."""
    adapter = MiniF2FAdapter()
    # _final_proof stays None because on_run_end was never called.
    base = WorkerOutput(output="", success=False, artifacts={})
    out = adapter.transform_output(_make_context(), base)
    assert out.artifacts == {}
    assert out.output == ""
    assert out.success is False
