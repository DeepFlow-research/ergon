import ast
from pathlib import Path

CLI_ROOT = Path(__file__).parents[3] / "ergon_cli"
DOMAIN_ROOT = CLI_ROOT / "domains"


def _python_files(root: Path) -> list[Path]:
    return [path for path in sorted(root.rglob("*.py")) if "__pycache__" not in path.parts]


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def test_argparse_namespace_stays_at_command_boundaries() -> None:
    allowed_names = {"commands.py", "executor.py", "parser.py"}

    for path in _python_files(DOMAIN_ROOT) + _python_files(CLI_ROOT / "shared"):
        if path.name in allowed_names:
            continue
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "argparse":
                assert all(alias.name != "Namespace" for alias in node.names), path
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "Namespace"
                and isinstance(node.value, ast.Name)
                and node.value.id == "argparse"
            ):
                raise AssertionError(path)


def test_domain_services_do_not_import_argparse() -> None:
    for path in sorted(DOMAIN_ROOT.glob("*/service.py")):
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name != "argparse" for alias in node.names), path
            if isinstance(node, ast.ImportFrom):
                assert node.module != "argparse", path


def test_domain_services_do_not_print_except_setup_streaming_boundaries() -> None:
    allowed = {DOMAIN_ROOT / "benchmarks" / "service.py"}

    for path in sorted(DOMAIN_ROOT.glob("*/service.py")):
        if path in allowed:
            continue
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "print", path
