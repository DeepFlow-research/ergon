"""Importing ``tests.e2e._fixtures`` populates the expected smoke slugs.

Phase C registers the researchrubrics happy + sad-path rows.  Phase D
adds minif2f and swebench-verified.  This test expects exactly what's
registered as of the current phase — update the expected sets when
adding env fixtures.
"""

import pytest


def test_researchrubrics_slugs_registered() -> None:
    import tests.e2e._fixtures  # noqa: F401  (import side-effect)
    from ergon_builtins.registry import EVALUATORS, WORKERS

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
    import tests.e2e._fixtures  # noqa: F401
    from ergon_builtins.registry import WORKERS

    retired = {"canonical-smoke"}
    still_present = retired & set(WORKERS.keys())
    assert not still_present, f"Retired worker slugs still in registry: {still_present}"


def test_register_is_idempotent() -> None:
    """Calling register_smoke_fixtures twice doesn't raise / duplicate."""
    from tests.e2e._fixtures import register_smoke_fixtures

    register_smoke_fixtures()
    register_smoke_fixtures()


def test_minif2f_slugs_registered() -> None:
    import tests.e2e._fixtures  # noqa: F401
    from ergon_builtins.registry import EVALUATORS, WORKERS

    assert "minif2f-smoke-worker" in WORKERS
    assert "minif2f-smoke-leaf" in WORKERS
    assert "minif2f-smoke-criterion" in EVALUATORS


def test_swebench_slugs_registered() -> None:
    import tests.e2e._fixtures  # noqa: F401
    from ergon_builtins.registry import EVALUATORS, WORKERS

    assert "swebench-smoke-worker" in WORKERS
    assert "swebench-smoke-leaf" in WORKERS
    assert "swebench-smoke-criterion" in EVALUATORS


def test_smoke_benchmarks_are_test_owned_when_harness_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.e2e._fixtures import register_smoke_fixtures
    from ergon_builtins.registry import BENCHMARKS

    slugs = ("researchrubrics", "minif2f", "swebench-verified")
    originals = {slug: BENCHMARKS[slug] for slug in slugs}
    monkeypatch.setenv("ENABLE_TEST_HARNESS", "1")

    try:
        register_smoke_fixtures()
        for slug in slugs:
            assert BENCHMARKS[slug].__module__.startswith("tests.e2e._fixtures")
    finally:
        BENCHMARKS.update(originals)
