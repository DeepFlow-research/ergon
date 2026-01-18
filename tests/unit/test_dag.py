"""Unit tests for TaskRegistry and DAG processing."""

from uuid import uuid4

import pytest

from h_arcane import Task, TaskStatus
from h_arcane.core._internal.task.registry import (
    CycleDetectedError,
    MissingDependencyError,
    TaskRegistry,
)


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
# Basic Registry Tests
# =============================================================================


class TestTaskRegistryBasic:
    """Basic TaskRegistry functionality tests."""

    def test_registry_with_single_task(self):
        """Registry handles single task."""
        worker = MockWorker()
        task = make_task("Single", worker)

        registry = TaskRegistry(task)

        assert len(registry) == 1
        assert registry.root_id == task.id
        assert task.id in registry

    def test_registry_flattens_tree(self):
        """Registry flattens nested task tree."""
        worker = MockWorker()
        c = make_task("C", worker)
        d = make_task("D", worker)
        a = make_task("A", worker, children=[c, d])
        b = make_task("B", worker)
        root = make_task("Root", worker, children=[a, b])

        registry = TaskRegistry(root)

        assert len(registry) == 5
        assert all(t.id in registry for t in [root, a, b, c, d])

    def test_registry_sets_parent_ids(self):
        """Registry sets parent_id on all tasks."""
        worker = MockWorker()
        child = make_task("Child", worker)
        parent = make_task("Parent", worker, children=[child])

        TaskRegistry(parent)

        assert parent.parent_id is None  # Root has no parent
        assert child.parent_id == parent.id

    def test_get_task(self):
        """get_task returns task by ID."""
        worker = MockWorker()
        task = make_task("Task", worker)

        registry = TaskRegistry(task)

        assert registry.get_task(task.id) == task
        assert registry.get_task(uuid4()) is None

    def test_get_root(self):
        """get_root returns the root task."""
        worker = MockWorker()
        child = make_task("Child", worker)
        root = make_task("Root", worker, children=[child])

        registry = TaskRegistry(root)

        assert registry.get_root() == root


# =============================================================================
# Dependency Resolution Tests
# =============================================================================


class TestDependencyResolution:
    """Tests for dependency resolution."""

    def test_resolves_task_object_dependencies(self):
        """Dependencies specified as Task objects are resolved to UUIDs."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        root = make_task("Root", worker, children=[a, b])

        TaskRegistry(root)

        assert b._resolved_dependency_ids == [a.id]

    def test_resolves_uuid_dependencies(self):
        """Dependencies specified as UUIDs are kept as-is."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a.id])
        root = make_task("Root", worker, children=[a, b])

        TaskRegistry(root)

        assert b._resolved_dependency_ids == [a.id]

    def test_missing_dependency_raises_error(self):
        """Missing dependency raises MissingDependencyError."""
        worker = MockWorker()
        missing_id = uuid4()
        task = make_task("Task", worker, depends_on=[missing_id])

        with pytest.raises(MissingDependencyError) as exc_info:
            TaskRegistry(task)

        assert exc_info.value.missing_dep_id == missing_id


# =============================================================================
# Cycle Detection Tests
# =============================================================================


class TestCycleDetection:
    """Tests for cycle detection in dependency graph."""

    def test_no_cycle_in_valid_dag(self):
        """Valid DAG passes validation."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        c = make_task("C", worker, depends_on=[b])
        root = make_task("Root", worker, children=[a, b, c])

        # Should not raise
        registry = TaskRegistry(root)
        assert len(registry) == 4

    def test_detects_direct_cycle(self):
        """Detects A → B → A cycle."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])

        # Create cycle: A depends on B
        a.depends_on = [b]

        root = make_task("Root", worker, children=[a, b])

        with pytest.raises(CycleDetectedError):
            TaskRegistry(root)

    def test_detects_self_cycle(self):
        """Detects A → A self-cycle."""
        worker = MockWorker()
        a = make_task("A", worker)
        a.depends_on = [a]  # Self-dependency

        with pytest.raises(CycleDetectedError):
            TaskRegistry(a)

    def test_detects_long_cycle(self):
        """Detects A → B → C → A cycle."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        c = make_task("C", worker, depends_on=[b])

        # Create cycle: A depends on C
        a.depends_on = [c]

        root = make_task("Root", worker, children=[a, b, c])

        with pytest.raises(CycleDetectedError):
            TaskRegistry(root)


# =============================================================================
# Initial Status Tests
# =============================================================================


class TestInitialStatuses:
    """Tests for initial status computation."""

    def test_leaf_without_deps_is_ready(self):
        """Leaf task with no dependencies starts as READY."""
        worker = MockWorker()
        task = make_task("Leaf", worker)

        TaskRegistry(task)

        assert task.status == TaskStatus.READY

    def test_leaf_with_deps_is_pending(self):
        """Leaf task with dependencies starts as PENDING."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        root = make_task("Root", worker, children=[a, b])

        TaskRegistry(root)

        assert a.status == TaskStatus.READY  # No deps
        assert b.status == TaskStatus.PENDING  # Has deps

    def test_composite_task_is_pending(self):
        """Composite task (with children) starts as PENDING."""
        worker = MockWorker()
        child = make_task("Child", worker)
        parent = make_task("Parent", worker, children=[child])

        TaskRegistry(parent)

        assert parent.status == TaskStatus.PENDING
        assert child.status == TaskStatus.READY


# =============================================================================
# Query Method Tests
# =============================================================================


class TestQueryMethods:
    """Tests for registry query methods."""

    def test_get_leaf_tasks(self):
        """get_leaf_tasks returns only leaf tasks."""
        worker = MockWorker()
        c = make_task("C", worker)
        d = make_task("D", worker)
        a = make_task("A", worker, children=[c, d])
        b = make_task("B", worker)
        root = make_task("Root", worker, children=[a, b])

        registry = TaskRegistry(root)
        leaves = registry.get_leaf_tasks()
        names = {t.name for t in leaves}

        assert names == {"B", "C", "D"}

    def test_get_ready_tasks(self):
        """get_ready_tasks returns tasks that are READY."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker)
        c = make_task("C", worker, depends_on=[a, b])
        root = make_task("Root", worker, children=[a, b, c])

        registry = TaskRegistry(root)
        ready = registry.get_ready_tasks()
        names = {t.name for t in ready}

        assert names == {"A", "B"}  # C is pending (deps not met)

    def test_get_dependents(self):
        """get_dependents returns tasks waiting on the given task."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        c = make_task("C", worker, depends_on=[a])
        d = make_task("D", worker, depends_on=[b])
        root = make_task("Root", worker, children=[a, b, c, d])

        registry = TaskRegistry(root)

        # B and C depend on A
        a_dependents = registry.get_dependents(a.id)
        names = {t.name for t in a_dependents}
        assert names == {"B", "C"}

        # Only D depends on B
        b_dependents = registry.get_dependents(b.id)
        assert len(b_dependents) == 1
        assert b_dependents[0].name == "D"

    def test_get_dependencies(self):
        """get_dependencies returns tasks that must complete first."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker)
        c = make_task("C", worker, depends_on=[a, b])
        root = make_task("Root", worker, children=[a, b, c])

        registry = TaskRegistry(root)

        c_deps = registry.get_dependencies(c.id)
        names = {t.name for t in c_deps}
        assert names == {"A", "B"}

    def test_get_blocking_dependencies(self):
        """get_blocking_dependencies returns incomplete dependencies."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker)
        c = make_task("C", worker, depends_on=[a, b])
        root = make_task("Root", worker, children=[a, b, c])

        registry = TaskRegistry(root)

        # Initially both A and B block C
        blocking = registry.get_blocking_dependencies(c.id)
        names = {t.name for t in blocking}
        assert names == {"A", "B"}

        # Mark A as completed
        a.status = TaskStatus.COMPLETED

        # Now only B blocks C
        blocking = registry.get_blocking_dependencies(c.id)
        assert len(blocking) == 1
        assert blocking[0].name == "B"

    def test_can_run(self):
        """can_run returns True when all dependencies are satisfied."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        root = make_task("Root", worker, children=[a, b])

        registry = TaskRegistry(root)

        # A can run (no deps)
        assert registry.can_run(a.id) is True

        # B cannot run (A not complete)
        assert registry.can_run(b.id) is False

        # Mark A complete
        a.status = TaskStatus.COMPLETED

        # Now B can run
        assert registry.can_run(b.id) is True

    def test_get_parent(self):
        """get_parent returns the parent task."""
        worker = MockWorker()
        grandchild = make_task("Grandchild", worker)
        child = make_task("Child", worker, children=[grandchild])
        root = make_task("Root", worker, children=[child])

        registry = TaskRegistry(root)

        assert registry.get_parent(root.id) is None
        assert registry.get_parent(child.id) == root
        assert registry.get_parent(grandchild.id) == child


# =============================================================================
# DAG Pattern Tests
# =============================================================================


class TestDAGPatterns:
    """Tests for common DAG patterns."""

    def test_linear_dag(self):
        """Linear DAG: A → B → C."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        c = make_task("C", worker, depends_on=[b])
        root = make_task("Root", worker, children=[a, b, c])

        registry = TaskRegistry(root)

        # Only A is ready initially
        ready = registry.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].name == "A"

        # Simulate execution
        a.status = TaskStatus.COMPLETED
        assert registry.can_run(b.id) is True
        assert registry.can_run(c.id) is False

        b.status = TaskStatus.COMPLETED
        assert registry.can_run(c.id) is True

    def test_diamond_dag(self):
        """Diamond DAG: A → B, A → C, B+C → D."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        c = make_task("C", worker, depends_on=[a])
        d = make_task("D", worker, depends_on=[b, c])
        root = make_task("Root", worker, children=[a, b, c, d])

        registry = TaskRegistry(root)

        # Only A is ready initially
        ready = registry.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].name == "A"

        # After A completes, B and C are ready
        a.status = TaskStatus.COMPLETED
        assert registry.can_run(b.id) is True
        assert registry.can_run(c.id) is True
        assert registry.can_run(d.id) is False

        # D needs both B and C
        b.status = TaskStatus.COMPLETED
        assert registry.can_run(d.id) is False  # Still waiting on C

        c.status = TaskStatus.COMPLETED
        assert registry.can_run(d.id) is True

    def test_parallel_tasks(self):
        """Parallel tasks: A, B, C all independent."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker)
        c = make_task("C", worker)
        root = make_task("Root", worker, children=[a, b, c])

        registry = TaskRegistry(root)

        # All are ready immediately
        ready = registry.get_ready_tasks()
        names = {t.name for t in ready}
        assert names == {"A", "B", "C"}


# =============================================================================
# Serialization Tests
# =============================================================================


class TestSerialization:
    """Tests for registry serialization."""

    def test_to_dict(self):
        """to_dict serializes the task tree."""
        worker = MockWorker()
        child = Task(name="Child", description="A child task", assigned_to=worker)
        root = Task(
            name="Root",
            description="Root task",
            assigned_to=worker,
            children=[child],
        )

        registry = TaskRegistry(root)
        data = registry.to_dict()

        assert data["name"] == "Root"
        assert data["description"] == "Root task"
        assert data["id"] == str(root.id)
        assert len(data["children"]) == 1
        assert data["children"][0]["name"] == "Child"

    def test_to_dict_includes_dependencies(self):
        """to_dict includes resolved dependencies."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        root = make_task("Root", worker, children=[a, b])

        registry = TaskRegistry(root)
        data = registry.to_dict()

        # Find B in children
        b_data = next(c for c in data["children"] if c["name"] == "B")
        assert b_data["depends_on"] == [str(a.id)]


# =============================================================================
# Status Aggregation Tests
# =============================================================================


class TestStatusAggregation:
    """Tests for status aggregation methods."""

    def test_is_all_complete(self):
        """is_all_complete returns True when all tasks are COMPLETED."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker)
        root = make_task("Root", worker, children=[a, b])

        registry = TaskRegistry(root)

        assert registry.is_all_complete() is False

        a.status = TaskStatus.COMPLETED
        b.status = TaskStatus.COMPLETED
        root.status = TaskStatus.COMPLETED

        assert registry.is_all_complete() is True

    def test_is_any_failed(self):
        """is_any_failed returns True if any task has FAILED status."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker)
        root = make_task("Root", worker, children=[a, b])

        registry = TaskRegistry(root)

        assert registry.is_any_failed() is False

        a.status = TaskStatus.FAILED

        assert registry.is_any_failed() is True
