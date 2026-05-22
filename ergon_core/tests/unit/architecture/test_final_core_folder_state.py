from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
CORE_ROOT = ROOT / "ergon_core" / "ergon_core" / "core"
DOCS_ROOT = ROOT / "docs"


FINAL_CORE_PACKAGES = {
    "application",
    "infrastructure",
    "jobs",
    "persistence",
    "rl",
    "shared",
    "views",
}

RETIRED_ROOTS = (
    CORE_ROOT / "domain",
    CORE_ROOT / "rest_api",
    CORE_ROOT / "application" / "jobs",
    CORE_ROOT / "application" / "read_models",
    CORE_ROOT / "application" / "graph",
    CORE_ROOT / "application" / "tasks",
    CORE_ROOT / "application" / "workflows",
    CORE_ROOT / "infrastructure" / "inngest" / "handlers",
)

FINAL_HOMES = (
    CORE_ROOT / "application" / "runtime",
    CORE_ROOT / "views",
    CORE_ROOT / "jobs",
    CORE_ROOT / "infrastructure" / "http",
    CORE_ROOT / "shared" / "context_parts.py",
)

DELETED_COMPATIBILITY_SYMBOLS = (
    "Context" + "Event" + "Payload",
    "Worker" + "Yield",
    "Telemetry" + "Repository",
    "Create" + "Task" + "Evaluation",
    "Benchmark" + "Definition" + "Record",
    "Experiment" + "Cohort",
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def test_core_top_level_package_shape_is_final() -> None:
    assert {
        path.name for path in CORE_ROOT.iterdir() if path.is_dir() and path.name != "__pycache__"
    } == FINAL_CORE_PACKAGES


def test_final_core_homes_exist_and_retired_roots_are_deleted() -> None:
    missing = [path.relative_to(ROOT).as_posix() for path in FINAL_HOMES if not path.exists()]
    retired = [path.relative_to(ROOT).as_posix() for path in RETIRED_ROOTS if path.exists()]

    assert missing == []
    assert retired == []


def test_deleted_compatibility_symbols_have_no_production_references() -> None:
    offenders: list[str] = []
    for path in _python_files(ROOT / "ergon_core" / "ergon_core"):
        text = path.read_text()
        for symbol in DELETED_COMPATIBILITY_SYMBOLS:
            if symbol in text:
                offenders.append(f"{path.relative_to(ROOT)} references {symbol}")

    assert offenders == []


def test_persistence_does_not_import_outer_or_application_layers() -> None:
    forbidden = (
        "ergon_core.core.application",
        "ergon_core.core.infrastructure",
        "ergon_core.core.jobs",
        "ergon_core.core.views",
    )
    offenders: list[str] = []

    for path in _python_files(CORE_ROOT / "persistence"):
        for module in _imports(path):
            if module.startswith(forbidden):
                offenders.append(f"{path.relative_to(ROOT)} imports {module}")

    assert offenders == []


def test_runtime_evaluation_and_views_do_not_import_jobs() -> None:
    checked_roots = (
        CORE_ROOT / "application" / "runtime",
        CORE_ROOT / "application" / "evaluation",
        CORE_ROOT / "views",
    )
    offenders: list[str] = []

    for root in checked_roots:
        for path in _python_files(root):
            for module in _imports(path):
                if module.startswith("ergon_core.core.jobs"):
                    offenders.append(f"{path.relative_to(ROOT)} imports {module}")

    assert offenders == []


def test_job_contracts_do_not_import_services_persistence_or_infrastructure() -> None:
    forbidden_prefixes = (
        "ergon_core.core.application.runtime",
        "ergon_core.core.application.evaluation",
        "ergon_core.core.application.resources",
        "ergon_core.core.application.ports",
        "ergon_core.core.application.communication",
        "ergon_core.core.infrastructure",
        "ergon_core.core.persistence",
        "ergon_core.core.views",
    )
    forbidden_names = {"get_session", "Session", "SQLModel", "select"}
    offenders: list[str] = []

    for path in (CORE_ROOT / "jobs").rglob("contract.py"):
        text = path.read_text()
        for module in _imports(path):
            if module.startswith(forbidden_prefixes) or module.endswith(".service"):
                offenders.append(f"{path.relative_to(ROOT)} imports {module}")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                offenders.append(f"{path.relative_to(ROOT)} references {node.id}")

    assert offenders == []


def test_job_inngest_wrappers_do_not_query_sqlmodel_directly() -> None:
    forbidden_snippets = ("get_session(", "select(", "session.exec(", "session.query(")
    offenders: list[str] = []

    for path in (CORE_ROOT / "jobs").rglob("inngest.py"):
        text = path.read_text()
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {snippet!r}")

    assert offenders == []


def test_infrastructure_does_not_own_views_or_resource_append_policy() -> None:
    forbidden_snippets = (
        "RunResourceRepository(",
        "RunResource(",
        "session.add(RunResource",
    )
    forbidden_view_builders = {"build_run_snapshot", "_build_task_tree_for_run"}
    offenders: list[str] = []

    for path in _python_files(CORE_ROOT / "infrastructure"):
        text = path.read_text()
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {snippet!r}")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in forbidden_view_builders
            ):
                offenders.append(f"{path.relative_to(ROOT)} defines {node.name}")

    assert offenders == []


def test_architecture_docs_describe_landed_final_core_layout() -> None:
    architecture_readme = (DOCS_ROOT / "architecture" / "README.md").read_text()
    runtime_lifecycle_doc = (DOCS_ROOT / "architecture" / "02_runtime_lifecycle.md").read_text()
    rfc_readme = (
        DOCS_ROOT
        / "rfcs"
        / "active"
        / "2026-05-18-core-domain-structure-standardization"
        / "README.md"
    ).read_text()

    assert "## Status: landed" in architecture_readme
    assert "status: landed" in rfc_readme
    assert "implementation-plan stack has landed" in rfc_readme

    for package in sorted(FINAL_CORE_PACKAGES):
        assert f"`core/{package}`" in architecture_readme
    for retired in ("core/domain", "core/rest_api", "core/application/read_models"):
        assert f"`{retired}`" in architecture_readme

    assert "`core/application/events/runtime.py`" in runtime_lifecycle_doc
    assert "job-local `contract.py` files re-export" in runtime_lifecycle_doc
    stale_runtime_contract_claims = (
        "event payload contract",
        "Define the event payload in `contract.py`",
        "| Event contracts | `core/jobs/**/contract.py` |",
    )
    for stale_claim in stale_runtime_contract_claims:
        assert stale_claim not in runtime_lifecycle_doc
