"""Env-injection tests for :class:`ResearchRubricsSandboxManager`.

The research-rubrics researcher worker invokes Exa tools (``exa_search``,
``exa_qa``, ``exa_get_content``) as skills that run *inside* the E2B
sandbox.  For those calls to authenticate, ``EXA_API_KEY`` from ``settings``
must be threaded into the sandbox process env at
``AsyncSandbox.create(envs=...)`` time.  This module asserts that
contract.

Without it, every real-LLM rollout would complete with the agent flailing
on Exa 401 errors — a degenerate distribution of failure modes, and one
that silently masks real simulator bugs.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ergon_core.core.providers.sandbox.manager import BaseSandboxManager
from ergon_core.core.providers.sandbox.research_rubrics_manager import (
    ResearchRubricsSandboxManager,
)


@pytest.fixture(autouse=True)
def _reset_sandbox_singleton() -> None:
    """Reset class-level singleton state between tests.

    ``BaseSandboxManager`` stores ``_instance`` and per-task dicts at
    class scope; leaking state across tests is real.
    """
    BaseSandboxManager._instance = None
    ResearchRubricsSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}
    BaseSandboxManager._creation_locks = {}
    BaseSandboxManager._run_ids = {}
    BaseSandboxManager._display_task_ids = {}
    BaseSandboxManager._file_registries = {}
    BaseSandboxManager._created_files_registry = {}
    yield
    BaseSandboxManager._instance = None
    ResearchRubricsSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}


def _make_fake_sandbox() -> MagicMock:
    """Return a MagicMock that satisfies ``BaseSandboxManager.create``.

    Base class calls ``run_code`` (for directory creation), ``files.write``
    (for writability smoke test), and ``commands.run`` (from the manager's
    own ``_install_dependencies`` override). All return successful sentinels.
    """
    fake = MagicMock()
    fake.sandbox_id = "sbx_fake_rr_001"
    fake.commands.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))
    fake.files.write = AsyncMock()
    fake.run_code = AsyncMock(
        return_value=MagicMock(error=None, logs=MagicMock(stdout=[], stderr=[]))
    )
    return fake


@pytest.mark.asyncio
async def test_create_injects_exa_api_key_into_sandbox_envs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EXA_API_KEY from settings must reach AsyncSandbox.create's envs kwarg."""
    fake_sandbox = _make_fake_sandbox()
    fake_create = AsyncMock(return_value=fake_sandbox)
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(create=fake_create),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-e2b-key",
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.exa_api_key",
        "test-exa-key-xyz",
    )

    mgr = ResearchRubricsSandboxManager()
    await mgr.create(sandbox_key=uuid4(), run_id=uuid4())

    fake_create.assert_awaited_once()
    call_kwargs = fake_create.await_args.kwargs
    assert "envs" in call_kwargs, (
        "ResearchRubricsSandboxManager.create must pass envs= to AsyncSandbox.create"
    )
    assert call_kwargs["envs"].get("EXA_API_KEY") == "test-exa-key-xyz", (
        f"expected EXA_API_KEY='test-exa-key-xyz' in sandbox envs, got {call_kwargs['envs']!r}"
    )


@pytest.mark.asyncio
async def test_create_fails_fast_when_required_key_missing_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A researchrubrics rollout with no EXA_API_KEY configured must fail
    at ``create()`` time with a clear message.

    Silently provisioning a sandbox would produce a run full of Exa 401s
    that look like model failures — we want the misconfiguration to
    surface before the subprocess even dispatches.
    """
    fake_sandbox = _make_fake_sandbox()
    fake_create = AsyncMock(return_value=fake_sandbox)
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.AsyncSandbox",
        MagicMock(create=fake_create),
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.e2b_api_key",
        "test-e2b-key",
    )
    monkeypatch.setattr(
        "ergon_core.core.providers.sandbox.manager.settings.exa_api_key",
        "",
    )

    mgr = ResearchRubricsSandboxManager()
    with pytest.raises(ValueError, match="EXA_API_KEY"):
        await mgr.create(sandbox_key=uuid4(), run_id=uuid4())

    fake_create.assert_not_awaited()
