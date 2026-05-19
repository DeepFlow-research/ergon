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


def test_sandbox_infrastructure_does_not_append_run_resource_rows_directly() -> None:
    offenders: list[str] = []

    for path in SANDBOX_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "ergon_core.core.application.resources.repository":
                    for alias in node.names:
                        if alias.name == "RunResourceRepository":
                            offenders.append(
                                f"{path.relative_to(ROOT)} imports RunResourceRepository"
                            )
                if node.module == "ergon_core.core.persistence.telemetry.models":
                    for alias in node.names:
                        if alias.name == "RunResource":
                            offenders.append(f"{path.relative_to(ROOT)} imports RunResource")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "ergon_core.core.application.resources.repository":
                        offenders.append(
                            f"{path.relative_to(ROOT)} imports resource repository module"
                        )
                    if alias.name == "ergon_core.core.persistence.telemetry.models":
                        offenders.append(f"{path.relative_to(ROOT)} imports telemetry models")
            if isinstance(node, ast.Call):
                called = _attr_name(node.func)
                if called == "RunResource":
                    offenders.append(f"{path.relative_to(ROOT)} constructs RunResource")
                if called == "append":
                    receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
                    if _attr_name(receiver) in {"_resource_repo", "resource_repo", "repo"}:
                        offenders.append(
                            f"{path.relative_to(ROOT)} appends through RunResourceRepository"
                        )
                if called == "add" and node.args and _calls_name(node.args[0], "RunResource"):
                    offenders.append(f"{path.relative_to(ROOT)} adds RunResource through session")

    assert offenders == []
