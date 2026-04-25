from uuid import UUID, uuid4

import pytest

from ergon_core.core.providers.sandbox.event_sink import SandboxEventSink


class _RecordingSink(SandboxEventSink):
    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []
        self.closed: list[tuple[str, str]] = []

    async def sandbox_created(
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        timeout_minutes: int,
        template: str | None = None,
    ) -> None:
        self.created.append((str(run_id), sandbox_id))

    async def sandbox_command(
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        command: str,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        return None

    async def sandbox_closed(
        self,
        task_id: UUID,
        sandbox_id: str,
        reason: str,
        run_id: UUID | None = None,
    ) -> None:
        self.closed.append((str(run_id), sandbox_id))


@pytest.mark.asyncio
async def test_smoke_sandbox_manager_ignores_e2b_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.e2e._fixtures.sandbox import SmokeSandboxManager

    monkeypatch.setenv("E2B_API_KEY", "present-but-smoke-uses-local-fake")
    run_id = uuid4()
    task_id = uuid4()

    manager = SmokeSandboxManager()
    sandbox_id = await manager.create(task_id, run_id=run_id)

    assert sandbox_id.startswith("smoke-sandbox-")
    assert manager.get_sandbox(task_id) is await manager.reconnect(sandbox_id)


@pytest.mark.asyncio
async def test_smoke_sandbox_health_command_matches_swebench_probe() -> None:
    from tests.e2e._fixtures.sandbox import SmokeSandboxManager

    run_id = uuid4()
    task_id = uuid4()
    manager = SmokeSandboxManager()

    try:
        sandbox_id = await manager.create(task_id, run_id=run_id)
        sandbox = await manager.reconnect(sandbox_id)

        result = await sandbox.commands.run(
            "python /tmp/smoke_health.py && python -c 'import pytest; print(pytest.__version__)'",
        )

        assert result.exit_code == 0
        assert "HEALTH_OK" in result.stdout
    finally:
        await manager.terminate(task_id)


@pytest.mark.asyncio
async def test_static_teardown_closes_registered_smoke_sandbox() -> None:
    from ergon_core.core.providers.sandbox.event_sink import NoopSandboxEventSink
    from ergon_core.core.providers.sandbox.manager import BaseSandboxManager
    from tests.e2e._fixtures.sandbox import SmokeSandboxManager

    sink = _RecordingSink()
    SmokeSandboxManager.set_event_sink(sink)
    manager = SmokeSandboxManager()
    run_id = uuid4()
    task_id = uuid4()

    try:
        sandbox_id = await manager.create(task_id, run_id=run_id)

        terminated = await BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)

        assert terminated is True
        assert manager.get_sandbox(task_id) is None
        assert sink.closed == [(str(run_id), sandbox_id)]
    finally:
        SmokeSandboxManager.set_event_sink(NoopSandboxEventSink())
        SmokeSandboxManager._sandboxes.pop(task_id, None)
        SmokeSandboxManager._sandbox_ids.pop(locals().get("sandbox_id", ""), None)
        tempdir = SmokeSandboxManager._tempdirs.pop(task_id, None)
        if tempdir is not None:
            tempdir.cleanup()
        SmokeSandboxManager._run_ids.pop(task_id, None)
        SmokeSandboxManager._display_task_ids.pop(task_id, None)
        SmokeSandboxManager._sandbox_manager_classes.pop(task_id, None)


def test_smoke_benchmarks_use_smoke_sandbox_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.e2e._fixtures import register_smoke_fixtures
    from tests.e2e._fixtures.benchmarks import (
        MiniF2FSmokeBenchmark,
        ResearchRubricsSmokeBenchmark,
        SweBenchSmokeBenchmark,
    )
    from tests.e2e._fixtures.sandbox import SmokeSandboxManager
    from ergon_builtins.registry import BENCHMARKS, SANDBOX_MANAGERS

    slugs = (
        ResearchRubricsSmokeBenchmark.type_slug,
        MiniF2FSmokeBenchmark.type_slug,
        SweBenchSmokeBenchmark.type_slug,
    )
    original_benchmarks = {slug: BENCHMARKS[slug] for slug in slugs}
    original_managers = {slug: SANDBOX_MANAGERS.get(slug) for slug in slugs}
    monkeypatch.setenv("ENABLE_TEST_HARNESS", "1")

    try:
        register_smoke_fixtures()
        for slug in slugs:
            assert SANDBOX_MANAGERS[slug] is SmokeSandboxManager
    finally:
        BENCHMARKS.update(original_benchmarks)
        for slug, manager_cls in original_managers.items():
            if manager_cls is None:
                SANDBOX_MANAGERS.pop(slug, None)
            else:
                SANDBOX_MANAGERS[slug] = manager_cls


def test_smoke_parent_treats_blocked_children_as_terminal() -> None:
    from ergon_core.core.persistence.graph.status_conventions import TERMINAL_STATUSES
    from tests.e2e._fixtures.smoke_base.worker_base import _CHILD_WAIT_TERMINAL_STATUSES

    assert "blocked" not in TERMINAL_STATUSES
    assert "blocked" in _CHILD_WAIT_TERMINAL_STATUSES
