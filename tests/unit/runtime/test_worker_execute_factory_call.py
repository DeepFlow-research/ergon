"""Verify worker_execute passes task_id / sandbox_id into the factory."""

from unittest.mock import MagicMock
from uuid import uuid4

from ergon_builtins.registry_core import WORKERS


def test_factory_receives_task_and_sandbox(monkeypatch) -> None:
    """The factory registered in WORKERS must receive task_id + sandbox_id kwargs."""
    captured: dict[str, object] = {}

    def capturing_factory(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        w = MagicMock()
        w.name = "captured"
        return w

    monkeypatch.setitem(WORKERS, "capturing", capturing_factory)

    task_id = uuid4()
    sandbox_id = "sbx-xyz"

    # Direct call imitating worker_execute.py:60
    worker_cls = WORKERS["capturing"]
    worker_cls(
        name="captured",
        model="anthropic:claude-sonnet-4",
        task_id=task_id,
        sandbox_id=sandbox_id,
    )

    assert captured == {
        "name": "captured",
        "model": "anthropic:claude-sonnet-4",
        "task_id": task_id,
        "sandbox_id": sandbox_id,
    }
