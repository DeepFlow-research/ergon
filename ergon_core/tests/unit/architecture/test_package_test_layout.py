from pathlib import Path


def test_package_owned_test_roots_exist() -> None:
    assert Path("ergon_core/tests").is_dir()
    assert Path("ergon_builtins/tests").is_dir()
    assert Path("ergon_cli/tests").is_dir()


def test_root_tests_are_black_box_or_shared_only() -> None:
    allowed = {
        "__init__.py",
        "__pycache__",
        "conftest.py",
        "e2e",
        "fixtures",
        "integration",
        "real_llm",
        "unit",
    }
    root_entries = {path.name for path in Path("tests").iterdir()}
    assert root_entries <= allowed


def test_remaining_root_unit_tests_are_shared_or_transitional() -> None:
    allowed = {
        "__init__.py",
        "__pycache__",
        "architecture",
        "benchmarks",
        "builtins",
        "cli",
        "providers",
        "real_llm",
        "smoke_base",
        "state",
        "test_openrouter_budget.py",
        "test_suppression_budget.py",
        "workers",
    }
    unit_entries = {path.name for path in Path("tests/unit").iterdir()}
    assert unit_entries <= allowed
