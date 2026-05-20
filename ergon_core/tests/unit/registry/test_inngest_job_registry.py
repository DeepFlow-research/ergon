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

EXPECTED_FUNCTION_ORDER = [
    "workflow-start",
    "task-execute",
    "task-propagate",
    "task-failure-propagate",
    "workflow-complete",
    "workflow-failed",
    "sandbox-setup",
    "worker-execute",
    "persist-outputs",
    "evaluate-task-run",
    "block-descendants-on-failed",
    "cancel-orphans-on-cancelled",
    "cleanup-cancelled-task",
    "run-cleanup",
    "sandbox-cleanup-on-completed",
    "sandbox-cleanup-on-failed",
]

RUN_CANCEL = (("run/cancelled", "event.data.run_id == async.data.run_id"),)
TASK_CANCEL = (("task/cancelled", "event.data.task_id == async.data.task_id"),)

EXPECTED_FUNCTION_METADATA = {
    "workflow-start": {
        "retries": 1,
        "cancel": RUN_CANCEL,
        "concurrency": (),
        "output": "WorkflowStartResult",
    },
    "task-execute": {
        "retries": 0,
        "cancel": (*RUN_CANCEL, *TASK_CANCEL),
        "concurrency": (15,),
        "output": "TaskExecuteResult",
    },
    "task-propagate": {
        "retries": 1,
        "cancel": RUN_CANCEL,
        "concurrency": (),
        "output": "TaskPropagateResult",
    },
    "task-failure-propagate": {
        "retries": 1,
        "cancel": RUN_CANCEL,
        "concurrency": (),
        "output": "TaskPropagateResult",
    },
    "workflow-complete": {
        "retries": 1,
        "cancel": RUN_CANCEL,
        "concurrency": (),
        "output": "WorkflowCompleteResult",
    },
    "workflow-failed": {
        "retries": 1,
        "cancel": RUN_CANCEL,
        "concurrency": (),
        "output": "WorkflowFailedResult",
    },
    "sandbox-setup": {
        "retries": 1,
        "cancel": (),
        "concurrency": (),
        "output": "SandboxReadyResult",
    },
    "worker-execute": {
        "retries": 0,
        "cancel": (),
        "concurrency": (),
        "output": "WorkerExecuteResult",
    },
    "persist-outputs": {
        "retries": 1,
        "cancel": (),
        "concurrency": (),
        "output": "PersistOutputsResult",
    },
    "evaluate-task-run": {
        "retries": 1,
        "cancel": RUN_CANCEL,
        "concurrency": (),
        "output": "EvaluateTaskRunResult",
    },
    "block-descendants-on-failed": {
        "retries": 1,
        "cancel": RUN_CANCEL,
        "concurrency": (),
        "output": "EmptySentinel",
    },
    "cancel-orphans-on-cancelled": {
        "retries": 1,
        "cancel": RUN_CANCEL,
        "concurrency": (),
        "output": "EmptySentinel",
    },
    "cleanup-cancelled-task": {
        "retries": 3,
        "cancel": RUN_CANCEL,
        "concurrency": (),
        "output": "EmptySentinel",
    },
    "run-cleanup": {
        "retries": 0,
        "cancel": (),
        "concurrency": (),
        "output": "RunCleanupResult",
    },
    "sandbox-cleanup-on-completed": {
        "retries": 1,
        "cancel": RUN_CANCEL,
        "concurrency": (),
        "output": "EmptySentinel",
    },
    "sandbox-cleanup-on-failed": {
        "retries": 1,
        "cancel": RUN_CANCEL,
        "concurrency": (),
        "output": "EmptySentinel",
    },
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
                    keyword.value for keyword in decorator.keywords if keyword.arg == "trigger"
                )
                assert isinstance(trigger, ast.Call)
                event = _literal_keyword(trigger, "event")
                registered[str(fn_id)] = str(event)

    assert registered == EXPECTED_FUNCTION_TRIGGERS


def test_all_functions_membership_order_and_metadata_stay_stable() -> None:
    from ergon_core.core.infrastructure.inngest.registry import ALL_FUNCTIONS

    assert [fn.local_id for fn in ALL_FUNCTIONS] == EXPECTED_FUNCTION_ORDER

    metadata = {}
    for fn in ALL_FUNCTIONS:
        opts = fn._opts
        cancel = tuple((item.event, item.if_exp) for item in (opts.cancel or ()))
        concurrency = tuple(item.limit for item in (opts.concurrency or ()))
        output_type = fn._output_type
        metadata[fn.local_id] = {
            "retries": opts.retries,
            "cancel": cancel,
            "concurrency": concurrency,
            "output": getattr(output_type, "__name__", repr(output_type)),
        }

    assert metadata == EXPECTED_FUNCTION_METADATA


def test_registry_imports_job_local_inngest_modules_only() -> None:
    text = REGISTRY.read_text()

    assert "ergon_core.core.infrastructure.inngest" + ".handlers" not in text
    assert "ergon_core.core.application" + ".jobs" not in text
    assert "ergon_core.core.jobs" in text
