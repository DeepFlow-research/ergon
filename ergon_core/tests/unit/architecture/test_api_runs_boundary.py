import ast
from pathlib import Path


RUNS_API_PATH = (
    Path(__file__).resolve().parents[4]
    / "ergon_core"
    / "ergon_core"
    / "core"
    / "infrastructure"
    / "http"
    / "routes"
    / "runs.py"
)

DOMAIN_HELPERS = {
    "_build_communication_threads",
    "_build_task_map",
    "_context_events_by_task",
    "_task_keyed_evaluations",
    "_task_keyed_executions",
    "_task_keyed_resources",
    "_task_keyed_sandboxes",
    "_task_timestamps",
}


def test_runs_api_does_not_own_run_snapshot_read_model_helpers() -> None:
    tree = ast.parse(RUNS_API_PATH.read_text())

    helper_defs = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in DOMAIN_HELPERS
    }

    assert helper_defs == set()


def test_runs_api_does_not_import_persistence_or_sqlmodel() -> None:
    tree = ast.parse(RUNS_API_PATH.read_text())

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)

    forbidden = {
        module
        for module in imported_modules
        if module == "sqlmodel" or module.startswith("ergon_core.core.persistence")
    }

    assert forbidden == set()
