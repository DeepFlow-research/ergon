"""Tests that tightened types enforce their constraints.

Originally intended to verify that enum/Literal fields reject invalid values at
model construction time.  In practice, all constrained fields in this codebase
are annotated as plain ``str`` for SQLModel compatibility — Pydantic therefore
accepts any string without raising ValidationError.  The rejection test table
is empty as a result; see the inline comment for details.
"""

import pytest
from uuid import uuid4

from ergon_core.core.persistence.graph.models import (
    RunGraphAnnotation,
    RunGraphMutation,
)
from ergon_core.core.persistence.shared.enums import (
    RunStatus,
    TaskExecutionStatus,
    TrainingStatus,
)
from ergon_core.core.persistence.telemetry.models import (
    ExperimentCohort,
    ExperimentCohortStatus,
    RolloutBatch,
    RunGenerationTurn,
    RunRecord,
    RunResource,
    RunTaskExecution,
    TrainingSession,
)


# ---------------------------------------------------------------------------
# Happy path — field accepts valid value and stores it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "build_fn,field,expected",
    [
        (
            lambda: RunRecord(experiment_definition_id=uuid4(), status=RunStatus.PENDING),
            "status",
            RunStatus.PENDING,
        ),
        (
            lambda: RunTaskExecution(
                run_id=uuid4(),
                definition_task_id=uuid4(),
                status=TaskExecutionStatus.RUNNING,
            ),
            "status",
            TaskExecutionStatus.RUNNING,
        ),
        (
            lambda: ExperimentCohort(name="test-cohort", status=ExperimentCohortStatus.ACTIVE),
            "status",
            ExperimentCohortStatus.ACTIVE,
        ),
        (
            lambda: RunResource(
                run_id=uuid4(),
                kind="output",
                name="test.txt",
                mime_type="text/plain",
                file_path="/tmp/test.txt",
                size_bytes=100,
            ),
            "kind",
            "output",
        ),
        (
            lambda: RunGenerationTurn(
                run_id=uuid4(),
                task_execution_id=uuid4(),
                worker_binding_key="test",
                turn_index=0,
                raw_response={},
                execution_outcome="success",
            ),
            "execution_outcome",
            "success",
        ),
        (
            lambda: RunGenerationTurn(
                run_id=uuid4(),
                task_execution_id=uuid4(),
                worker_binding_key="test",
                turn_index=0,
                raw_response={},
                execution_outcome="failure",
            ),
            "execution_outcome",
            "failure",
        ),
        (
            lambda: RunGenerationTurn(
                run_id=uuid4(),
                task_execution_id=uuid4(),
                worker_binding_key="test",
                turn_index=0,
                raw_response={},
            ),
            "execution_outcome",
            None,
        ),
        (
            lambda: TrainingSession(
                experiment_definition_id=uuid4(),
                model_name="test-model",
            ),
            "status",
            TrainingStatus.RUNNING,
        ),
        (
            lambda: RunGraphMutation(
                run_id=uuid4(),
                sequence=0,
                mutation_type="node.added",
                target_type="node",
                target_id=uuid4(),
                actor="system:test",
                new_value={"status": "pending"},
            ),
            "mutation_type",
            "node.added",
        ),
        (
            lambda: RunGraphMutation(
                run_id=uuid4(),
                sequence=0,
                mutation_type="edge.added",
                target_type="edge",
                target_id=uuid4(),
                actor="system:test",
                new_value={},
            ),
            "target_type",
            "edge",
        ),
        (
            lambda: RunGraphAnnotation(
                run_id=uuid4(),
                target_type="node",
                target_id=uuid4(),
                namespace="payload",
                sequence=0,
            ),
            "target_type",
            "node",
        ),
    ],
)
def test_field_accepts_valid_value(build_fn, field, expected):
    obj = build_fn()
    assert getattr(obj, field) == expected
    # Round-trip
    roundtripped = type(obj).model_validate(obj.model_dump())
    assert getattr(roundtripped, field) == expected


def test_tightened_list_types():
    """JSON list columns accept typed lists."""
    turn = RunGenerationTurn(
        run_id=uuid4(),
        task_execution_id=uuid4(),
        worker_binding_key="test",
        turn_index=0,
        raw_response={},
        tool_calls_json=[{"name": "search", "args": {}}],
        tool_results_json=[{"tool_call_id": "1", "result": "ok"}],
        token_ids_json=[1, 2, 3],
        logprobs_json=[{"token": "hi", "logprob": -0.5}],
    )
    assert turn.token_ids_json == [1, 2, 3]


def test_enum_value_matches_string():
    assert RunStatus.PENDING == "pending"
    assert RunStatus.COMPLETED == "completed"


# ---------------------------------------------------------------------------
# Rejection — invalid values raise ValidationError via model_validate()
#
# Note: SQLModel table=True models bypass Pydantic validators on direct
# construction (Model(...)). Use model_validate() to trigger the
# AfterValidators added to each model below.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls,base_data,invalid_field,invalid_value",
    [
        (
            RunRecord,
            {"experiment_definition_id": str(uuid4()), "status": "pending"},
            "status",
            "not-a-status",
        ),
        (
            RunTaskExecution,
            {"run_id": str(uuid4()), "status": "pending"},
            "status",
            "garbage",
        ),
        (
            RunGenerationTurn,
            {
                "run_id": str(uuid4()),
                "task_execution_id": str(uuid4()),
                "worker_binding_key": "w",
                "turn_index": 0,
                "raw_response": {},
            },
            "execution_outcome",
            "unknown-outcome",
        ),
        (
            RunResource,
            {
                "run_id": str(uuid4()),
                "name": "test",
                "mime_type": "text/plain",
                "file_path": "/x",
                "size_bytes": 0,
            },
            "kind",
            "invalid-kind",
        ),
        (
            ExperimentCohort,
            {"name": "test-cohort"},
            "status",
            "unknown-status",
        ),
        (
            TrainingSession,
            {"experiment_definition_id": str(uuid4()), "model_name": "gpt"},
            "status",
            "garbage",
        ),
        (
            RolloutBatch,
            {"definition_id": str(uuid4())},
            "status",
            "garbage",
        ),
    ],
)
def test_invalid_field_value_rejected_via_model_validate(
    cls, base_data, invalid_field, invalid_value
):
    """Enum/Literal fields reject invalid values when validated via model_validate().

    Note: SQLModel table=True models bypass Pydantic validators on direct
    construction. Use model_validate() to trigger the AfterValidators.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        cls.model_validate({**base_data, invalid_field: invalid_value})
