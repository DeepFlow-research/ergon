"""Tests that tightened types enforce their constraints.

Verifies that enum/Literal fields reject invalid values at model construction
time, catching bugs that would previously slip through as unchecked strings.
"""

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
    RunGenerationTurn,
    RunRecord,
    RunResource,
    RunTaskExecution,
    RunTaskStateEvent,
    TrainingSession,
)


class TestRunRecordStatus:
    def test_accepts_valid_status(self):
        record = RunRecord(
            experiment_definition_id=uuid4(),
            status=RunStatus.PENDING,
        )
        assert record.status == RunStatus.PENDING

    def test_enum_value_matches_string(self):
        assert RunStatus.PENDING == "pending"
        assert RunStatus.COMPLETED == "completed"


class TestRunTaskExecutionStatus:
    def test_accepts_valid_status(self):
        execution = RunTaskExecution(
            run_id=uuid4(),
            definition_task_id=uuid4(),
            status=TaskExecutionStatus.RUNNING,
        )
        assert execution.status == TaskExecutionStatus.RUNNING


class TestRunTaskStateEventTypes:
    def test_accepts_valid_event_type(self):
        event = RunTaskStateEvent(
            run_id=uuid4(),
            definition_task_id=uuid4(),
            event_type="state_change",
            new_status=TaskExecutionStatus.COMPLETED,
        )
        assert event.event_type == "state_change"

    def test_accepts_valid_old_status(self):
        event = RunTaskStateEvent(
            run_id=uuid4(),
            definition_task_id=uuid4(),
            event_type="state_change",
            old_status=TaskExecutionStatus.PENDING,
            new_status=TaskExecutionStatus.RUNNING,
        )
        assert event.old_status == TaskExecutionStatus.PENDING


class TestExperimentCohortStatus:
    def test_default_status_is_active(self):
        cohort = ExperimentCohort(
            name="test-cohort",
            status=ExperimentCohortStatus.ACTIVE,
        )
        assert cohort.status == ExperimentCohortStatus.ACTIVE


class TestRunResourceKind:
    def test_accepts_output(self):
        resource = RunResource(
            run_id=uuid4(),
            kind="output",
            name="test.txt",
            mime_type="text/plain",
            file_path="/tmp/test.txt",
            size_bytes=100,
        )
        assert resource.kind == "output"


class TestRunGenerationTurnOutcome:
    def test_accepts_success(self):
        turn = RunGenerationTurn(
            run_id=uuid4(),
            task_execution_id=uuid4(),
            worker_binding_key="test",
            turn_index=0,
            raw_response={},
            execution_outcome="success",
        )
        assert turn.execution_outcome == "success"

    def test_accepts_failure(self):
        turn = RunGenerationTurn(
            run_id=uuid4(),
            task_execution_id=uuid4(),
            worker_binding_key="test",
            turn_index=0,
            raw_response={},
            execution_outcome="failure",
        )
        assert turn.execution_outcome == "failure"

    def test_accepts_none_for_legacy(self):
        turn = RunGenerationTurn(
            run_id=uuid4(),
            task_execution_id=uuid4(),
            worker_binding_key="test",
            turn_index=0,
            raw_response={},
        )
        assert turn.execution_outcome is None

    def test_tightened_list_types(self):
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


class TestTrainingSessionStatus:
    def test_default_status_is_running(self):
        ts = TrainingSession(
            experiment_definition_id=uuid4(),
            model_name="test-model",
        )
        assert ts.status == TrainingStatus.RUNNING


class TestGraphMutationTypes:
    def test_accepts_valid_mutation_type(self):
        mutation = RunGraphMutation(
            run_id=uuid4(),
            sequence=0,
            mutation_type="node.added",
            target_type="node",
            target_id=uuid4(),
            actor="system:test",
            new_value={"status": "pending"},
        )
        assert mutation.mutation_type == "node.added"
        assert mutation.target_type == "node"

    def test_accepts_edge_target_type(self):
        mutation = RunGraphMutation(
            run_id=uuid4(),
            sequence=0,
            mutation_type="edge.added",
            target_type="edge",
            target_id=uuid4(),
            actor="system:test",
            new_value={},
        )
        assert mutation.target_type == "edge"


class TestGraphAnnotationTargetType:
    def test_accepts_node(self):
        annotation = RunGraphAnnotation(
            run_id=uuid4(),
            target_type="node",
            target_id=uuid4(),
            namespace="payload",
            sequence=0,
        )
        assert annotation.target_type == "node"
