"""ReActGenericWorker: composes toolkit from ctx.metadata['toolkit_benchmark']."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_builtins.workers.baselines.react_generic_worker import ReActGenericWorker


def _ctx(benchmark_slug: str) -> SimpleNamespace:
    return SimpleNamespace(
        run_id=uuid4(),
        node_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sb-test",
        task_id=uuid4(),
        definition_id=None,
        metadata={"toolkit_benchmark": benchmark_slug},
    )


def _async_iter(items: list[object]) -> object:
    async def _gen():
        for i in items:
            yield i

    return _gen()


@pytest.mark.asyncio
async def test_execute_composes_toolkit_from_metadata_for_swebench() -> None:
    # Instantiate with whatever signature ReActWorker uses; if unknown kwargs fail,
    # adapt this line to match the actual ReActWorker.__init__ signature.
    worker = ReActGenericWorker(name="w", model="x")
    ctx = _ctx("swebench-verified")
    fake_sandbox = MagicMock()

    called: dict[str, object] = {}

    def _spy(**kwargs: object) -> list[object]:
        called.update(kwargs)
        return ["tool-a", "tool-b"]

    with (
        patch(
            "ergon_builtins.workers.baselines.react_generic_worker.AsyncSandbox.connect",
            AsyncMock(return_value=fake_sandbox),
        ),
        patch(
            "ergon_builtins.workers.baselines.react_generic_worker.compose_benchmark_toolkit",
            side_effect=_spy,
        ),
        patch.object(
            ReActGenericWorker.__mro__[1],
            "execute",
            return_value=_async_iter([]),
        ),
    ):
        _turns = [t async for t in worker.execute(task=None, context=ctx)]

    assert called["benchmark_slug"] == "swebench-verified"
    assert worker.tools == ["tool-a", "tool-b"]


def test_raises_if_metadata_missing_toolkit_benchmark() -> None:
    worker = ReActGenericWorker(name="w", model="x")
    ctx = SimpleNamespace(
        run_id=uuid4(),
        node_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sb-test",
        task_id=uuid4(),
        definition_id=None,
        metadata={},
    )
    with pytest.raises(ValueError, match="toolkit_benchmark"):
        worker._benchmark_slug(ctx)
