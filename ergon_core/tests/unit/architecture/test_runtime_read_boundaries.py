"""PR 3 textual guards: the worker_execute job body must read only
from the run tier, never from definition tables.

After PR 3, `worker_execute.py` goes through `graph_repo.node(...)` to
get a typed Task; the legacy DefinitionRepository / ExperimentDefinitionTask
imports are gone. PR 11 deletes the legacy prep methods entirely.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_worker_execute_does_not_read_definition_repository() -> None:
    """`worker_execute.py` body must not import definition-tier
    symbols. PR 11's textual guard for the broader runtime is the
    final-state ledger's `worker_execute_imports_only_run_tier` check;
    this guard is the per-PR version that PR 3 flips green."""

    text = (ROOT / "ergon_core/ergon_core/core/application/jobs/worker_execute.py").read_text()
    assert "DefinitionRepository" not in text, (
        "worker_execute imports DefinitionRepository; the run-tier read "
        "boundary (Δ.2) forbids this."
    )
    assert "task_with_instance" not in text, (
        "worker_execute calls task_with_instance; the run-tier read "
        "boundary forbids definition-tier reads."
    )
    assert "ExperimentDefinitionTask" not in text, (
        "worker_execute imports ExperimentDefinitionTask; the run-tier "
        "read boundary forbids definition-tier reads."
    )


def test_worker_execute_uses_object_bound_worker() -> None:
    """PR 5 retires the v1 worker-from-registry bridge.

    The body must read the worker directly off ``task.worker`` (the
    PR 5 object-bound field) — not via ``ComponentCatalogService`` or
    the old ``_worker_from_payload_bridge`` helper. If either name
    creeps back into the job body, the run-tier read boundary that
    PR 3 set up has regressed.
    """

    text = (ROOT / "ergon_core/ergon_core/core/application/jobs/worker_execute.py").read_text()
    assert "ComponentCatalogService" not in text, (
        "worker_execute must read worker from `task.worker` only — "
        "ComponentCatalogService imports recreate the registry-driven "
        "runtime that PR 5 removed."
    )
    assert "_worker_from_payload_bridge" not in text, "PR 5 deletes the PR 3 worker payload bridge."
    assert "task.worker" in text, (
        "PR 5 binds the worker directly to the Task snapshot; "
        "worker_execute must read it off `task.worker`."
    )


def test_evaluate_task_run_uses_thin_payload_and_run_tier_read() -> None:
    """PR 4 textual guard: the `evaluate_task_run.py` body reads only
    from the run tier and only via the thin id-only payload."""

    body = (ROOT / "ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py").read_text()

    # Thin payload only.
    assert "TaskEvaluateRequest" in body
    assert "EvaluateTaskRunRequest" not in body, (
        "PR 4 retires the legacy multi-field payload from the eval body; "
        "the import shim still exists in models.py for back-compat."
    )

    # No definition-tier reads.
    assert "DefinitionRepository" not in body, (
        "evaluate_task_run must not load definition rows directly — "
        "definition reads belong in EvaluationService.lookup_evaluator_id."
    )
    assert "ExperimentDefinitionTask" not in body
    # No registry-based evaluator resolution inside the body.
    assert "ComponentCatalogService" not in body

    # Uses the same run-tier loader the orchestrator uses.
    assert "WorkflowGraphRepository" in body
    assert ".node(" in body


def test_evaluate_task_run_uses_object_bound_evaluators() -> None:
    """PR 5: the eval body dispatches on ``task.evaluators[index]``.

    Retires the PR 4 ``_evaluator_bridge`` (was a sibling module
    owning the multi-hop binding-key → ExperimentDefinitionEvaluator
    → ComponentCatalogService lookup chain). PR 5's object-bound Task
    snapshot carries Evaluator instances inline.
    """

    import ergon_core.core.application.jobs as jobs_pkg
    from pathlib import Path

    body = (ROOT / "ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py").read_text()
    assert "task.evaluators[" in body, (
        "PR 5 binds evaluators directly to the Task; the eval worker "
        "must dispatch on task.evaluators[index]."
    )
    # Bridge module is gone.
    jobs_dir = Path(jobs_pkg.__file__).parent
    assert not (jobs_dir / "_evaluator_bridge.py").exists(), (
        "PR 5 deletes the PR 4 evaluator-resolution bridge module."
    )


def test_evaluate_task_run_detaches_sandbox() -> None:
    """PR 5: the eval body releases the local sandbox handle on the
    way out so the gRPC stream / TCP connection doesn't leak. The
    external sandbox stays running — the orchestrator (`execute_task`)
    owns termination.
    """

    body = (ROOT / "ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py").read_text()
    assert "task.sandbox.detach()" in body, (
        "PR 5 wires Sandbox.detach() into the eval body's finally so "
        "the local runtime handle is always released."
    )


def test_execute_task_fans_out_via_step_invoke() -> None:
    """PR 4 textual guard: the orchestrator fans out evaluators
    synchronously via ``ctx.step.invoke`` + ``asyncio.gather`` and
    bounds sandbox lifetime via ``try/finally``.

    Note: the plan code originally placed this logic in
    `worker_execute.py`; in our codebase `execute_task.py` is the
    orchestrator (it invokes sandbox_setup, worker_execute, and
    persist_outputs as siblings). See PR 4 plan § "Implementation
    Note — Bridge-Everything Approach" for the location rationale.
    """

    body = (ROOT / "ergon_core/ergon_core/core/application/jobs/execute_task.py").read_text()
    assert "ctx.step.invoke" in body
    assert "evaluate_task_run_function" in body
    assert "ctx.group.parallel" in body, (
        "Use Inngest-native `ctx.group.parallel` for the fan-out, not "
        "`asyncio.gather` over `step.invoke` coroutines."
    )
    assert "finally:" in body
    assert "terminate_sandbox_by_id" in body, (
        "sandbox termination must live inside the orchestrator now; PR 11 "
        "removes the helper entirely once a `lifecycle_hub.release` "
        "replacement lands."
    )
