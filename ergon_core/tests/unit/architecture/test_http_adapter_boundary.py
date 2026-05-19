"""Architecture guards for the REST HTTP adapter boundary."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CORE = ROOT / "ergon_core" / "ergon_core" / "core"
HTTP_ROOT = CORE / "infrastructure" / "http"
ROUTES_ROOT = HTTP_ROOT / "routes"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_top_level_rest_api_package_is_absent() -> None:
    assert not (CORE / "rest_api").exists()


def test_http_app_documents_bootstrap_boundary_exception() -> None:
    app_path = HTTP_ROOT / "app.py"
    docstring = ast.get_docstring(ast.parse(app_path.read_text()))

    assert docstring is not None
    assert "REST bootstrap/composition root" in docstring
    assert "bootstrap exception" in docstring


def test_http_route_modules_do_not_import_sqlmodel_table_classes() -> None:
    offenders: list[str] = []
    for path in sorted(ROUTES_ROOT.glob("*.py")):
        if path.name == "__init__.py":
            continue
        for module in _imported_modules(path):
            if module == "sqlmodel" or (
                module.startswith("ergon_core.core.persistence.") and module.endswith(".models")
            ):
                offenders.append(f"{path.relative_to(ROOT)} imports {module}")

    assert offenders == []
