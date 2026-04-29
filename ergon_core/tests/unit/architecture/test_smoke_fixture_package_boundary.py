"""Guard smoke fixture imports stay behind an explicit test-support boundary."""

from pathlib import Path


def test_runtime_entrypoints_do_not_import_tests_smoke_fixtures() -> None:
    entrypoints = (
        Path("ergon_core/ergon_core/core/rest_api/app.py"),
        Path("ergon_cli/ergon_cli/composition/__init__.py"),
    )

    for path in entrypoints:
        text = path.read_text()
        assert "tests.e2e._fixtures" not in text
        assert "ergon_core.dev.smoke_fixtures" not in text
    assert (
        "tests.fixtures.smoke_components"
        not in Path("ergon_core/ergon_core/core/rest_api/app.py").read_text()
    )


def test_smoke_fixtures_live_in_tests_package() -> None:
    assert Path("tests/fixtures/smoke_components").is_dir()
    assert not Path("ergon_core/ergon_core/test_support/smoke_fixtures").exists()
    assert not Path("ergon_core/ergon_core/dev/smoke_fixtures").exists()
