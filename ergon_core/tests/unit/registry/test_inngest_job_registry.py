from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "ergon_core/core/infrastructure/inngest/registry.py"
JOBS_ROOT = ROOT / "ergon_core/core/jobs"


EXPECTED_FUNCTION_TRIGGERS = {
    "workflow-start": "workflow/started",
    "task-execute": "task/ready",
    "task-propagate": "task/completed",
    "task-failure-propagate": "task/failed",
    "workflow-complete": "workflow/completed",
    "workflow-failed": "workflow/failed",
    "sandbox-setup": "task/sandbox-setup",
    "worker-execute": "task/worker-execute",
    "persist-outputs": "task/persist-outputs",
    "evaluate-task-run": "task/evaluate",
    "block-descendants-on-failed": "task/failed",
    "cancel-orphans-on-cancelled": "task/cancelled",
    "cleanup-cancelled-task": "task/cancelled",
    "run-cleanup": "run/cleanup",
    "sandbox-cleanup-on-completed": "task/completed",
    "sandbox-cleanup-on-failed": "task/failed",
}


def _literal_keyword(call: ast.Call, keyword_name: str) -> object:
    for keyword in call.keywords:
        if keyword.arg == keyword_name:
            return ast.literal_eval(keyword.value)
    raise AssertionError(f"missing keyword {keyword_name!r}")


def test_inngest_function_ids_and_events_stay_registered() -> None:
    registered: dict[str, str] = {}

    for path in JOBS_ROOT.rglob("inngest.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if not (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "create_function"
                ):
                    continue
                fn_id = _literal_keyword(decorator, "fn_id")
                trigger = next(
                    keyword.value
                    for keyword in decorator.keywords
                    if keyword.arg == "trigger"
                )
                assert isinstance(trigger, ast.Call)
                event = _literal_keyword(trigger, "event")
                registered[str(fn_id)] = str(event)

    assert registered == EXPECTED_FUNCTION_TRIGGERS


def test_registry_imports_job_local_inngest_modules_only() -> None:
    text = REGISTRY.read_text()

    assert "ergon_core.core.infrastructure.inngest" + ".handlers" not in text
    assert "ergon_core.core.application" + ".jobs" not in text
    assert "ergon_core.core.jobs" in text
