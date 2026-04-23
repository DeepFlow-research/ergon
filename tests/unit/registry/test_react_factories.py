"""Smoke-test the new registry factory signatures."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from ergon_builtins.registry_core import WORKERS
from ergon_core.api import Worker


def test_no_bare_react_v1_entry() -> None:
    """RFC §1: `react-v1` bare entry removed — every factory binds a concrete toolkit."""
    assert "react-v1" not in WORKERS, (
        "Bare `react-v1` entry must not exist post-RFC. Use `minif2f-react` or "
        "`swebench-react` instead."
    )


def test_training_stub_factory_accepts_new_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-benchmark factories must accept `task_id` / `sandbox_id` kwargs (option a)."""
    factory = WORKERS["training-stub"]
    worker = factory(
        name="training-stub-under-test",
        model=None,
        task_id=uuid4(),
        sandbox_id="sbx-abc",
    )
    assert isinstance(worker, Worker)
    assert worker.name == "training-stub-under-test"


def test_minif2f_factory_builds_toolkit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The minif2f factory must construct a live toolkit bound to the sandbox."""
    # reason: imports deferred to avoid pulling registry_core + sandbox_manager
    # eagerly into test collection. Every test pulls its own patch target.
    from ergon_builtins import registry_core

    # reason: only needed for MagicMock spec= below; eager import would pull
    # the benchmark sandbox module into all registry tests.
    from ergon_builtins.benchmarks.minif2f import sandbox_manager as sm_mod

    fake_sandbox = MagicMock(name="fake-sandbox")
    fake_manager = MagicMock(spec=sm_mod.MiniF2FSandboxManager)
    fake_manager.get_sandbox.return_value = fake_sandbox
    # Patch on the call-site module so the test does not depend on lazy
    # imports inside the factory.
    monkeypatch.setattr(registry_core, "MiniF2FSandboxManager", lambda: fake_manager)

    factory = WORKERS["minif2f-react"]
    task_id = uuid4()
    worker = factory(
        name="minif2f-test",
        model=None,
        task_id=task_id,
        sandbox_id="sbx-minif2f",
    )
    assert isinstance(worker, Worker)
    # Factory should have asked the manager for the sandbox
    fake_manager.get_sandbox.assert_called_once_with(task_id)
    # Tools list must be non-empty (the MiniF2F toolkit publishes ≥1 tool)
    assert worker.tools != []
    # `max_iterations` must be explicit — 30 is the MiniF2F budget from the old adapter
    assert worker.max_iterations == 30
