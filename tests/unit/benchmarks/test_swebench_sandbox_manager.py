"""Install-dependencies behavior for SWE-Bench."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)

SAMPLE_PAYLOAD = {
    "instance_id": "django__django-12345",
    "repo": "django/django",
    "base_commit": "abcdef1234567890",
    "version": "4.2",
    "problem_statement": "fix foo",
    "fail_to_pass": ["tests.test_x"],
    "pass_to_pass": ["tests.test_y"],
    "environment_setup_commit": "setup123",
    "test_patch": "",
    "hints_text": "",
}


@pytest.mark.asyncio
async def test_install_runs_setup_and_install_scripts(monkeypatch: pytest.MonkeyPatch) -> None:
    from ergon_core.core.persistence import queries as q_mod

    monkeypatch.setattr(
        q_mod.queries.task_executions,
        "get_task_payload",
        lambda _tid: SAMPLE_PAYLOAD,
    )

    fake_spec = MagicMock(
        setup_env_script="echo setup",
        install_repo_script="echo install",
    )
    from ergon_builtins.benchmarks.swebench_verified import sandbox_manager as sm

    monkeypatch.setattr(sm, "make_test_spec", lambda _row: fake_spec)

    sandbox = MagicMock()
    sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout="ok"))

    manager = SWEBenchSandboxManager()
    await manager._install_dependencies(sandbox, uuid4())  # type: ignore[attr-defined]

    assert sandbox.commands.run.call_count == 2
    cmds = [c.args[0] for c in sandbox.commands.run.call_args_list]
    assert any("echo setup" in cmd for cmd in cmds)
    assert any("echo install" in cmd for cmd in cmds)


@pytest.mark.asyncio
async def test_install_raises_when_payload_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from ergon_core.core.persistence import queries as q_mod
    from ergon_core.core.providers.sandbox.errors import SandboxSetupError

    monkeypatch.setattr(q_mod.queries.task_executions, "get_task_payload", lambda _tid: None)

    manager = SWEBenchSandboxManager()
    with pytest.raises(SandboxSetupError, match="No task_payload"):
        await manager._install_dependencies(MagicMock(), uuid4())  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_install_raises_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    from ergon_builtins.benchmarks.swebench_verified import sandbox_manager as sm
    from ergon_core.core.persistence import queries as q_mod
    from ergon_core.core.providers.sandbox.errors import SandboxSetupError

    monkeypatch.setattr(
        q_mod.queries.task_executions, "get_task_payload", lambda _tid: SAMPLE_PAYLOAD
    )
    monkeypatch.setattr(
        sm,
        "make_test_spec",
        lambda _row: MagicMock(setup_env_script="false", install_repo_script="true"),
    )

    sandbox = MagicMock()
    sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=1, stdout="boom"))

    manager = SWEBenchSandboxManager()
    with pytest.raises(SandboxSetupError, match="setup_env"):
        await manager._install_dependencies(sandbox, uuid4())  # type: ignore[attr-defined]
