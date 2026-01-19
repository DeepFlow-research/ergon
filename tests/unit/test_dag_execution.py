"""
Unit tests for DAG execution flow.

These tests verify the structure and logic of the execute_task() function
and related DAG execution components without requiring actual Inngest/DB.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

import pytest

from h_arcane.core.task import Task, TaskStatus
from h_arcane.core.runner import ExecutionResult, TaskResult, execute_task, _wait_for_completion
from h_arcane.core._internal.db.models import RunStatus
from h_arcane.core._internal.task.registry import TaskRegistry
from h_arcane.core._internal.task.persistence import serialize_task_tree


# =============================================================================
# Mock Worker for Testing
# =============================================================================


class MockWorker:
    """Simple mock worker for testing."""

    def __init__(self, name: str = "mock_worker"):
        self.id = uuid4()
        self.name = name
        self.model = "gpt-4o"
        self.tools = []
        self.system_prompt = "You are a test worker."

    async def execute(self, task, context):
        pass


def make_task(name: str, worker: MockWorker, **kwargs) -> Task:
    """Helper to create tasks with auto-generated description for tests."""
    return Task(name=name, description=f"Test task: {name}", assigned_to=worker, **kwargs)


# =============================================================================
# ExecutionResult Tests
# =============================================================================


class TestExecutionResult:
    """Tests for ExecutionResult model."""

    def test_execution_result_defaults(self):
        """ExecutionResult has correct defaults."""

        result = ExecutionResult(success=True, status=TaskStatus.COMPLETED)

        assert result.success is True
        assert result.status == TaskStatus.COMPLETED
        assert result.outputs == []
        assert result.score is None
        assert result.task_results == {}
        assert result.error is None

    def test_execution_result_with_all_fields(self):
        """ExecutionResult accepts all fields."""

        run_id = uuid4()
        exp_id = uuid4()

        result = ExecutionResult(
            success=True,
            status=TaskStatus.COMPLETED,
            score=0.85,
            duration_seconds=10.5,
            run_id=run_id,
            experiment_id=exp_id,
        )

        assert result.score == 0.85
        assert result.duration_seconds == 10.5
        assert result.run_id == run_id
        assert result.experiment_id == exp_id


class TestTaskResult:
    """Tests for TaskResult model."""

    def test_task_result_required_fields(self):
        """TaskResult requires task_id, name, status."""

        task_id = uuid4()
        result = TaskResult(
            task_id=task_id,
            name="Test Task",
            status=TaskStatus.COMPLETED,
        )

        assert result.task_id == task_id
        assert result.name == "Test Task"
        assert result.status == TaskStatus.COMPLETED

    def test_task_result_optional_fields(self):
        """TaskResult optional fields have defaults."""

        result = TaskResult(
            task_id=uuid4(),
            name="Test",
            status=TaskStatus.COMPLETED,
        )

        assert result.score is None
        assert result.outputs == []
        assert result.error is None


# =============================================================================
# execute_task Tests
# =============================================================================


class TestExecuteTaskStructure:
    """Tests for execute_task() structure and validation."""

    @pytest.mark.asyncio
    @patch("h_arcane.core.runner.inngest_client")
    @patch("h_arcane.core.runner.persist_workflow")
    @patch("h_arcane.core.runner.TaskRegistry")
    @patch("h_arcane.core.runner.AgentRegistry")
    async def test_execute_task_creates_registry(
        self,
        mock_agent_registry,
        mock_task_registry,
        mock_persist_workflow,
        mock_inngest,
    ):
        """execute_task creates TaskRegistry from task."""

        worker = MockWorker()
        task = make_task("Test", worker)

        # Mock the registry
        mock_registry_instance = MagicMock()
        mock_task_registry.return_value = mock_registry_instance

        # Mock agent registry
        mock_agent_instance = MagicMock()
        mock_agent_registry.return_value = mock_agent_instance

        # Mock persist_workflow
        mock_experiment = MagicMock()
        mock_experiment.id = uuid4()
        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_persist_workflow.return_value = (mock_experiment, mock_run, {})

        # Mock inngest
        mock_inngest.send = AsyncMock()

        # Patch _wait_for_completion to return immediately
        with patch("h_arcane.core.runner._wait_for_completion") as mock_wait:
            mock_wait.return_value = ExecutionResult(
                success=True,
                status=TaskStatus.COMPLETED,
                run_id=mock_run.id,
                experiment_id=mock_experiment.id,
            )

            await execute_task(task, timeout_seconds=1)

        # Verify TaskRegistry was created
        mock_task_registry.assert_called_once_with(task)

    @pytest.mark.asyncio
    async def test_execute_task_handles_exception(self):
        """execute_task handles exceptions gracefully."""

        worker = MockWorker()
        task = make_task("Test", worker)

        # Patch TaskRegistry to raise an exception
        with patch("h_arcane.core.runner.TaskRegistry") as mock_registry:
            mock_registry.side_effect = ValueError("Invalid task tree")

            result = await execute_task(task)

        assert result.success is False
        assert result.status == TaskStatus.FAILED
        assert result.error is not None and "Invalid task tree" in result.error


# =============================================================================
# _wait_for_completion Tests
# =============================================================================


class TestWaitForCompletion:
    """Tests for _wait_for_completion() polling logic."""

    @pytest.mark.asyncio
    @patch("h_arcane.core.runner.queries")
    async def test_returns_on_completed_status(self, mock_queries):
        """Returns immediately when run is COMPLETED."""

        run_id = uuid4()
        exp_id = uuid4()

        # Mock a completed run
        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.status = RunStatus.COMPLETED
        mock_run.completed_at = datetime.now(timezone.utc)
        mock_run.output_resource_ids = []
        mock_run.final_score = 0.9
        mock_run.benchmark_specific_results = {}
        mock_run.total_cost_usd = 0.05
        mock_run.error_message = None
        mock_queries.runs.get.return_value = mock_run
        mock_queries.task_executions.get_by_run.return_value = []

        result = await _wait_for_completion(
            run_id=run_id,
            experiment_id=exp_id,
            timeout=10,
            started_at=datetime.now(timezone.utc),
        )

        assert result.success is True
        assert result.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    @patch("h_arcane.core.runner.queries")
    async def test_returns_on_failed_status(self, mock_queries):
        """Returns immediately when run is FAILED."""

        run_id = uuid4()
        exp_id = uuid4()

        # Mock a failed run
        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.status = RunStatus.FAILED
        mock_run.completed_at = datetime.now(timezone.utc)
        mock_run.output_resource_ids = []
        mock_run.final_score = None
        mock_run.benchmark_specific_results = {}
        mock_run.total_cost_usd = 0.0
        mock_run.error_message = "Task execution failed"
        mock_queries.runs.get.return_value = mock_run
        mock_queries.task_executions.get_by_run.return_value = []

        result = await _wait_for_completion(
            run_id=run_id,
            experiment_id=exp_id,
            timeout=10,
            started_at=datetime.now(timezone.utc),
        )

        assert result.success is False
        assert result.status == TaskStatus.FAILED
        assert result.error == "Task execution failed"

    @pytest.mark.asyncio
    @patch("h_arcane.core.runner.queries")
    @patch("h_arcane.core.runner.asyncio.sleep", new_callable=AsyncMock)
    async def test_times_out_when_not_terminal(self, mock_sleep, mock_queries):
        """Times out when run doesn't reach terminal state."""

        run_id = uuid4()
        exp_id = uuid4()

        # Mock a still-running run
        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.status = RunStatus.EXECUTING
        mock_queries.runs.get.return_value = mock_run

        result = await _wait_for_completion(
            run_id=run_id,
            experiment_id=exp_id,
            timeout=0.01,  # Very short timeout
            started_at=datetime.now(timezone.utc),
            poll_interval=0.001,
        )

        assert result.success is False
        assert result.error is not None and "timed out" in result.error.lower()

    @pytest.mark.asyncio
    @patch("h_arcane.core.runner.queries")
    async def test_handles_run_not_found(self, mock_queries):
        """Handles case when run is not found."""

        run_id = uuid4()
        exp_id = uuid4()

        mock_queries.runs.get.return_value = None

        result = await _wait_for_completion(
            run_id=run_id,
            experiment_id=exp_id,
            timeout=10,
            started_at=datetime.now(timezone.utc),
        )

        assert result.success is False
        assert result.error is not None and "not found" in result.error.lower()


# =============================================================================
# Integration Tests (without real Inngest)
# =============================================================================


class TestDAGStructure:
    """Tests for DAG structure validation."""

    def test_single_task_dag(self):
        """Single task creates valid DAG structure."""

        worker = MockWorker()
        task = make_task("Single", worker)

        registry = TaskRegistry(task)

        assert len(registry) == 1
        assert registry.root_id == task.id
        ready = registry.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == task.id

    def test_linear_dag(self):
        """Linear A -> B -> C creates valid DAG."""

        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        c = make_task("C", worker, depends_on=[b])
        root = make_task("Root", worker, children=[a, b, c])

        registry = TaskRegistry(root)

        assert len(registry) == 4  # root + 3 children

        # Only A should be ready initially
        ready = registry.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].name == "A"

    def test_diamond_dag(self):
        """Diamond A -> (B, C) -> D creates valid DAG."""

        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        c = make_task("C", worker, depends_on=[a])
        d = make_task("D", worker, depends_on=[b, c])
        root = make_task("Root", worker, children=[a, b, c, d])

        registry = TaskRegistry(root)

        assert len(registry) == 5

        # Only A should be ready initially
        ready = registry.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].name == "A"

        # B and C depend on A
        dependents = registry.get_dependents(a.id)
        dependent_names = {t.name for t in dependents}
        assert dependent_names == {"B", "C"}


class TestPropagationIntegration:
    """Integration tests for propagation logic with mock queries."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_extract_dependencies(self, mock_queries):
        """Extract dependencies from task tree."""

        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])

        # Serialize the task tree

        root = make_task("Root", worker, children=[a, b])
        TaskRegistry(root)
        tree = serialize_task_tree(root)

        # Use schema method directly
        dependencies = tree.extract_dependencies()

        # B depends on A
        assert len(dependencies) == 1
        dep_b_id, dep_a_id = dependencies[0]
        assert dep_b_id == str(b.id)
        assert dep_a_id == str(a.id)
