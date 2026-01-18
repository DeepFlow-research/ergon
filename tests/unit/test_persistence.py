"""Unit tests for the persistence layer."""

from pathlib import Path
from uuid import uuid4

import pytest

from h_arcane import Resource, Task
from h_arcane.core._internal.task.persistence import (
    compute_initial_task_states,
    create_experiment_from_task,
    create_resource_from_sdk,
    create_run_from_config,
    serialize_task_tree,
    create_output_resource_from_sdk,
)
from h_arcane.core._internal.task.registry import TaskRegistry
from h_arcane.benchmarks.enums import BenchmarkName


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
# serialize_task_tree Tests
# =============================================================================


class TestSerializeTaskTree:
    """Tests for serialize_task_tree()."""

    def test_serialize_single_task(self):
        """Serialize a single task to JSON."""
        worker = MockWorker()
        task = Task(
            name="Single Task",
            description="A single task",
            assigned_to=worker,
        )

        result = serialize_task_tree(task)

        assert result["id"] == str(task.id)
        assert result["name"] == "Single Task"
        assert result["description"] == "A single task"
        assert result["depends_on"] == []
        assert result["children"] == []
        assert result["is_leaf"] is True
        assert result["parent_id"] is None
        assert result["evaluator_type"] is None

    def test_serialize_task_with_children(self):
        """Serialize a task with children."""
        worker = MockWorker()
        child1 = make_task("Child 1", worker)
        child2 = make_task("Child 2", worker)
        parent = Task(
            name="Parent",
            description="Parent task",
            assigned_to=worker,
            children=[child1, child2],
        )

        result = serialize_task_tree(parent)

        assert result["name"] == "Parent"
        assert result["is_leaf"] is False
        assert len(result["children"]) == 2
        assert result["children"][0]["name"] == "Child 1"
        assert result["children"][1]["name"] == "Child 2"

    def test_serialize_task_with_dependencies(self):
        """Serialize a task with dependencies."""
        worker = MockWorker()
        dep1 = make_task("Dep 1", worker)
        dep2 = make_task("Dep 2", worker)
        task = make_task("Task", worker, depends_on=[dep1, dep2])
        root = make_task("Root", worker, children=[dep1, dep2, task])

        # Process through registry to resolve dependencies
        TaskRegistry(root)
        result = serialize_task_tree(task)

        assert len(result["depends_on"]) == 2
        assert str(dep1.id) in result["depends_on"]
        assert str(dep2.id) in result["depends_on"]

    def test_serialize_task_with_resources(self):
        """Serialize a task with resources."""
        worker = MockWorker()
        task = Task(
            name="Task",
            description="Task with resources",
            assigned_to=worker,
            resources=[
                Resource(name="File 1", path="/path/to/file1.txt"),
                Resource(name="File 2", content="inline content"),
            ],
        )

        result = serialize_task_tree(task)

        assert len(result["resources"]) == 2
        assert result["resources"][0]["name"] == "File 1"
        assert result["resources"][0]["path"] == "/path/to/file1.txt"
        assert result["resources"][1]["name"] == "File 2"
        assert result["resources"][1]["content"] == "inline content"

    def test_serialize_nested_tree(self):
        """Serialize a deeply nested task tree."""
        worker = MockWorker()

        # Build: root -> parent -> child
        child = make_task("Child", worker)
        parent = make_task("Parent", worker, children=[child])
        root = make_task("Root", worker, children=[parent])

        # Process through registry to set parent_ids
        TaskRegistry(root)
        result = serialize_task_tree(root)

        assert result["name"] == "Root"
        assert len(result["children"]) == 1
        assert result["children"][0]["name"] == "Parent"
        assert len(result["children"][0]["children"]) == 1
        assert result["children"][0]["children"][0]["name"] == "Child"


# =============================================================================
# compute_initial_task_states Tests
# =============================================================================


class TestComputeInitialTaskStates:
    """Tests for compute_initial_task_states()."""

    def test_single_task_is_ready(self):
        """Single leaf task with no deps should be READY."""
        worker = MockWorker()
        task = make_task("Task", worker)
        registry = TaskRegistry(task)

        states = compute_initial_task_states(registry)

        assert str(task.id) in states
        assert states[str(task.id)] == "ready"

    def test_task_with_deps_is_pending(self):
        """Task with dependencies should be PENDING."""
        worker = MockWorker()
        dep = make_task("Dep", worker)
        task = make_task("Task", worker, depends_on=[dep])
        root = make_task("Root", worker, children=[dep, task])

        registry = TaskRegistry(root)
        states = compute_initial_task_states(registry)

        assert states[str(dep.id)] == "ready"  # No deps
        assert states[str(task.id)] == "pending"  # Has deps

    def test_composite_task_is_pending(self):
        """Composite task (with children) should be PENDING."""
        worker = MockWorker()
        child = make_task("Child", worker)
        parent = make_task("Parent", worker, children=[child])

        registry = TaskRegistry(parent)
        states = compute_initial_task_states(registry)

        assert states[str(parent.id)] == "pending"
        assert states[str(child.id)] == "ready"


# =============================================================================
# create_experiment_from_task Tests
# =============================================================================


class TestCreateExperimentFromTask:
    """Tests for create_experiment_from_task()."""

    def test_creates_experiment_data(self):
        """Create experiment data from task."""
        worker = MockWorker()
        task = Task(
            name="Test Task",
            description="A test task description",
            assigned_to=worker,
        )
        registry = TaskRegistry(task)

        data = create_experiment_from_task(task, registry)

        assert data["task_id"] == str(task.id)
        assert data["task_description"] == "A test task description"
        assert data["root_task_id"] == str(task.id)
        assert "task_tree" in data
        assert data["task_tree"]["name"] == "Test Task"

    def test_creates_experiment_with_custom_benchmark(self):
        """Create experiment with custom benchmark name."""
        worker = MockWorker()
        task = make_task("Task", worker)
        registry = TaskRegistry(task)

        data = create_experiment_from_task(task, registry, benchmark_name="GDPEVAL")

        # Should parse benchmark name
        assert data["benchmark_name"] == BenchmarkName.GDPEVAL


# =============================================================================
# create_run_from_config Tests
# =============================================================================


class TestCreateRunFromConfig:
    """Tests for create_run_from_config()."""

    def test_creates_run_data(self):
        """Create run data from config."""
        worker = MockWorker()
        task = make_task("Task", worker)
        registry = TaskRegistry(task)
        experiment_id = uuid4()

        data = create_run_from_config(experiment_id, registry)

        assert data["experiment_id"] == experiment_id
        assert data["worker_model"] == "gpt-4o"
        assert data["max_questions"] == 10
        assert "task_states" in data
        assert str(task.id) in data["task_states"]

    def test_creates_run_with_custom_config(self):
        """Create run with custom configuration."""
        worker = MockWorker()
        task = make_task("Task", worker)
        registry = TaskRegistry(task)
        experiment_id = uuid4()

        data = create_run_from_config(
            experiment_id,
            registry,
            worker_model="gpt-4o-mini",
            max_questions=5,
        )

        assert data["worker_model"] == "gpt-4o-mini"
        assert data["max_questions"] == 5


# =============================================================================
# create_resource_from_sdk Tests
# =============================================================================


class TestCreateResourceFromSDK:
    """Tests for create_resource_from_sdk()."""

    def test_creates_resource_from_file_path(self, tmp_path):
        """Create resource from file path."""
        # Create a temporary file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        sdk_resource = Resource(name="Test File", path=str(test_file))
        experiment_id = uuid4()
        task_id = uuid4()

        data = create_resource_from_sdk(sdk_resource, experiment_id, task_id)

        assert data["experiment_id"] == experiment_id
        assert data["task_id"] == task_id
        assert data["is_input"] is True
        assert data["name"] == "Test File"
        assert data["mime_type"] == "text/plain"
        assert data["file_path"] == str(test_file.absolute())
        assert data["size_bytes"] == 13  # len("Hello, World!")

    def test_creates_resource_from_inline_content(self):
        """Create resource from inline content."""
        sdk_resource = Resource(name="Inline", content="Test content")
        experiment_id = uuid4()
        task_id = uuid4()

        data = create_resource_from_sdk(sdk_resource, experiment_id, task_id)

        assert data["experiment_id"] == experiment_id
        assert data["task_id"] == task_id
        assert data["is_input"] is True
        assert data["name"] == "Inline"
        assert data["size_bytes"] == len("Test content".encode("utf-8"))
        # File should have been created
        assert Path(data["file_path"]).exists()

    def test_creates_resource_from_url(self):
        """Create resource from URL."""
        sdk_resource = Resource(name="Remote", url="https://example.com/data.csv")
        experiment_id = uuid4()
        task_id = uuid4()

        data = create_resource_from_sdk(sdk_resource, experiment_id, task_id)

        assert data["experiment_id"] == experiment_id
        assert data["task_id"] == task_id
        assert data["is_input"] is True
        assert data["name"] == "Remote"
        assert data["file_path"] == "https://example.com/data.csv"
        assert data["size_bytes"] == 0  # Unknown until downloaded

    def test_raises_for_missing_file(self):
        """Raise error if file path doesn't exist."""
        sdk_resource = Resource(name="Missing", path="/nonexistent/file.txt")
        experiment_id = uuid4()
        task_id = uuid4()

        with pytest.raises(FileNotFoundError):
            create_resource_from_sdk(sdk_resource, experiment_id, task_id)

    def test_raises_for_empty_resource(self):
        """Raise error if resource has no path, content, or url."""
        sdk_resource = Resource(name="Empty")
        experiment_id = uuid4()
        task_id = uuid4()

        with pytest.raises(ValueError, match="must have path, content, or url"):
            create_resource_from_sdk(sdk_resource, experiment_id, task_id)


# =============================================================================
# Integration Tests (without DB)
# =============================================================================


class TestPersistenceIntegration:
    """Integration tests for the full persistence flow (without DB)."""

    def test_full_workflow_serialization(self, tmp_path):
        """Test full workflow can be serialized."""
        worker = MockWorker()

        # Create a test file
        test_file = tmp_path / "data.txt"
        test_file.write_text("Test data")

        # Create workflow
        task_a = Task(
            name="Task A",
            description="First task with resources",
            assigned_to=worker,
            resources=[Resource(name="Data", path=str(test_file))],
        )
        task_b = Task(
            name="Task B",
            description="Second task with dependency",
            assigned_to=worker,
            depends_on=[task_a],
        )
        workflow = Task(
            name="Workflow",
            description="Test workflow",
            assigned_to=worker,
            children=[task_a, task_b],
        )

        # Process
        registry = TaskRegistry(workflow)

        # Create experiment data
        exp_data = create_experiment_from_task(workflow, registry)
        assert exp_data["task_tree"]["name"] == "Workflow"
        assert len(exp_data["task_tree"]["children"]) == 2

        # Create run data
        exp_id = uuid4()
        run_data = create_run_from_config(exp_id, registry)
        assert len(run_data["task_states"]) == 3  # workflow + 2 children

        # Create resource data
        resource_data = create_resource_from_sdk(task_a.resources[0], exp_id, task_a.id)
        assert resource_data["name"] == "Data"


# =============================================================================
# Task Field Serializer Tests
# =============================================================================


class TestTaskFieldSerializers:
    """Tests for Task model field serializers."""

    def test_model_dump_serializes_worker(self):
        """model_dump() should serialize assigned_to worker."""
        worker = MockWorker("analyst")
        task = make_task("Test", worker)

        data = task.model_dump(mode="json")

        assert "assigned_to" in data
        assert data["assigned_to"]["id"] == str(worker.id)
        assert data["assigned_to"]["name"] == "analyst"
        assert data["assigned_to"]["type"] == "MockWorker"

    def test_model_dump_serializes_full_team(self):
        """model_dump() should serialize full_team."""
        worker1 = MockWorker("worker1")
        worker2 = MockWorker("worker2")
        task = Task(
            name="Team Task",
            description="Task with full team",
            assigned_to=worker1,
            full_team=[worker1, worker2],
        )

        data = task.model_dump(mode="json")

        assert data["full_team"] is not None
        assert len(data["full_team"]) == 2
        assert data["full_team"][0]["name"] == "worker1"
        assert data["full_team"][1]["name"] == "worker2"

    def test_model_dump_serializes_none_full_team(self):
        """model_dump() should handle None full_team."""
        worker = MockWorker()
        task = make_task("Test", worker)

        data = task.model_dump(mode="json")

        assert data["full_team"] is None

    def test_model_dump_serializes_depends_on(self):
        """model_dump() should serialize depends_on as UUIDs."""
        worker = MockWorker()
        dep1 = make_task("Dep 1", worker)
        dep2 = make_task("Dep 2", worker)
        task = make_task("Task", worker, depends_on=[dep1, dep2])

        data = task.model_dump(mode="json")

        assert len(data["depends_on"]) == 2
        assert data["depends_on"][0] == str(dep1.id)
        assert data["depends_on"][1] == str(dep2.id)

    def test_model_dump_serializes_mixed_depends_on(self):
        """model_dump() should handle mixed Task and UUID in depends_on."""
        worker = MockWorker()
        dep1 = make_task("Dep 1", worker)
        uuid_dep = uuid4()
        task = make_task("Task", worker, depends_on=[dep1, uuid_dep])

        data = task.model_dump(mode="json")

        assert len(data["depends_on"]) == 2
        assert data["depends_on"][0] == str(dep1.id)
        assert data["depends_on"][1] == str(uuid_dep)

    def test_model_dump_serializes_evaluator(self):
        """model_dump() should serialize evaluator type."""

        class MockEvaluator:
            pass

        worker = MockWorker()
        task = Task(
            name="Evaluated Task",
            description="Task with evaluator",
            assigned_to=worker,
            evaluator=MockEvaluator(),
        )

        data = task.model_dump(mode="json")

        assert data["evaluator"] is not None
        assert data["evaluator"]["type"] == "MockEvaluator"

    def test_model_dump_serializes_none_evaluator(self):
        """model_dump() should handle None evaluator."""
        worker = MockWorker()
        task = make_task("Test", worker)

        data = task.model_dump(mode="json")

        assert data["evaluator"] is None


# =============================================================================
# create_output_resource_from_sdk Tests
# =============================================================================


class TestCreateOutputResourceFromSDK:
    """Tests for create_output_resource_from_sdk()."""

    def test_creates_output_resource_from_file(self, tmp_path):
        """Create output resource from file path."""
        test_file = tmp_path / "output.txt"
        test_file.write_text("Output content")

        sdk_resource = Resource(name="Output File", path=str(test_file))
        run_id = uuid4()
        task_id = uuid4()
        execution_id = uuid4()

        data = create_output_resource_from_sdk(sdk_resource, run_id, task_id, execution_id)

        assert data["run_id"] == run_id
        assert data["task_id"] == task_id
        assert data["task_execution_id"] == execution_id
        assert data["is_input"] is False
        assert data["name"] == "Output File"

    def test_creates_output_resource_from_content(self):
        """Create output resource from inline content."""
        sdk_resource = Resource(name="Generated", content="Generated content")
        run_id = uuid4()
        task_id = uuid4()
        execution_id = uuid4()

        data = create_output_resource_from_sdk(sdk_resource, run_id, task_id, execution_id)

        assert data["run_id"] == run_id
        assert data["task_execution_id"] == execution_id
        assert data["is_input"] is False
        assert data["name"] == "Generated"
        assert Path(data["file_path"]).exists()

    def test_creates_output_resource_from_url(self):
        """Create output resource from URL."""
        sdk_resource = Resource(name="Remote Output", url="https://example.com/result.json")
        run_id = uuid4()
        task_id = uuid4()
        execution_id = uuid4()

        data = create_output_resource_from_sdk(sdk_resource, run_id, task_id, execution_id)

        assert data["run_id"] == run_id
        assert data["is_input"] is False
        assert data["file_path"] == "https://example.com/result.json"


# =============================================================================
# serialize_task_tree with field serializers Tests
# =============================================================================


class TestSerializeTaskTreeWithSerializers:
    """Tests that serialize_task_tree uses Task's field serializers."""

    def test_includes_worker_info(self):
        """Serialized tree should include worker info."""
        worker = MockWorker("my_worker")
        task = make_task("Test", worker)

        result = serialize_task_tree(task)

        assert "assigned_to" in result
        assert result["assigned_to"]["id"] == str(worker.id)
        assert result["assigned_to"]["name"] == "my_worker"
        assert result["assigned_to"]["type"] == "MockWorker"

    def test_includes_full_team(self):
        """Serialized tree should include full team."""
        worker1 = MockWorker("lead")
        worker2 = MockWorker("support")
        task = Task(
            name="Team Task",
            description="Collaborative task",
            assigned_to=worker1,
            full_team=[worker1, worker2],
        )

        result = serialize_task_tree(task)

        assert result["full_team"] is not None
        assert len(result["full_team"]) == 2

    def test_nested_tree_includes_worker_info(self):
        """Nested tree serialization includes worker info at all levels."""
        worker_parent = MockWorker("parent_worker")
        worker_child = MockWorker("child_worker")

        child = Task(
            name="Child",
            description="Child task",
            assigned_to=worker_child,
        )
        parent = Task(
            name="Parent",
            description="Parent task",
            assigned_to=worker_parent,
            children=[child],
        )

        result = serialize_task_tree(parent)

        assert result["assigned_to"]["name"] == "parent_worker"
        assert result["children"][0]["assigned_to"]["name"] == "child_worker"
