"""Unit tests for AgentRegistry."""

from uuid import uuid4

import pytest

from h_arcane import Task
from h_arcane.core._internal.agents.registry import AgentRegistry


# =============================================================================
# Mock Worker for Testing
# =============================================================================


class MockWorker:
    """Simple mock worker for testing."""

    def __init__(self, name: str = "mock_worker", model: str = "gpt-4o"):
        self.id = uuid4()
        self.name = name
        self.model = model
        self.tools = []
        self.system_prompt = "You are a test worker."

    async def execute(self, task, context):
        pass


class MockWorkerWithTools:
    """Mock worker with tools for testing tool serialization."""

    def __init__(self, name: str = "tool_worker"):
        self.id = uuid4()
        self.name = name
        self.model = "gpt-4o"
        self.system_prompt = "Worker with tools."

        # Different tool types to test serialization
        def my_tool():
            pass

        class ToolClass:
            name = "class_tool"

        self.tools = [my_tool, ToolClass(), "string_tool"]

    async def execute(self, task, context):
        pass


def make_task(name: str, worker: MockWorker, **kwargs) -> Task:
    """Helper to create tasks with auto-generated description for tests."""
    return Task(name=name, description=f"Test task: {name}", assigned_to=worker, **kwargs)


# =============================================================================
# Basic Registration Tests
# =============================================================================


class TestAgentRegistryBasic:
    """Tests for basic AgentRegistry functionality."""

    def test_empty_registry(self):
        """New registry starts empty."""
        registry = AgentRegistry()
        assert len(registry) == 0
        assert registry.get_all_workers() == []

    def test_register_single_worker(self):
        """Register a single worker."""
        registry = AgentRegistry()
        worker = MockWorker("analyst")

        registry.register_worker(worker)

        assert len(registry) == 1
        assert worker.id in registry
        assert registry.get_worker(worker.id) is worker

    def test_register_duplicate_worker_deduplicates(self):
        """Registering same worker twice only keeps one."""
        registry = AgentRegistry()
        worker = MockWorker("analyst")

        registry.register_worker(worker)
        registry.register_worker(worker)

        assert len(registry) == 1

    def test_register_different_workers(self):
        """Register multiple different workers."""
        registry = AgentRegistry()
        worker1 = MockWorker("analyst")
        worker2 = MockWorker("writer")

        registry.register_worker(worker1)
        registry.register_worker(worker2)

        assert len(registry) == 2
        assert worker1.id in registry
        assert worker2.id in registry

    def test_worker_without_id_raises(self):
        """Worker without id attribute raises error."""
        registry = AgentRegistry()

        class BadWorker:
            name = "bad"

        with pytest.raises(ValueError, match="has no 'id' attribute"):
            registry.register_worker(BadWorker())  # type: ignore[arg-type]


# =============================================================================
# Task Tree Registration Tests
# =============================================================================


class TestRegisterFromTask:
    """Tests for register_from_task()."""

    def test_register_from_single_task(self):
        """Register workers from a single task."""
        registry = AgentRegistry()
        worker = MockWorker("analyst")
        task = make_task("Task", worker)

        registry.register_from_task(task)

        assert len(registry) == 1
        assert worker.id in registry

    def test_register_from_task_with_full_team(self):
        """Register workers from task with full_team."""
        registry = AgentRegistry()
        primary = MockWorker("analyst")
        helper1 = MockWorker("writer")
        helper2 = MockWorker("reviewer")
        task = Task(
            name="Task",
            description="Collaborative task",
            assigned_to=primary,
            full_team=[primary, helper1, helper2],
        )

        registry.register_from_task(task)

        # Should have 3 unique workers (primary appears twice but deduped)
        assert len(registry) == 3
        assert primary.id in registry
        assert helper1.id in registry
        assert helper2.id in registry

    def test_register_from_task_tree(self):
        """Register workers from a task tree with children."""
        registry = AgentRegistry()
        analyst = MockWorker("analyst")
        writer = MockWorker("writer")
        reviewer = MockWorker("reviewer")

        child1 = make_task("Research", analyst)
        child2 = make_task("Write", writer)
        child3 = make_task("Review", reviewer)
        root = Task(
            name="Report",
            description="Full report workflow",
            assigned_to=analyst,  # Analyst is also the manager
            children=[child1, child2, child3],
        )

        registry.register_from_task(root)

        # Should have 3 unique workers
        assert len(registry) == 3
        assert analyst.id in registry
        assert writer.id in registry
        assert reviewer.id in registry

    def test_register_from_nested_tree(self):
        """Register workers from deeply nested task tree."""
        registry = AgentRegistry()
        worker_a = MockWorker("A")
        worker_b = MockWorker("B")
        worker_c = MockWorker("C")

        leaf = make_task("Leaf", worker_c)
        middle = make_task("Middle", worker_b, children=[leaf])
        root = make_task("Root", worker_a, children=[middle])

        registry.register_from_task(root)

        assert len(registry) == 3

    def test_register_shared_workers_across_tasks(self):
        """Same worker assigned to multiple tasks is only registered once."""
        registry = AgentRegistry()
        shared_worker = MockWorker("shared")

        task1 = make_task("Task 1", shared_worker)
        task2 = make_task("Task 2", shared_worker)
        root = Task(
            name="Root",
            description="Root with shared workers",
            assigned_to=shared_worker,
            children=[task1, task2],
        )

        registry.register_from_task(root)

        assert len(registry) == 1
        assert shared_worker.id in registry


# =============================================================================
# AgentConfig Data Creation Tests
# =============================================================================


class TestCreateAgentConfigData:
    """Tests for create_agent_config_data()."""

    def test_basic_config_data(self):
        """Create config data with basic worker."""
        registry = AgentRegistry()
        worker = MockWorker("analyst", model="gpt-4o-mini")
        worker.system_prompt = "You are an analyst."
        run_id = uuid4()

        data = registry.create_agent_config_data(worker, run_id)

        assert data["run_id"] == run_id
        assert data["name"] == "analyst"
        assert data["agent_type"] == "MockWorker"
        assert data["model"] == "gpt-4o-mini"
        assert data["system_prompt"] == "You are an analyst."
        assert data["tools"] == []
        assert data["role"] == "worker"

    def test_config_data_with_custom_role(self):
        """Create config data with custom role."""
        registry = AgentRegistry()
        worker = MockWorker("stakeholder")
        run_id = uuid4()

        data = registry.create_agent_config_data(worker, run_id, role="stakeholder")

        assert data["role"] == "stakeholder"

    def test_config_data_with_tools(self):
        """Create config data with tools serialized."""
        registry = AgentRegistry()
        worker = MockWorkerWithTools("tool_user")
        run_id = uuid4()

        data = registry.create_agent_config_data(worker, run_id)

        # Tools should be serialized to names
        assert "my_tool" in data["tools"]  # Function name
        assert "class_tool" in data["tools"]  # Class with .name
        assert "string_tool" in data["tools"]  # String tool

    def test_create_all_config_data(self):
        """Create config data for all registered workers."""
        registry = AgentRegistry()
        worker1 = MockWorker("analyst")
        worker2 = MockWorker("writer")
        registry.register_worker(worker1)
        registry.register_worker(worker2)
        run_id = uuid4()

        all_data = registry.create_all_agent_config_data(run_id)

        assert len(all_data) == 2
        names = {d["name"] for d in all_data}
        assert names == {"analyst", "writer"}


# =============================================================================
# Config ID Lookup Tests
# =============================================================================


class TestConfigIdLookup:
    """Tests for get_config_id() after persistence."""

    def test_config_id_before_persist_returns_none(self):
        """get_config_id returns None before persist is called."""
        registry = AgentRegistry()
        worker = MockWorker("analyst")
        registry.register_worker(worker)

        assert registry.get_config_id(worker.id) is None

    def test_config_id_for_unknown_worker(self):
        """get_config_id returns None for unknown worker."""
        registry = AgentRegistry()
        unknown_id = uuid4()

        assert registry.get_config_id(unknown_id) is None


# =============================================================================
# Integration Tests
# =============================================================================


class TestAgentRegistryIntegration:
    """Integration tests for full workflow."""

    def test_full_workflow_without_db(self):
        """Test full workflow using data creation (no DB)."""
        # Create a realistic task tree
        analyst = MockWorker("analyst")
        writer = MockWorker("writer")
        reviewer = MockWorker("reviewer")

        research = make_task("Research", analyst)
        write = make_task("Write", writer, depends_on=[research])
        review = make_task("Review", reviewer, depends_on=[write])
        workflow = Task(
            name="Report Workflow",
            description="Full report generation workflow",
            assigned_to=analyst,  # Manager
            children=[research, write, review],
        )

        # Build registry
        registry = AgentRegistry()
        registry.register_from_task(workflow)

        # Verify workers collected
        assert len(registry) == 3

        # Create config data
        run_id = uuid4()
        configs = registry.create_all_agent_config_data(run_id)

        assert len(configs) == 3
        for config in configs:
            assert config["run_id"] == run_id
            assert config["agent_type"] == "MockWorker"
            assert config["role"] == "worker"

    def test_iteration_and_contains(self):
        """Test __iter__ and __contains__."""
        registry = AgentRegistry()
        worker1 = MockWorker("a")
        worker2 = MockWorker("b")
        registry.register_worker(worker1)
        registry.register_worker(worker2)

        # Test __contains__
        assert worker1.id in registry
        assert worker2.id in registry
        assert uuid4() not in registry

        # Test __iter__
        workers = list(registry)
        assert len(workers) == 2
        assert worker1 in workers
        assert worker2 in workers
