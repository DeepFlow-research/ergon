from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, patch

import pytest

from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager


class _FakeFiles:
    async def write(self, _path: str, _content: bytes) -> None:
        return None

    async def read(self, _path: str) -> str:
        return "{}"


class _FakeCommands:
    async def run(self, _command: str, timeout: int | None = None):  # noqa: ANN001
        del timeout
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _FakeSandbox:
    def __init__(self, sandbox_id: str) -> None:
        self.sandbox_id = sandbox_id
        self.files = _FakeFiles()
        self.commands = _FakeCommands()

    async def run_code(self, _code: str, language: str = "python"):  # noqa: ANN001
        del language
        return SimpleNamespace(error=None, logs=SimpleNamespace(stdout=[], stderr=[]))

    async def kill(self) -> None:
        return None

    async def set_timeout(self, timeout: int) -> None:
        del timeout
        return None


class _FakeSandboxManager(BaseSandboxManager):
    async def _install_dependencies(self, sandbox, task_id: UUID) -> None:  # noqa: ANN001
        del sandbox, task_id


class _BlockingUploadSandboxManager(_FakeSandboxManager):
    def configure(self, upload_started: asyncio.Event, allow_upload: asyncio.Event) -> None:
        self._upload_started = upload_started
        self._allow_upload = allow_upload

    async def _upload_directory(self, sandbox, local_dir: Path, remote_dir: str) -> None:  # noqa: ANN001
        del sandbox, local_dir, remote_dir
        self._upload_started.set()
        await self._allow_upload.wait()


@pytest.fixture(autouse=True)
def _reset_fake_manager_class_state() -> None:
    _FakeSandboxManager._instance = None
    _FakeSandboxManager._sandboxes = {}
    _FakeSandboxManager._file_registries = {}
    _FakeSandboxManager._created_files_registry = {}
    _FakeSandboxManager._skills_packages = {}
    _FakeSandboxManager._run_ids = {}
    _FakeSandboxManager._creation_locks = {}

    _BlockingUploadSandboxManager._instance = None
    _BlockingUploadSandboxManager._sandboxes = {}
    _BlockingUploadSandboxManager._file_registries = {}
    _BlockingUploadSandboxManager._created_files_registry = {}
    _BlockingUploadSandboxManager._skills_packages = {}
    _BlockingUploadSandboxManager._run_ids = {}
    _BlockingUploadSandboxManager._creation_locks = {}


def _make_skills_dir(tmp_path: Path) -> Path:
    skills_dir = tmp_path / "minif2f"
    skills_dir.mkdir()
    (skills_dir / "__init__.py").write_text("", encoding="utf-8")
    return skills_dir


@pytest.mark.asyncio
async def test_create_isolated_by_run_for_shared_logical_task(tmp_path: Path) -> None:
    shared_task_id = uuid4()
    run_a = uuid4()
    run_b = uuid4()
    skills_dir = _make_skills_dir(tmp_path)
    manager = _FakeSandboxManager()
    created_sandboxes = [_FakeSandbox("sandbox-a"), _FakeSandbox("sandbox-b")]

    with (
        patch(
            "h_arcane.core._internal.infrastructure.sandbox.settings.e2b_api_key",
            "test-key",
        ),
        patch(
            "h_arcane.core._internal.infrastructure.sandbox.AsyncSandbox.create",
            new=AsyncMock(side_effect=created_sandboxes),
        ) as mock_create,
        patch(
            "h_arcane.core._internal.infrastructure.sandbox.dashboard_emitter.sandbox_created",
            new=AsyncMock(),
        ),
    ):
        sandbox_id_a = await manager.create(
            run_a,
            run_id=run_a,
            skills_dir=skills_dir,
            display_task_id=shared_task_id,
        )
        sandbox_id_b = await manager.create(
            run_b,
            run_id=run_b,
            skills_dir=skills_dir,
            display_task_id=shared_task_id,
        )

    assert sandbox_id_a == "sandbox-a"
    assert sandbox_id_b == "sandbox-b"
    assert mock_create.await_count == 2
    assert manager.get_sandbox(run_a) is not None
    assert manager.get_sandbox(run_b) is not None
    assert manager.get_sandbox(run_a) is not manager.get_sandbox(run_b)
    assert manager._skills_packages[run_a] == "minif2f"
    assert manager._skills_packages[run_b] == "minif2f"


@pytest.mark.asyncio
async def test_create_waits_for_inflight_setup_before_reusing_same_run(tmp_path: Path) -> None:
    shared_task_id = uuid4()
    run_id = uuid4()
    skills_dir = _make_skills_dir(tmp_path)
    upload_started = asyncio.Event()
    allow_upload = asyncio.Event()
    manager = _BlockingUploadSandboxManager()
    manager.configure(upload_started, allow_upload)

    with (
        patch(
            "h_arcane.core._internal.infrastructure.sandbox.settings.e2b_api_key",
            "test-key",
        ),
        patch(
            "h_arcane.core._internal.infrastructure.sandbox.AsyncSandbox.create",
            new=AsyncMock(return_value=_FakeSandbox("sandbox-locked")),
        ) as mock_create,
        patch(
            "h_arcane.core._internal.infrastructure.sandbox.dashboard_emitter.sandbox_created",
            new=AsyncMock(),
        ),
    ):
        first = asyncio.create_task(
            manager.create(
                run_id,
                run_id=run_id,
                skills_dir=skills_dir,
                display_task_id=shared_task_id,
            )
        )
        await upload_started.wait()

        second = asyncio.create_task(
            manager.create(
                run_id,
                run_id=run_id,
                skills_dir=skills_dir,
                display_task_id=shared_task_id,
            )
        )
        await asyncio.sleep(0)
        assert not second.done()

        allow_upload.set()
        assert await first == "sandbox-locked"
        assert await second == "sandbox-locked"

    assert mock_create.await_count == 1
    assert manager._skills_packages[run_id] == "minif2f"
