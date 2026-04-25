"""Cross-benchmark env-injection contract for sandbox managers.

Every concrete :class:`BaseSandboxManager` subclass declares which env
vars its in-sandbox tools need via the ``required_env_keys`` ClassVar.
``BaseSandboxManager.create`` reads the matching lowercase attribute
from ``settings`` and threads the result into ``AsyncSandbox.create``'s
``envs`` kwarg.

These tests assert the round-trip for every registered manager:

- When ``required_env_keys`` is non-empty, a dummy value set on
  ``settings`` lands in the ``envs`` dict passed to
  ``AsyncSandbox.create``.
- When ``required_env_keys`` is empty, no ``envs`` kwarg is threaded
  (the sandbox sees no injected auth).

Adding a new benchmark with in-sandbox auth means: declare its keys
on its sandbox manager, set the corresponding attribute on
``settings``, add the manager class to ``_MANAGERS`` below — the
parametrised test runs unchanged.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager
from ergon_core.core.providers.sandbox.research_rubrics_manager import (
    ResearchRubricsSandboxManager,
)

# Every concrete ``BaseSandboxManager`` subclass ergon ships. Add new
# managers here so the env-injection contract is enforced for them too.
_MANAGERS: tuple[type[BaseSandboxManager], ...] = (
    MiniF2FSandboxManager,
    SWEBenchSandboxManager,
    GDPEvalSandboxManager,
    ResearchRubricsSandboxManager,
)


@pytest.fixture(autouse=True)
def _reset_sandbox_singleton() -> None:
    """Reset singleton + per-task state on every concrete manager."""
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}
    BaseSandboxManager._creation_locks = {}
    BaseSandboxManager._run_ids = {}
    BaseSandboxManager._display_task_ids = {}
    BaseSandboxManager._file_registries = {}
    BaseSandboxManager._created_files_registry = {}
    for cls in _MANAGERS:
        cls._instance = None
    yield
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}
    for cls in _MANAGERS:
        cls._instance = None


def _make_fake_sandbox() -> MagicMock:
    """Minimal AsyncSandbox stand-in that satisfies the base ``create`` path."""
    fake = MagicMock()
    fake.sandbox_id = "sbx_fake_env_contract"
    fake.commands.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))
    fake.files.write = AsyncMock()
    fake.run_code = AsyncMock(
        return_value=MagicMock(error=None, logs=MagicMock(stdout=[], stderr=[]))
    )
    return fake


def _install_async_sandbox_and_e2b_key(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Patch in a fake ``AsyncSandbox.create`` and a non-empty E2B key.

    Returns the ``fake_create`` AsyncMock so callers can inspect
    ``await_args.kwargs``.
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
    return fake_create


def _stub_subclass_lifecycle_hooks(
    monkeypatch: pytest.MonkeyPatch,
    manager_cls: type[BaseSandboxManager],
) -> None:
    """Stub per-manager ``_install_dependencies`` / ``_verify_setup`` /
    ``_create_directory_structure`` so the env-injection contract is
    exercised without each manager's benchmark-specific setup
    (Lean smoke checks, SWEBench toolchain installs, etc.).
    """
    monkeypatch.setattr(manager_cls, "_install_dependencies", AsyncMock())
    monkeypatch.setattr(manager_cls, "_verify_setup", AsyncMock())
    monkeypatch.setattr(manager_cls, "_create_directory_structure", AsyncMock())


@pytest.mark.parametrize(
    "manager_cls",
    _MANAGERS,
    ids=lambda cls: cls.__name__,
)
@pytest.mark.asyncio
async def test_required_env_keys_round_trip_into_sandbox(
    manager_cls: type[BaseSandboxManager],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every key declared in ``required_env_keys`` must appear in the
    ``envs`` dict threaded to ``AsyncSandbox.create`` with the value
    sourced from ``settings``."""
    # Seed every declared key with a unique dummy on settings so we can
    # verify round-trip per key, not just "something was set".
    expected_envs: dict[str, str] = {}
    for idx, key in enumerate(manager_cls.required_env_keys):
        dummy = f"dummy-{key}-{idx}"
        expected_envs[key] = dummy
        monkeypatch.setattr(
            f"ergon_core.core.providers.sandbox.manager.settings.{key.lower()}",
            dummy,
        )

    fake_create = _install_async_sandbox_and_e2b_key(monkeypatch)
    _stub_subclass_lifecycle_hooks(monkeypatch, manager_cls)

    mgr = manager_cls()
    await mgr.create(sandbox_key=uuid4(), run_id=uuid4())

    fake_create.assert_awaited_once()
    call_kwargs = fake_create.await_args.kwargs

    if manager_cls.required_env_keys:
        assert "envs" in call_kwargs, (
            f"{manager_cls.__name__} declares required_env_keys="
            f"{manager_cls.required_env_keys} but no envs kwarg was threaded to "
            f"AsyncSandbox.create"
        )
        for key, expected in expected_envs.items():
            assert call_kwargs["envs"].get(key) == expected, (
                f"{manager_cls.__name__}: expected sandbox envs[{key!r}]={expected!r}, "
                f"got {call_kwargs['envs'].get(key)!r}"
            )
    else:
        assert "envs" not in call_kwargs, (
            f"{manager_cls.__name__} declares no required_env_keys but "
            f"envs={call_kwargs.get('envs')!r} was threaded to AsyncSandbox.create"
        )


@pytest.mark.parametrize(
    "manager_cls",
    _MANAGERS,
    ids=lambda cls: cls.__name__,
)
def test_required_env_keys_is_a_tuple_of_strings(
    manager_cls: type[BaseSandboxManager],
) -> None:
    """Declarative shape check: ``required_env_keys`` must be a tuple of
    uppercase env-var names.  Catches drift (list vs tuple, lowercase,
    accidental reassignment to a single string)."""
    keys = manager_cls.required_env_keys
    assert isinstance(keys, tuple), (
        f"{manager_cls.__name__}.required_env_keys must be a tuple, got {type(keys).__name__}"
    )
    for key in keys:
        assert isinstance(key, str), (
            f"{manager_cls.__name__}.required_env_keys entries must be str, got {type(key).__name__}"
        )
        assert key == key.upper(), (
            f"{manager_cls.__name__}.required_env_keys entry {key!r} must be uppercase"
        )
