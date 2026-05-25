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


def _import_offenders(path: Path, tree: ast.AST) -> list[str]:
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            offenders.extend(_import_from_offenders(path, node))
        elif isinstance(node, ast.Import):
            offenders.extend(_plain_import_offenders(path, node))
    return offenders


def _import_from_offenders(path: Path, node: ast.ImportFrom) -> list[str]:
    if node.module == "ergon_core.core.application.resources.repository":
        return [
            f"{path.relative_to(ROOT)} imports SampleResourceRepository"
            for alias in node.names
            if alias.name == "SampleResourceRepository"
        ]
    if node.module == "ergon_core.core.persistence.telemetry.models":
        return [
            f"{path.relative_to(ROOT)} imports SampleResource"
            for alias in node.names
            if alias.name == "SampleResource"
        ]
    return []


def _plain_import_offenders(path: Path, node: ast.Import) -> list[str]:
    offenders: list[str] = []
    for alias in node.names:
        if alias.name == "ergon_core.core.application.resources.repository":
            offenders.append(f"{path.relative_to(ROOT)} imports resource repository module")
        if alias.name == "ergon_core.core.persistence.telemetry.models":
            offenders.append(f"{path.relative_to(ROOT)} imports telemetry models")
    return offenders


def _call_offenders(path: Path, tree: ast.AST) -> list[str]:
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = _attr_name(node.func)
        if called == "SampleResource":
            offenders.append(f"{path.relative_to(ROOT)} constructs SampleResource")
        if _is_repository_append(node, called):
            offenders.append(f"{path.relative_to(ROOT)} appends through SampleResourceRepository")
        if called == "add" and node.args and _calls_name(node.args[0], "SampleResource"):
            offenders.append(f"{path.relative_to(ROOT)} adds SampleResource through session")
    return offenders


def _is_repository_append(node: ast.Call, called: str | None) -> bool:
    if called != "append" or not isinstance(node.func, ast.Attribute):
        return False
    return _attr_name(node.func.value) in {"_resource_repo", "resource_repo", "repo"}


def test_sandbox_infrastructure_does_not_append_run_resource_rows_directly() -> None:
    offenders: list[str] = []

    for path in SANDBOX_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        offenders.extend(_import_offenders(path, tree))
        offenders.extend(_call_offenders(path, tree))

    assert offenders == []
