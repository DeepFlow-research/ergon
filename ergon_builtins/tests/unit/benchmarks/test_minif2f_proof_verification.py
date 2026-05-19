"""MiniF2F criterion reads proof via the object-bound sandbox.

The criterion reads ``/workspace/final_output/final_solution.lean`` from
``context.task.sandbox``. The old criterion-runtime bridge was removed in
PR 11.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from ergon_builtins.benchmarks.minif2f.rules.proof_verification import (
    ProofVerificationCriterion,
)
from ergon_core.api import WorkerOutput
from ergon_core.api.criterion import CriterionContext
from ergon_core.api.benchmark import EmptyTaskPayload, Task
from ergon_core.api.sandbox.runtime import CommandResult
from ergon_core.test_support.task_factory import task_with_id


def _make_task(sandbox: MagicMock | None = None) -> Task:
    task = task_with_id(
        uuid4(),
        task_slug="t1",
        instance_key="default",
        description="theorem t : True := by trivial",
        task_payload=EmptyTaskPayload(),
    )
    if sandbox is not None:
        task.sandbox = sandbox
    return task


@pytest.mark.asyncio
async def test_reads_proof_via_task_sandbox() -> None:
    """The criterion must read the final solution from the task sandbox."""
    sandbox = MagicMock()
    sandbox.read_file = AsyncMock(return_value=b"theorem t : True := by trivial")
    sandbox.write_file = AsyncMock()
    sandbox.run_command = AsyncMock(
        return_value=CommandResult(stdout="[ok]", stderr="", exit_code=0)
    )
    sandbox.is_live = True

    context = CriterionContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        task=_make_task(sandbox),
        worker_result=WorkerOutput(output="irrelevant", success=True),
    )

    criterion = ProofVerificationCriterion()
    result = await criterion.evaluate(context)

    sandbox.read_file.assert_awaited_once_with("/workspace/final_output/final_solution.lean")
    assert result.name == "proof_verification"
    assert result.score == 1.0
    assert result.passed is True
    assert result.feedback == "Proof successfully verified by Lean compiler."


@pytest.mark.asyncio
async def test_scores_zero_when_proof_missing() -> None:
    """When sandbox.read_file raises OSError the score is 0."""
    sandbox = MagicMock()
    sandbox.read_file = AsyncMock(side_effect=OSError("missing"))

    context = CriterionContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        task=_make_task(sandbox),
        worker_result=WorkerOutput(output="irrelevant", success=True),
    )

    criterion = ProofVerificationCriterion()
    result = await criterion.evaluate(context)
    assert result.score == 0.0
    assert not result.passed
    assert "final_solution.lean" in result.feedback
