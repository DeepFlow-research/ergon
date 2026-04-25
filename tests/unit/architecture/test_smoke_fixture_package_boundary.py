"""Guard smoke fixture imports stay behind an explicit test-support boundary."""

from pathlib import Path


def test_runtime_entrypoints_do_not_import_tests_smoke_fixtures() -> None:
    entrypoints = (
        Path("ergon_core/ergon_core/core/api/app.py"),
        Path("ergon_cli/ergon_cli/composition/__init__.py"),
    )

    for path in entrypoints:
        text = path.read_text()
        assert "tests.e2e._fixtures" not in text
        assert "ergon_core.dev.smoke_fixtures" not in text
        assert "ergon_core.test_support.smoke_fixtures" in text


def test_smoke_fixtures_live_in_test_support_package() -> None:
    assert Path("ergon_core/ergon_core/test_support/smoke_fixtures").is_dir()
    assert not Path("ergon_core/ergon_core/dev/smoke_fixtures").exists()
