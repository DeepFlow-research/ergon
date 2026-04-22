"""MiniF2F criterion reads proof via CriterionRuntime, not WorkerOutput.artifacts.

The pre-RFC-2026-04-22 path read ``worker_result.artifacts["final_solution.lean"]``,
which is dead code after the Inngest ``worker_execute`` boundary drops
``artifacts``. The criterion now reads the published ``final_solution.lean``
run-resource via ``context.runtime.read_resource``.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.minif2f.rules.proof_verification import (
    ProofVerificationCriterion,
)
from ergon_core.api import WorkerOutput
from ergon_core.api.criterion_runtime import CommandResult
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.task_types import BenchmarkTask


def _make_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_slug="t1",
        instance_key="default",
        description="theorem t : True := by trivial",
        task_payload={},
    )


@pytest.mark.asyncio
async def test_reads_proof_via_runtime_read_resource() -> None:
    """The criterion must call runtime.read_resource('final_solution.lean')."""
    runtime = MagicMock()
    runtime.read_resource = AsyncMock(return_value=b"theorem t : True := by trivial")
    runtime.write_file = AsyncMock()
    runtime.run_command = AsyncMock(
        return_value=CommandResult(stdout="[ok]", stderr="", exit_code=0)
    )

    context = EvaluationContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        task=_make_task(),
        worker_result=WorkerOutput(output="irrelevant", success=True),
        sandbox_id="sbx-abc",
        metadata={"runtime": runtime},
        runtime=runtime,
    )

    criterion = ProofVerificationCriterion()
    result = await criterion.evaluate(context)

    runtime.read_resource.assert_awaited_once_with("final_solution.lean")
    # Smoke: result is a well-formed CriterionResult.
    assert result.name
    # The criterion did NOT touch worker_result.artifacts.
    assert context.worker_result.artifacts == {}


@pytest.mark.asyncio
async def test_scores_zero_when_proof_missing() -> None:
    """When read_resource raises ResourceNotFoundError the score is 0."""
    # reason: lazy import mirrors the criterion's own lazy import of this
    # core-internal exception so tests don't pin it at module scope.
    from ergon_core.core.runtime.evaluation.criterion_runtime import (
        ResourceNotFoundError,
    )

    runtime = MagicMock()
    runtime.read_resource = AsyncMock(side_effect=ResourceNotFoundError("missing"))

    context = EvaluationContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        task=_make_task(),
        worker_result=WorkerOutput(output="irrelevant", success=True),
        sandbox_id="sbx-abc",
        metadata={"runtime": runtime},
        runtime=runtime,
    )

    criterion = ProofVerificationCriterion()
    result = await criterion.evaluate(context)
    assert result.score == 0.0
    assert not result.passed
