"""``BaseSmokeLeafWorker._send_completion_message`` posts a
well-formed ``CreateMessageRequest`` to ``CommunicationService.save_message``.

Mocked: ``communication_service`` singleton + the DB session used by
``_lookup_task_slug``.  Real DB / Inngest is not needed at unit tier.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ergon_core.api import BenchmarkTask
from ergon_core.core.persistence.shared.types import AssignedWorkerSlug
from ergon_core.core.providers.sandbox.manager import AsyncSandbox
from ergon_core.core.runtime.services.communication_schemas import CreateMessageRequest
from ergon_core.test_support.smoke_fixtures.smoke_base.leaf_base import BaseSmokeLeafWorker
from ergon_core.test_support.smoke_fixtures.smoke_base.subworker import SubworkerResult


class _IdleSubworker:
    """Placeholder subworker never invoked — the test calls
    ``_send_completion_message`` directly."""

    async def work(
        self, node_id: str, sandbox: AsyncSandbox
    ) -> SubworkerResult:  # pragma: no cover
        raise NotImplementedError


class _Leaf(BaseSmokeLeafWorker):
    type_slug = "unit-test-leaf"
    subworker_cls = _IdleSubworker


def _leaf() -> _Leaf:
    return _Leaf(
        name="unit-test",
        model=None,
        task_id=uuid4(),
        sandbox_id="sbx-unit",
    )


def _context(*, node_id=None, execution_id=None, run_id=None):
    ctx = MagicMock()
    ctx.node_id = node_id or uuid4()
    ctx.execution_id = execution_id or uuid4()
    ctx.run_id = run_id or uuid4()
    ctx.sandbox_id = "sbx-unit"
    return ctx


def _patch_session_with_task_slug(monkeypatch, slug: str) -> None:
    """Patch ``get_session`` so ``_lookup_task_slug`` returns ``slug``."""
    node = MagicMock()
    node.task_slug = slug
    session = MagicMock()
    session.get = MagicMock(return_value=node)
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=session)
    cm.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(
        "ergon_core.test_support.smoke_fixtures.smoke_base.leaf_base.get_session",
        lambda: cm,
    )


@pytest.mark.asyncio
async def test_send_completion_message_posts_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_send_completion_message`` builds a ``CreateMessageRequest`` with
    ``from_agent_id='leaf-{slug}'``, ``to_agent_id='parent'``, topic
    ``'smoke-completion'`` and posts it via ``communication_service``."""
    saved: list[CreateMessageRequest] = []

    async def _record(request: CreateMessageRequest) -> MagicMock:
        saved.append(request)
        return MagicMock()

    monkeypatch.setattr(
        "ergon_core.test_support.smoke_fixtures.smoke_base.leaf_base.communication_service.save_message",
        AsyncMock(side_effect=_record),
    )
    _patch_session_with_task_slug(monkeypatch, "l_2")

    leaf = _leaf()
    ctx = _context()
    result = SubworkerResult(
        file_path="/workspace/final_output/probe_l_2.json",
        probe_stdout="OK",
        probe_exit_code=0,
    )

    await leaf._send_completion_message(ctx, result)

    assert len(saved) == 1
    req = saved[0]
    assert req.run_id == ctx.run_id
    assert req.task_execution_id == ctx.execution_id
    assert req.from_agent_id == "leaf-l_2"
    assert req.to_agent_id == "parent"
    assert req.thread_topic == "smoke-completion"
    assert "l_2" in req.content
    assert "exit=0" in req.content


@pytest.mark.asyncio
async def test_send_completion_message_not_called_when_subworker_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_send_completion_message must not be called when subworker.work() raises."""
    save_mock = AsyncMock()
    monkeypatch.setattr(
        "ergon_core.test_support.smoke_fixtures.smoke_base.leaf_base.communication_service.save_message",
        save_mock,
    )
    # Mock sandbox reconnect so execute() doesn't need a real sandbox.
    monkeypatch.setattr(
        "ergon_core.test_support.smoke_fixtures.smoke_base.leaf_base.SmokeSandboxManager.reconnect",
        AsyncMock(return_value=MagicMock(sandbox_id="smoke-sandbox-unit")),
    )

    class _FailingSubworker:
        async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
            raise RuntimeError("sad-path: deliberate fail")

    class _FailingLeaf(BaseSmokeLeafWorker):
        type_slug = "unit-test-leaf-failing"
        subworker_cls = _FailingSubworker

    leaf = _FailingLeaf(name="unit-test", model=None, task_id=uuid4(), sandbox_id="sbx-unit")
    task = BenchmarkTask(task_slug="l_fail", instance_key="default", description="x")

    with pytest.raises(RuntimeError, match="sad-path"):
        async for _ in leaf.execute(task, context=_context()):
            pass

    save_mock.assert_not_called()
