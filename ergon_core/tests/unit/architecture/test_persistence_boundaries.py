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
    Path("ergon_core/ergon_core/core/rest_api/test_harness.py"),
    # Context events are streamed from the application job as each model turn
    # lands; this older path is intentionally deferred until the context
    # event repository owns its transaction boundary.
    Path("ergon_core/ergon_core/core/application/jobs/worker_execute.py"),
    # Workflow lifecycle jobs still own small transactional updates.
    # New jobs should use repositories/services instead.
    Path("ergon_core/ergon_core/core/application/jobs/start_workflow.py"),
    Path("ergon_core/ergon_core/core/application/jobs/run_cleanup.py"),
    Path("ergon_core/ergon_core/core/application/jobs/cleanup_cancelled_task.py"),
    Path("ergon_core/ergon_core/core/application/jobs/cancel_orphan_subtasks.py"),
    Path("ergon_core/ergon_core/core/application/jobs/complete_workflow.py"),
    Path("ergon_core/ergon_core/core/application/jobs/sandbox_setup.py"),
    Path("ergon_core/ergon_core/core/application/jobs/fail_workflow.py"),
}

CHECKED_ROOTS = (
    Path("ergon_core/ergon_core/core/rest_api"),
    Path("ergon_core/ergon_core/core/infrastructure/dashboard"),
    Path("ergon_core/ergon_core/core/infrastructure/inngest/handlers"),
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
