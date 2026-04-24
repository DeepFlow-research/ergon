from uuid import uuid4

import pytest


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
    from ergon_builtins.registry import SANDBOX_MANAGERS

    slugs = (
        ResearchRubricsSmokeBenchmark.type_slug,
        MiniF2FSmokeBenchmark.type_slug,
        SweBenchSmokeBenchmark.type_slug,
    )
    original_managers = {slug: SANDBOX_MANAGERS.get(slug) for slug in slugs}
    monkeypatch.setenv("ENABLE_TEST_HARNESS", "1")

    try:
        register_smoke_fixtures()
        for slug in slugs:
            assert SANDBOX_MANAGERS[slug] is SmokeSandboxManager
    finally:
        for slug, manager_cls in original_managers.items():
            if manager_cls is None:
                SANDBOX_MANAGERS.pop(slug, None)
            else:
                SANDBOX_MANAGERS[slug] = manager_cls
