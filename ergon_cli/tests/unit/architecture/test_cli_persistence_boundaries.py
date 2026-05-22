import ast
from pathlib import Path


FORBIDDEN_PREFIXES = ("ergon_core.core.persistence",)
FORBIDDEN_NAMES = {"Session"}


def test_run_and_experiment_domains_do_not_import_persistence_or_sessions() -> None:
    root = Path(__file__).parents[3] / "ergon_cli" / "domains"
    files = [
        *sorted((root / "runs").glob("*.py")),
        *sorted((root / "experiments").glob("*.py")),
    ]

    for path in files:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(FORBIDDEN_PREFIXES), path
                    assert alias.name != "sqlmodel", path
                    assert alias.name not in FORBIDDEN_NAMES, path
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                assert not node.module.startswith(FORBIDDEN_PREFIXES), path
                for alias in node.names:
                    assert alias.name not in FORBIDDEN_NAMES, path
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "Session"
                and isinstance(node.value, ast.Name)
                and node.value.id == "sqlmodel"
            ):
                raise AssertionError(path)
