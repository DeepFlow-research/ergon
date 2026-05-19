import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SANDBOX_ROOT = ROOT / "ergon_core" / "core" / "infrastructure" / "sandbox"


def _attr_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _calls_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Call) and _attr_name(node.func) == name


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _import_from_offenders(path: Path, node: ast.ImportFrom) -> list[str]:
    offenders: list[str] = []
    imported_names = {alias.name for alias in node.names}
    if (
        node.module == "ergon_core.core.application.resources.repository"
        and "RunResourceRepository" in imported_names
    ):
        offenders.append(f"{_relative(path)} imports RunResourceRepository")
    if (
        node.module == "ergon_core.core.persistence.telemetry.models"
        and "RunResource" in imported_names
    ):
        offenders.append(f"{_relative(path)} imports RunResource")
    return offenders


def _import_offenders(path: Path, node: ast.Import) -> list[str]:
    offenders: list[str] = []
    imported_modules = {alias.name for alias in node.names}
    if "ergon_core.core.application.resources.repository" in imported_modules:
        offenders.append(f"{_relative(path)} imports resource repository module")
    if "ergon_core.core.persistence.telemetry.models" in imported_modules:
        offenders.append(f"{_relative(path)} imports telemetry models")
    return offenders


def _call_offenders(path: Path, node: ast.Call) -> list[str]:
    offenders: list[str] = []
    called = _attr_name(node.func)
    if called == "RunResource":
        offenders.append(f"{_relative(path)} constructs RunResource")
    if called == "append":
        receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
        if _attr_name(receiver) in {"_resource_repo", "resource_repo", "repo"}:
            offenders.append(f"{_relative(path)} appends through RunResourceRepository")
    if called == "add" and node.args and _calls_name(node.args[0], "RunResource"):
        offenders.append(f"{_relative(path)} adds RunResource through session")
    return offenders


def test_sandbox_infrastructure_does_not_append_run_resource_rows_directly() -> None:
    offenders: list[str] = []

    for path in SANDBOX_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                offenders.extend(_import_from_offenders(path, node))
            elif isinstance(node, ast.Import):
                offenders.extend(_import_offenders(path, node))
            elif isinstance(node, ast.Call):
                offenders.extend(_call_offenders(path, node))

    assert offenders == []
