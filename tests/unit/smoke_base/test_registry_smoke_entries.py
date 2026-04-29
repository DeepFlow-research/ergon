"""Registering ``tests.fixtures.smoke_components`` populates smoke slugs.

Phase C registers the researchrubrics happy + sad-path rows.  Phase D
adds minif2f and swebench-verified.  This test expects exactly what's
registered as of the current phase — update the expected sets when
adding env fixtures.
"""

import pytest


def _registry_maps():
    from ergon_core.api.registry import registry

    return registry.workers, registry.evaluators, registry.benchmarks, registry.sandbox_managers


def test_researchrubrics_slugs_registered() -> None:
    from tests.fixtures.smoke_components import register_smoke_fixtures

    register_smoke_fixtures()
    workers, evaluators, _, _ = _registry_maps()

    expected_workers = {
        "researchrubrics-smoke-worker",
        "researchrubrics-smoke-leaf",
        "researchrubrics-smoke-recursive-worker",
        "researchrubrics-sadpath-smoke-worker",
        "researchrubrics-smoke-leaf-failing",
    }
    for slug in expected_workers:
        assert slug in workers, f"worker slug missing from registry: {slug}"

    assert "researchrubrics-smoke-criterion" in evaluators
    assert "smoke-post-root-timing-criterion" in evaluators


def test_no_retired_slugs_present() -> None:
    from tests.fixtures.smoke_components import register_smoke_fixtures

    register_smoke_fixtures()
    workers, _, _, _ = _registry_maps()

    retired = {"canonical-smoke"}
    still_present = retired & set(workers.keys())
    assert not still_present, f"Retired worker slugs still in registry: {still_present}"


def test_register_is_idempotent() -> None:
    """Calling register_smoke_fixtures twice doesn't raise / duplicate."""
    from tests.fixtures.smoke_components import register_smoke_fixtures

    register_smoke_fixtures()
    register_smoke_fixtures()


def test_minif2f_slugs_registered() -> None:
    from tests.fixtures.smoke_components import register_smoke_fixtures

    register_smoke_fixtures()
    workers, evaluators, _, _ = _registry_maps()

    assert "minif2f-smoke-worker" in workers
    assert "minif2f-smoke-leaf" in workers
    assert "minif2f-smoke-recursive-worker" in workers
    assert "minif2f-sadpath-smoke-worker" in workers
    assert "minif2f-smoke-leaf-failing" in workers
    assert "minif2f-smoke-criterion" in evaluators


def test_swebench_slugs_registered() -> None:
    from tests.fixtures.smoke_components import register_smoke_fixtures

    register_smoke_fixtures()
    workers, evaluators, _, _ = _registry_maps()

    assert "swebench-smoke-worker" in workers
    assert "swebench-smoke-leaf" in workers
    assert "swebench-smoke-recursive-worker" in workers
    assert "swebench-sadpath-smoke-worker" in workers
    assert "swebench-smoke-leaf-failing" in workers
    assert "swebench-smoke-criterion" in evaluators


def test_smoke_benchmarks_are_test_owned_when_harness_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ergon_builtins.registry import register_builtins
    from ergon_core.api.registry import registry
    from tests.fixtures.smoke_components import register_smoke_fixtures
    from tests.fixtures.smoke_components.sandbox import SmokeSandboxManager

    register_builtins(registry)
    slugs = ("researchrubrics", "minif2f", "swebench-verified")
    original_benchmarks = {slug: registry.benchmarks[slug] for slug in slugs}
    original_managers = {slug: registry.sandbox_managers.get(slug) for slug in slugs}
    monkeypatch.setenv("ENABLE_TEST_HARNESS", "1")

    try:
        register_smoke_fixtures()
        for slug in slugs:
            assert registry.benchmarks[slug].__module__.startswith("tests.fixtures.smoke_components")
            assert registry.sandbox_managers[slug] is SmokeSandboxManager
    finally:
        registry.benchmarks.update(original_benchmarks)
        for slug, manager_cls in original_managers.items():
            if manager_cls is None:
                registry.sandbox_managers.pop(slug, None)
            else:
                registry.sandbox_managers[slug] = manager_cls
