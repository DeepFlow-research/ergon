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
    }
    root_entries = {path.name for path in Path("tests").iterdir()}
    assert root_entries <= allowed
