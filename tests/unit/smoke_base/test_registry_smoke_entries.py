"""Registering ``ergon_core.test_support.smoke_fixtures`` populates smoke slugs.

Phase C registers the researchrubrics happy + sad-path rows.  Phase D
adds minif2f and swebench-verified.  This test expects exactly what's
registered as of the current phase — update the expected sets when
adding env fixtures.
"""

import pytest


def test_researchrubrics_slugs_registered() -> None:
    from ergon_core.test_support.smoke_fixtures import register_smoke_fixtures
    from ergon_builtins.registry import EVALUATORS, WORKERS

    register_smoke_fixtures()

    expected_workers = {
        "researchrubrics-smoke-worker",
        "researchrubrics-smoke-leaf",
        "researchrubrics-sadpath-smoke-worker",
        "researchrubrics-smoke-leaf-failing",
    }
    for slug in expected_workers:
        assert slug in WORKERS, f"worker slug missing from registry: {slug}"

    assert "researchrubrics-smoke-criterion" in EVALUATORS


def test_no_retired_slugs_present() -> None:
    from ergon_core.test_support.smoke_fixtures import register_smoke_fixtures
    from ergon_builtins.registry import WORKERS

    register_smoke_fixtures()

    retired = {"canonical-smoke"}
    still_present = retired & set(WORKERS.keys())
    assert not still_present, f"Retired worker slugs still in registry: {still_present}"


def test_register_is_idempotent() -> None:
    """Calling register_smoke_fixtures twice doesn't raise / duplicate."""
    from ergon_core.test_support.smoke_fixtures import register_smoke_fixtures

    register_smoke_fixtures()
    register_smoke_fixtures()


def test_minif2f_slugs_registered() -> None:
    from ergon_core.test_support.smoke_fixtures import register_smoke_fixtures
    from ergon_builtins.registry import EVALUATORS, WORKERS

    register_smoke_fixtures()

    assert "minif2f-smoke-worker" in WORKERS
    assert "minif2f-smoke-leaf" in WORKERS
    assert "minif2f-smoke-criterion" in EVALUATORS


def test_swebench_slugs_registered() -> None:
    from ergon_core.test_support.smoke_fixtures import register_smoke_fixtures
    from ergon_builtins.registry import EVALUATORS, WORKERS

    register_smoke_fixtures()

    assert "swebench-smoke-worker" in WORKERS
    assert "swebench-smoke-leaf" in WORKERS
    assert "swebench-smoke-criterion" in EVALUATORS


def test_smoke_benchmarks_are_test_owned_when_harness_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ergon_core.test_support.smoke_fixtures import register_smoke_fixtures
    from ergon_builtins.registry import BENCHMARKS, SANDBOX_MANAGERS
    from ergon_core.test_support.smoke_fixtures.sandbox import SmokeSandboxManager

    slugs = ("researchrubrics", "minif2f", "swebench-verified")
    original_benchmarks = {slug: BENCHMARKS[slug] for slug in slugs}
    original_managers = {slug: SANDBOX_MANAGERS.get(slug) for slug in slugs}
    monkeypatch.setenv("ENABLE_TEST_HARNESS", "1")

    try:
        register_smoke_fixtures()
        for slug in slugs:
            assert BENCHMARKS[slug].__module__.startswith("ergon_core.test_support.smoke_fixtures")
            assert SANDBOX_MANAGERS[slug] is SmokeSandboxManager
    finally:
        BENCHMARKS.update(original_benchmarks)
        for slug, manager_cls in original_managers.items():
            if manager_cls is None:
                SANDBOX_MANAGERS.pop(slug, None)
            else:
                SANDBOX_MANAGERS[slug] = manager_cls
