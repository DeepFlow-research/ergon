"""PR 3 textual guards: the worker_execute job body must read only
from the run tier, never from definition tables.

`worker_execute.py` goes through `graph_repo.node(...)` to get a typed
Task; definition-tier imports stay out of the runtime job body.
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


def test_worker_execute_prefers_task_worker_over_legacy_bridge() -> None:
    """PR 5 makes ``task.worker`` the canonical source.

    The body must read the worker off ``task.worker`` first. A narrow
    legacy fallback lives in a sibling module
    (``_legacy_worker_bridge.py``) and only fires when
    ``task.worker is None`` — i.e. when an unmigrated TaskSpec-returning
    benchmark reaches this path. The body must NOT import
    ``ComponentCatalogService`` directly or define an in-body
    ``_worker_from_payload_bridge`` function; both belong in the
    sibling. PR 11 (after PR 10c migrates the last benchmark) deletes
    the sibling module and the ``if worker is None:`` branch.
    """

    text = (ROOT / "ergon_core/ergon_core/core/application/jobs/worker_execute.py").read_text()
    assert "ComponentCatalogService" not in text, (
        "worker_execute body must not import the registry directly — "
        "any legacy fallback lives in `_legacy_worker_bridge.py`."
    )
    # The PR 3 in-body bridge name is gone; the PR 5 legacy fallback is
    # a sibling-module function and must not appear as a module-level
    # def here.
    assert "def _worker_from_payload_bridge" not in text, (
        "PR 5 retired the in-body bridge. The legacy fallback lives in a "
        "sibling module, not as a top-level def in `worker_execute.py`."
    )
    assert "task.worker" in text, (
        "PR 5 binds the worker directly to the Task snapshot; "
        "`worker_execute` must read it off `task.worker`."
    )


def test_evaluate_task_run_uses_thin_payload_and_run_tier_read() -> None:
    """`evaluate_task_run.py` reads from the run tier via id-only payload."""

    body = (ROOT / "ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py").read_text()

    # Thin payload only.
    assert "TaskEvaluateRequest" in body
    assert "EvaluateTaskRunRequest" not in body, (
        "The legacy multi-field payload must stay out of the eval body."
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
    """The eval body dispatches on ``task.evaluators[index]``."""

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
        "The evaluator-resolution bridge module must stay deleted."
    )


def test_evaluate_task_run_detaches_sandbox() -> None:
    """The eval body releases its local sandbox handle on the way out."""

    body = (ROOT / "ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py").read_text()
    assert "task.sandbox.detach()" in body, (
        "PR 5 wires Sandbox.detach() into the eval body's finally so "
        "the local runtime handle is always released."
    )


def test_execute_task_fans_out_via_step_invoke() -> None:
    """PR 4 textual guard: the orchestrator fans out evaluators
    synchronously via ``ctx.step.invoke`` + ``ctx.group.parallel``.

    Note: the plan code originally placed this logic in
    `worker_execute.py`; in our codebase `execute_task.py` is the
    orchestrator (it invokes sandbox_setup, worker_execute, and
    persist_outputs as siblings). Sandbox termination is owned by the
    sibling sandbox_cleanup functions gated on terminal task events.
    """

    body = (ROOT / "ergon_core/ergon_core/core/application/jobs/execute_task.py").read_text()
    assert "ctx.step.invoke" in body
    assert "evaluate_task_run_function" in body
    assert "ctx.group.parallel" in body, (
        "Use Inngest-native `ctx.group.parallel` for the fan-out, not "
        "`asyncio.gather` over `step.invoke` coroutines."
    )
    assert "sandbox_cleanup" in body, (
        "sandbox termination must be delegated to the sibling cleanup "
        "functions, not an inline orchestrator finally block."
    )
