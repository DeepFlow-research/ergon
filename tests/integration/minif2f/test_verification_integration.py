"""Fixture-proof integration test for the MiniF2F verification pipeline.

No model involvement — this test exists to isolate the
sandbox → ProofVerificationCriterion path so that bugs in the Lean
invocation, sandbox mounting, or criterion plumbing surface *before*
we pay for a real model run.

Skipped when ``E2B_API_KEY`` is missing OR the minif2f template hasn't
been registered (i.e. nobody has run ``ergon benchmark setup minif2f``
on this machine).
"""

import json
import os
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.minif2f.rules.proof_verification import (
    ProofVerificationCriterion,
)
from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.benchmarks.minif2f.sandbox.utils import REGISTRY_PATH
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import WorkerOutput
from ergon_core.api.task_types import BenchmarkTask, EmptyTaskPayload
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager
from ergon_core.core.runtime.evaluation.criterion_runtime import (
    DefaultCriterionRuntime,
)
from ergon_core.core.runtime.evaluation.evaluation_schemas import CriterionContext


def _require_setup() -> None:
    if not os.environ.get("E2B_API_KEY"):
        pytest.skip("E2B_API_KEY not set — skipping live sandbox test")
    if not REGISTRY_PATH.exists():
        pytest.skip(f"{REGISTRY_PATH} missing — run `ergon benchmark setup minif2f` first")
    try:
        with REGISTRY_PATH.open() as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        pytest.skip(f"{REGISTRY_PATH} unreadable — rerun setup")
    if "minif2f" not in data:
        pytest.skip("minif2f template not registered — run `ergon benchmark setup minif2f`")


@pytest.fixture(autouse=True)
def _reset_sandbox_singleton():
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}
    BaseSandboxManager._file_registries = {}
    BaseSandboxManager._created_files_registry = {}
    yield
    BaseSandboxManager._instance = None
    BaseSandboxManager._sandboxes = {}


def _make_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_slug="mathd_algebra_176",
        instance_key="default",
        description=("theorem mathd_algebra_176 (x : ℝ) : (x + 1) ^ 2 * x = x ^ 3 + 2 * x ^ 2 + x"),
        evaluator_binding_keys=("default",),
        task_payload=EmptyTaskPayload(),
    )


async def _setup_runtime(
    sandbox_manager: MiniF2FSandboxManager,
    run_id,
) -> DefaultCriterionRuntime:
    """Spin up a sandbox and wrap it in a DefaultCriterionRuntime."""
    # Use run_id as the sandbox_key so get_sandbox(run_id) works.
    await sandbox_manager.create(
        sandbox_key=run_id,
        run_id=run_id,
        timeout_minutes=10,
    )
    ctx = CriterionContext(run_id=run_id)
    return DefaultCriterionRuntime(context=ctx, sandbox_manager=sandbox_manager)


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(600)  # template pull + first mathlib import can be slow
async def test_fixture_proof_verifies_to_score_1() -> None:
    _require_setup()

    run_id = uuid4()

    mgr = MiniF2FSandboxManager()
    runtime = await _setup_runtime(mgr, run_id)
    try:
        worker_output = WorkerOutput(
            output="",
            success=True,
        )
        eval_ctx = EvaluationContext(
            run_id=run_id,
            task_id=uuid4(),
            execution_id=uuid4(),
            task=_make_task(),
            worker_result=worker_output,
            sandbox_id=mgr.get_sandbox(run_id).sandbox_id,  # type: ignore[union-attr]
            metadata={"runtime": runtime},
            runtime=runtime,
        )

        criterion = ProofVerificationCriterion(
            name="proof_verification",
            weight=1.0,
            max_score=1.0,
        )
        result = await criterion.evaluate(eval_ctx)

        assert result.score == 1.0, f"Fixture proof failed to verify. Feedback: {result.feedback!r}"
        assert result.passed is True
    finally:
        await mgr.terminate(run_id)
