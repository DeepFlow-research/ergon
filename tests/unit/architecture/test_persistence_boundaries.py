"""Architecture guards for persistence boundaries."""

from pathlib import Path


FORBIDDEN_PATTERNS = (
    "get_session(",
    "session.exec(",
    "session.get(",
    "select(",
)

ALLOWLIST = {
    # Test harness endpoints are explicitly debug/dev-only and expose raw state
    # for rollout inspection. They should remain isolated behind settings gates.
    Path("ergon_core/ergon_core/core/api/test_harness.py"),
    # Context events are streamed from the Inngest worker as each model turn
    # lands; this legacy path is intentionally deferred until the context
    # event repository owns its transaction boundary.
    Path("ergon_core/ergon_core/core/runtime/inngest/worker_execute.py"),
    # Legacy workflow lifecycle functions still own small transactional updates.
    # New Inngest functions should use repositories/services instead.
    Path("ergon_core/ergon_core/core/runtime/inngest/start_workflow.py"),
    Path("ergon_core/ergon_core/core/runtime/inngest/run_cleanup.py"),
    Path("ergon_core/ergon_core/core/runtime/inngest/cleanup_cancelled_task.py"),
    Path("ergon_core/ergon_core/core/runtime/inngest/cancel_orphan_subtasks.py"),
    Path("ergon_core/ergon_core/core/runtime/inngest/complete_workflow.py"),
    Path("ergon_core/ergon_core/core/runtime/inngest/sandbox_setup.py"),
    Path("ergon_core/ergon_core/core/runtime/inngest/fail_workflow.py"),
}

CHECKED_ROOTS = (
    Path("ergon_core/ergon_core/core/api"),
    Path("ergon_core/ergon_core/core/dashboard"),
    Path("ergon_core/ergon_core/core/runtime/inngest"),
)


def test_db_access_stays_out_of_api_dashboard_and_inngest_layers() -> None:
    offenders: list[str] = []
    for root in CHECKED_ROOTS:
        for path in root.rglob("*.py"):
            if path in ALLOWLIST:
                continue
            text = path.read_text()
            matches = [pattern for pattern in FORBIDDEN_PATTERNS if pattern in text]
            if matches:
                offenders.append(f"{path}: {', '.join(matches)}")

    assert offenders == []
