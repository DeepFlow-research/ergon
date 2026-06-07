from __future__ import annotations

import ast
import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CORE_ROOT = ROOT / "ergon_core/core"
APPLICATION_ROOT = CORE_ROOT / "application"
RUNTIME_ROOT = APPLICATION_ROOT / "runtime"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def test_runtime_is_single_application_owner_for_graph_task_and_workflow_lifecycle() -> None:
    for retired in ("graph", "tasks", "workflows"):
        assert not (APPLICATION_ROOT / retired).exists()

    expected_modules = {
        "__init__.py",
        "errors.py",
        "events.py",
        "graph_repository.py",
        "graph_traversal.py",
        "lifecycle.py",
        "models.py",
        "resources.py",
        "sample_identity.py",
        "sample_lifecycle.py",
        "status.py",
        "task_cleanup.py",
        "task_execution.py",
        "task_execution_repository.py",
        "task_inspection.py",
        "task_management.py",
    }
    assert expected_modules <= {path.name for path in RUNTIME_ROOT.glob("*.py")}


def test_core_imports_do_not_reference_retired_runtime_packages() -> None:
    forbidden = (
        "ergon_core.core.application.graph",
        "ergon_core.core.application.tasks",
        "ergon_core.core.application.workflows",
    )
    offenders: list[str] = []
    for path in CORE_ROOT.rglob("*.py"):
        if "tests" in path.parts:
            continue
        for module in _imports(path):
            if module.startswith(forbidden):
                offenders.append(f"{path.relative_to(ROOT)} imports {module}")

    assert offenders == []


def test_runtime_services_do_not_reintroduce_duplicated_dispatch_or_identity_helpers() -> None:
    offenders: list[str] = []
    for path in RUNTIME_ROOT.glob("*.py"):
        if path.name in {"events.py", "sample_identity.py"}:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
                "_dispatch_task_ready",
                "_resolve_definition_id",
            }:
                offenders.append(f"{path.relative_to(ROOT)}::{node.name}")

    assert offenders == []


def test_runtime_public_service_parameters_use_task_id_vocabulary() -> None:
    offenders: list[str] = []
    for module_name in (
        "ergon_core.core.application.runtime.graph_repository",
        "ergon_core.core.application.runtime.task_inspection",
        "ergon_core.core.application.runtime.task_management",
        "ergon_core.core.application.runtime.resources",
        "ergon_core.core.application.runtime.sample_lifecycle",
    ):
        module = __import__(module_name, fromlist=["*"])
        for _, member in inspect.getmembers(module, inspect.isfunction):
            if member.__name__.startswith("_"):
                continue
            if "node_id" in inspect.signature(member).parameters:
                offenders.append(f"{module_name}.{member.__name__}")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module_name:
                continue
            for method_name, method in inspect.getmembers(cls, inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                if "node_id" in inspect.signature(method).parameters:
                    offenders.append(f"{module_name}.{cls.__name__}.{method_name}")

    assert offenders == []
