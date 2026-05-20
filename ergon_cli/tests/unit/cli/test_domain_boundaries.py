import ast
from pathlib import Path


def test_converted_services_do_not_import_argparse() -> None:
    root = Path(__file__).parents[3] / "ergon_cli" / "domains"
    service_files = [
        root / "doctor" / "service.py",
        root / "stack" / "service.py",
        root / "workers" / "service.py",
        root / "evaluators" / "service.py",
    ]

    for path in service_files:
        tree = ast.parse(path.read_text())
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        from_imports = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        ]
        assert "argparse" not in imports
        assert "argparse" not in from_imports
