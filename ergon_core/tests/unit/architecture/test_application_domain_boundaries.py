"""Application-domain import and layout boundary guards."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
PACKAGE_ROOT = ROOT / "ergon_core"
APPLICATION_ROOT = PACKAGE_ROOT / "ergon_core" / "core" / "application"
APPLICATION_PREFIX = "ergon_core.core.application"

PUBLIC_CROSS_DOMAIN_MODULES = {"service", "models", "errors"}
APPROVED_DOMAIN_FILES = {
    "__init__.py",
    "service.py",
    "models.py",
    "errors.py",
    "repository.py",
    "policy.py",
    "mappers.py",
    "dto_mapping.py",
}
APPROVED_DOMAIN_DIRS = {"policies", "__pycache__"}

LAYOUT_FILE_EXCEPTIONS = {
    "context": {"events.py"},
    "evaluation": {"scoring.py", "summary.py"},
    "events": {"base.py", "runtime.py"},
    "experiments": {"definition_writer.py", "handles.py", "launch.py"},
    "ports": {"dashboard.py", "resources.py"},
    "resources": {"publishing.py"},
    "runtime": {
        "events.py",
        "graph_lookup.py",
        "graph_repository.py",
        "graph_traversal.py",
        "lifecycle.py",
        "orchestration.py",
        "resources.py",
        "run_identity.py",
        "run_lifecycle.py",
        "run_records.py",
        "status.py",
        "task_cleanup.py",
        "task_errors.py",
        "task_execution.py",
        "task_execution_repository.py",
        "task_inspection.py",
        "task_management.py",
        "task_models.py",
        "task_service.py",
        "workflow_errors.py",
        "workflow_models.py",
    },
    "testing": {"test_harness_service.py"},
}
LAYOUT_DIR_EXCEPTIONS: dict[str, set[str]] = {}

_PRIVATE_CROSS_DOMAIN_IMPORT_LEDGER = (
    (
        "ergon_core.core.application.communication.service",
        "ergon_core.core.application.ports.dashboard",
        "PR 02: make application ports protocol-only public collaboration points.",
    ),
    (
        "ergon_core.core.application.experiments.launch",
        "ergon_core.core.application.events.runtime",
        "PR 05: route runtime event collaboration through public runtime facades.",
    ),
    (
        "ergon_core.core.application.experiments.launch",
        "ergon_core.core.application.runtime.run_records",
        "PR 05: route run-record access through public runtime facades.",
    ),
    (
        "ergon_core.core.application.ports.dashboard",
        "ergon_core.core.application.events.base",
        "PR 02: make application ports protocol-only public collaboration points.",
    ),
    (
        "ergon_core.core.application.resources.publishing",
        "ergon_core.core.application.ports.resources",
        "PR 02: make application ports protocol-only public collaboration points.",
    ),
    (
        "ergon_core.core.application.runtime.events",
        "ergon_core.core.application.events.runtime",
        "PR 05: route runtime event collaboration through public runtime facades.",
    ),
    (
        "ergon_core.core.application.runtime.run_lifecycle",
        "ergon_core.core.application.evaluation.scoring",
        "PR 03: keep evaluation scoring behind evaluation public APIs.",
    ),
    (
        "ergon_core.core.application.runtime.run_records",
        "ergon_core.core.application.events.runtime",
        "PR 05: route runtime event collaboration through public runtime facades.",
    ),
    (
        "ergon_core.core.application.runtime.run_records",
        "ergon_core.core.application.experiments.handles",
        "PR 04: decide and document experiment handle public surface.",
    ),
    (
        "ergon_core.core.application.runtime.task_execution",
        "ergon_core.core.application.ports.dashboard",
        "PR 02: make application ports protocol-only public collaboration points.",
    ),
    (
        "ergon_core.core.application.runtime.task_management",
        "ergon_core.core.application.events.runtime",
        "PR 05: route runtime event collaboration through public runtime facades.",
    ),
    (
        "ergon_core.core.application.runtime.task_management",
        "ergon_core.core.application.ports.dashboard",
        "PR 02: make application ports protocol-only public collaboration points.",
    ),
    (
        "ergon_core.core.application.runtime.task_models",
        "ergon_core.core.application.events.runtime",
        "PR 05: route runtime event collaboration through public runtime facades.",
    ),
)

PRIVATE_CROSS_DOMAIN_IMPORT_LEDGER = tuple(
    pytest.param(
        source_module,
        target_module,
        marks=pytest.mark.xfail(
            strict=True,
            reason=reason,
        ),
        id=f"{source_module} -> {target_module}",
    )
    for source_module, target_module, reason in _PRIVATE_CROSS_DOMAIN_IMPORT_LEDGER
)


@dataclass(frozen=True, order=True)
class ImportEdge:
    source_module: str
    target_module: str


def _module_name_for_path(path: Path) -> str:
    rel = path.relative_to(PACKAGE_ROOT)
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _source_package_parts(path: Path, module_name: str) -> list[str]:
    parts = module_name.split(".")
    if path.name == "__init__.py":
        return parts
    return parts[:-1]


def _resolve_import_from_base(
    *,
    path: Path,
    source_module: str,
    level: int,
    module: str | None,
) -> str:
    if level == 0:
        return module or ""

    package_parts = _source_package_parts(path, source_module)
    kept_parts = package_parts[: len(package_parts) - (level - 1)]
    base = ".".join(kept_parts)
    if module:
        return f"{base}.{module}"
    return base


def _application_domain_and_leaf(module_name: str) -> tuple[str, str | None] | None:
    if module_name == APPLICATION_PREFIX:
        return None
    if not module_name.startswith(f"{APPLICATION_PREFIX}."):
        return None

    parts = module_name.split(".")
    if len(parts) < 4:
        return None
    domain = parts[3]
    leaf = parts[4] if len(parts) > 4 else None
    return domain, leaf


def _application_domain_for_path(path: Path) -> str:
    return path.relative_to(APPLICATION_ROOT).parts[0]


def _domain_child_exists(domain: str, name: str) -> bool:
    domain_root = APPLICATION_ROOT / domain
    return (domain_root / f"{name}.py").exists() or (domain_root / name).is_dir()


def _import_targets(path: Path) -> list[str]:
    source_module = _module_name_for_path(path)
    tree = ast.parse(path.read_text(), filename=str(path))
    targets: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
            continue

        if not isinstance(node, ast.ImportFrom) or node.module == "__future__":
            continue

        base = _resolve_import_from_base(
            path=path,
            source_module=source_module,
            level=node.level,
            module=node.module,
        )
        if not base:
            continue

        for alias in node.names:
            if alias.name == "*":
                targets.append(base)
                continue
            domain_info = _application_domain_and_leaf(base)
            if domain_info is None:
                targets.append(base)
                continue
            domain, leaf = domain_info
            if leaf is None and _domain_child_exists(domain, alias.name):
                targets.append(f"{base}.{alias.name}")
            else:
                targets.append(base)

    return targets


def _application_import_edges() -> set[ImportEdge]:
    edges: set[ImportEdge] = set()
    for path in APPLICATION_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue

        source_module = _module_name_for_path(path)
        source_domain = _application_domain_for_path(path)
        for target_module in _import_targets(path):
            target_info = _application_domain_and_leaf(target_module)
            if target_info is None:
                continue

            target_domain, _leaf = target_info
            if target_domain == source_domain:
                continue

            edges.add(ImportEdge(source_module, target_module))

    return edges


def _private_cross_domain_imports() -> set[ImportEdge]:
    private_edges: set[ImportEdge] = set()
    for edge in _application_import_edges():
        _target_domain, leaf = _application_domain_and_leaf(edge.target_module) or (
            "",
            None,
        )
        if leaf is None or leaf in PUBLIC_CROSS_DOMAIN_MODULES:
            continue
        private_edges.add(edge)
    return private_edges


@pytest.mark.parametrize(
    ("source_module", "target_module"),
    PRIVATE_CROSS_DOMAIN_IMPORT_LEDGER,
)
def test_ledgered_private_cross_domain_imports_are_removed(
    source_module: str,
    target_module: str,
) -> None:
    """Strict xfail ledger: XPASS means a future cleanup removed the import."""

    assert ImportEdge(source_module, target_module) not in _private_cross_domain_imports()


def test_no_unledgered_private_cross_domain_imports() -> None:
    current = _private_cross_domain_imports()
    ledgered = {
        ImportEdge(source_module, target_module)
        for source_module, target_module, _reason in _PRIVATE_CROSS_DOMAIN_IMPORT_LEDGER
    }

    offenders = [
        f"{edge.source_module} imports private {edge.target_module}"
        for edge in sorted(current - ledgered)
    ]

    assert offenders == []


def test_cross_domain_imports_only_target_public_domain_modules() -> None:
    offenders: list[str] = []
    for edge in sorted(_application_import_edges()):
        _target_domain, leaf = _application_domain_and_leaf(edge.target_module) or (
            "",
            None,
        )
        if leaf is None or leaf in PUBLIC_CROSS_DOMAIN_MODULES:
            continue
        if any(
            (edge.source_module, edge.target_module) == (source_module, target_module)
            for source_module, target_module, _reason in _PRIVATE_CROSS_DOMAIN_IMPORT_LEDGER
        ):
            continue
        offenders.append(f"{edge.source_module} imports {edge.target_module}")

    assert offenders == []


def test_application_domain_directories_keep_approved_layout() -> None:
    offenders: list[str] = []

    for domain_root in sorted(path for path in APPLICATION_ROOT.iterdir() if path.is_dir()):
        if domain_root.name == "__pycache__":
            continue

        allowed_files = APPROVED_DOMAIN_FILES | LAYOUT_FILE_EXCEPTIONS.get(
            domain_root.name,
            set(),
        )
        allowed_dirs = APPROVED_DOMAIN_DIRS | LAYOUT_DIR_EXCEPTIONS.get(
            domain_root.name,
            set(),
        )

        for child in sorted(domain_root.iterdir()):
            if child.is_file() and child.name not in allowed_files:
                offenders.append(
                    f"{child.relative_to(ROOT)} is not an approved application domain filename"
                )
            elif child.is_dir() and child.name not in allowed_dirs:
                offenders.append(
                    f"{child.relative_to(ROOT)} is not an approved application domain directory"
                )

    assert offenders == []
