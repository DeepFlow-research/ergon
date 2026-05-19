from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CORE_ROOT = ROOT / "ergon_core/core"
JOBS_ROOT = CORE_ROOT / "jobs"


EXPECTED_JOB_PACKAGES = {
    "workflow/start",
    "workflow/complete",
    "workflow/fail",
    "task/execute",
    "task/propagate",
    "task/evaluate",
    "task/cleanup_cancelled",
    "task/cancel_orphans",
    "task/worker_execute",
    "sandbox/setup",
    "sandbox/cleanup",
    "resources/persist_outputs",
    "run/cleanup",
}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def test_job_composition_packages_own_contract_job_and_inngest_modules() -> None:
    assert not (CORE_ROOT / "application" / "jobs").exists()
    assert not (CORE_ROOT / "infrastructure" / "inngest" / "handlers").exists()
    assert not (CORE_ROOT / "application" / "jobs" / "models.py").exists()

    for package in EXPECTED_JOB_PACKAGES:
        job_dir = JOBS_ROOT / package
        assert (job_dir / "contract.py").exists(), package
        assert (job_dir / "job.py").exists(), package
        assert (job_dir / "inngest.py").exists(), package


def test_job_contracts_do_not_import_runtime_or_infrastructure_layers() -> None:
    forbidden = (
        "ergon_core.core.infrastructure",
        "ergon_core.core.persistence",
        "ergon_core.core.application.tasks",
        "ergon_core.core.application.workflows",
        "ergon_core.core.application.graph",
        "ergon_core.core.application.ports",
        "ergon_core.core.application.resources",
        "ergon_core.core.views",
    )
    offenders: list[str] = []

    for path in JOBS_ROOT.rglob("contract.py"):
        for module in _imports(path):
            if module.startswith(forbidden):
                offenders.append(f"{path.relative_to(ROOT)} imports {module}")

    assert offenders == []


def test_job_modules_do_not_import_concrete_infrastructure_adapters() -> None:
    allowed_inngest_imports = {
        "ergon_core.core.infrastructure.inngest.client",
        "ergon_core.core.infrastructure.inngest.errors",
    }
    forbidden = (
        "ergon_core.core.infrastructure.dashboard",
        "ergon_core.core.infrastructure.http",
    )
    offenders: list[str] = []

    for path in JOBS_ROOT.rglob("job.py"):
        for module in _imports(path):
            if module.startswith(forbidden):
                offenders.append(f"{path.relative_to(ROOT)} imports {module}")
            if (
                module.startswith("ergon_core.core.infrastructure.inngest")
                and module not in allowed_inngest_imports
            ):
                offenders.append(f"{path.relative_to(ROOT)} imports {module}")

    assert offenders == []


def test_inngest_modules_are_thin_framework_adapters() -> None:
    forbidden_snippets = (
        "select(",
        ".exec(",
        ".query(",
        "session.get(",
        "get_session(",
        "WorkflowService(",
        "TaskManagementService(",
        "EvaluationService(",
    )
    offenders: list[str] = []

    for path in JOBS_ROOT.rglob("inngest.py"):
        text = path.read_text()
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {snippet!r}")

    assert offenders == []
