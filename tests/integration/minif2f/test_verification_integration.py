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
from pathlib import Path
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
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    ExperimentRecord,
    RunRecord,
    RunTaskExecution,
)
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager
from ergon_core.core.providers.sandbox.resource_publisher import SandboxResourcePublisher
from ergon_core.core.runtime.evaluation.criterion_runtime import (
    DefaultCriterionRuntime,
)
from ergon_core.core.runtime.evaluation.evaluation_schemas import CriterionContext

_FIXTURE_PROOF = Path(__file__).parents[2] / "fixtures" / "minif2f" / "known_good_proof.lean"


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
    ctx = CriterionContext(
        run_id=run_id,
        task_input="test task",
        agent_reasoning="test output",
    )
    return DefaultCriterionRuntime(context=ctx, sandbox_manager=sandbox_manager)


async def _publish_fixture_proof(
    runtime: DefaultCriterionRuntime,
    sandbox_manager: MiniF2FSandboxManager,
    *,
    run_id,
    task_execution_id,
    blob_root: Path,
) -> None:
    await runtime.run_command("mkdir -p /workspace/final_output")
    await runtime.write_file(
        "/workspace/final_output/final_solution.lean",
        _FIXTURE_PROOF.read_bytes(),
    )
    sandbox = sandbox_manager.get_sandbox(run_id)
    assert sandbox is not None
    publisher = SandboxResourcePublisher(
        sandbox=sandbox,
        run_id=run_id,
        task_execution_id=task_execution_id,
        blob_root=blob_root,
    )
    await publisher.sync()


def _seed_run_record(run_id, task_execution_id) -> None:
    with get_session() as session:
        definition = ExperimentDefinition(benchmark_type="minif2f")
        session.add(definition)
        session.flush()
        experiment = ExperimentRecord(
            name="minif2f verification fixture",
            benchmark_type="minif2f",
            sample_count=1,
            sample_selection_json={"instance_keys": ["default"]},
            default_worker_team_json={"primary": "minif2f-react"},
            design_json={},
            metadata_json={},
            status="running",
        )
        session.add(experiment)
        session.flush()
        run = RunRecord(
            id=run_id,
            experiment_id=experiment.id,
            workflow_definition_id=definition.id,
            benchmark_type="minif2f",
            instance_key="default",
            worker_team_json={"primary": "minif2f-react"},
            status=RunStatus.EXECUTING,
        )
        session.add(run)
        session.flush()
        node = RunGraphNode(
            run_id=run_id,
            instance_key="default",
            task_slug="mathd_algebra_176",
            description=_make_task().description,
            status="completed",
            assigned_worker_slug="minif2f-react",
            level=0,
        )
        session.add(node)
        session.flush()
        execution = RunTaskExecution(
            id=task_execution_id,
            run_id=run_id,
            node_id=node.id,
            status=TaskExecutionStatus.COMPLETED,
            final_assistant_message="fixture proof written",
        )
        session.add(execution)
        session.commit()


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(600)  # template pull + first mathlib import can be slow
async def test_fixture_proof_verifies_to_score_1(tmp_path: Path) -> None:
    _require_setup()

    run_id = uuid4()
    task_execution_id = uuid4()
    _seed_run_record(run_id, task_execution_id)

    mgr = MiniF2FSandboxManager()
    runtime = await _setup_runtime(mgr, run_id)
    try:
        worker_output = WorkerOutput(
            output="",
            success=True,
        )
        await _publish_fixture_proof(
            runtime,
            mgr,
            run_id=run_id,
            task_execution_id=task_execution_id,
            blob_root=tmp_path / "blob",
        )
        eval_ctx = EvaluationContext(
            run_id=run_id,
            task_id=uuid4(),
            execution_id=task_execution_id,
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
