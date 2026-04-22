"""BaseSmokeLeafWorker: runs the subworker, writes files into the sandbox,
yields a turn, and get_output reflects probe success/failure."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from ergon_builtins.workers.stubs.base_smoke_leaf import BaseSmokeLeafWorker
from ergon_builtins.workers.stubs.smoke_subworker import SubworkerResult


class _OkSubworker:
    async def work(self, node_id, sandbox):  # noqa: ANN001
        await sandbox.files.write(f"/workspace/final_output/{node_id}.txt", "hi")
        return SubworkerResult(
            file_path=f"/workspace/final_output/{node_id}.txt",
            probe_stdout="ok\n",
            probe_exit_code=0,
        )


class _OkLeaf(BaseSmokeLeafWorker):
    type_slug = "smoke-leaf-test-ok"
    subworker_cls = _OkSubworker  # type: ignore[assignment]


def _ctx(node_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(
        run_id=uuid4(),
        definition_id=None,
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sb-test",
        node_id=node_id,
        metadata={},
    )


@pytest.mark.asyncio
async def test_leaf_writes_file_yields_turn_and_reports_success() -> None:
    fake_sandbox = MagicMock()
    fake_sandbox.files.write = AsyncMock()

    with patch(
        "ergon_builtins.workers.stubs.base_smoke_leaf.AsyncSandbox.connect",
        AsyncMock(return_value=fake_sandbox),
    ):
        node_id = UUID("00000000-0000-0000-0000-0000000000aa")
        leaf = _OkLeaf(name="ok", model=None)
        ctx = _ctx(node_id)

        turns = [turn async for turn in leaf.execute(task=None, context=ctx)]

    assert len(turns) >= 1
    fake_sandbox.files.write.assert_awaited()
    output = leaf.get_output(ctx)
    assert output.success is True
    assert output.metadata["probe_exit_code"] == 0


@pytest.mark.asyncio
async def test_leaf_reports_failure_when_probe_nonzero() -> None:
    class _FailSubworker:
        async def work(self, node_id, sandbox):  # noqa: ANN001
            return SubworkerResult(f"/workspace/final_output/{node_id}.txt", "err", 1)

    class _FailLeaf(BaseSmokeLeafWorker):
        type_slug = "smoke-leaf-test-fail"
        subworker_cls = _FailSubworker  # type: ignore[assignment]

    fake_sandbox = MagicMock()
    fake_sandbox.files.write = AsyncMock()

    with patch(
        "ergon_builtins.workers.stubs.base_smoke_leaf.AsyncSandbox.connect",
        AsyncMock(return_value=fake_sandbox),
    ):
        node_id = UUID("00000000-0000-0000-0000-0000000000bb")
        leaf = _FailLeaf(name="fail", model=None)
        ctx = _ctx(node_id)
        _ = [t async for t in leaf.execute(task=None, context=ctx)]

    assert leaf.get_output(ctx).success is False
