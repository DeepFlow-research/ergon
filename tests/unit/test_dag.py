"""Unit tests for task DAG validation."""

from uuid import uuid4

import pytest

from h_arcane import Task, TaskStatus
from h_arcane.core.worker import BaseWorker
from h_arcane.core._internal.task.validation import (
    CycleDetectedError,
    MissingDependencyError,
    validate_task_dag,
)


# =============================================================================
# Mock Worker for Testing
# =============================================================================


class MockWorker(BaseWorker):
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
# Basic Validation Tests
# =============================================================================


class TestValidateTaskDagBasic:
    """Basic validate_task_dag functionality tests."""

    def test_validates_single_task(self):
        """Validation handles single task."""
        worker = MockWorker()
        task = make_task("Single", worker)

        validate_task_dag(task)

        # Task should be ready (leaf with no deps)
        assert task.status == TaskStatus.READY

    def test_flattens_tree_sets_parent_ids(self):
        """Validation flattens tree and sets parent_id on all tasks."""
        worker = MockWorker()
        c = make_task("C", worker)
        d = make_task("D", worker)
        a = make_task("A", worker, children=[c, d])
        b = make_task("B", worker)
        root = make_task("Root", worker, children=[a, b])

        validate_task_dag(root)

        assert root.parent_id is None  # Root has no parent
        assert a.parent_id == root.id
        assert b.parent_id == root.id
        assert c.parent_id == a.id
        assert d.parent_id == a.id


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

        validate_task_dag(root)

        assert b._resolved_dependency_ids == [a.id]

    def test_resolves_uuid_dependencies(self):
        """Dependencies specified as UUIDs are kept as-is."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a.id])
        root = make_task("Root", worker, children=[a, b])

        validate_task_dag(root)

        assert b._resolved_dependency_ids == [a.id]

    def test_missing_dependency_raises_error(self):
        """Missing dependency raises MissingDependencyError."""
        worker = MockWorker()
        missing_id = uuid4()
        task = make_task("Task", worker, depends_on=[missing_id])

        with pytest.raises(MissingDependencyError) as exc_info:
            validate_task_dag(task)

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
        validate_task_dag(root)

    def test_detects_direct_cycle(self):
        """Detects A → B → A cycle."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])

        # Create cycle: A depends on B
        a.depends_on = [b]

        root = make_task("Root", worker, children=[a, b])

        with pytest.raises(CycleDetectedError):
            validate_task_dag(root)

    def test_detects_self_cycle(self):
        """Detects A → A self-cycle."""
        worker = MockWorker()
        a = make_task("A", worker)
        a.depends_on = [a]  # Self-dependency

        with pytest.raises(CycleDetectedError):
            validate_task_dag(a)

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
            validate_task_dag(root)


# =============================================================================
# Initial Status Tests
# =============================================================================


class TestInitialStatuses:
    """Tests for initial status computation."""

    def test_leaf_without_deps_is_ready(self):
        """Leaf task with no dependencies starts as READY."""
        worker = MockWorker()
        task = make_task("Leaf", worker)

        validate_task_dag(task)

        assert task.status == TaskStatus.READY

    def test_leaf_with_deps_is_pending(self):
        """Leaf task with dependencies starts as PENDING."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        root = make_task("Root", worker, children=[a, b])

        validate_task_dag(root)

        assert a.status == TaskStatus.READY  # No deps
        assert b.status == TaskStatus.PENDING  # Has deps

    def test_composite_task_is_pending(self):
        """Composite task (with children) starts as PENDING."""
        worker = MockWorker()
        child = make_task("Child", worker)
        parent = make_task("Parent", worker, children=[child])

        validate_task_dag(parent)

        assert parent.status == TaskStatus.PENDING
        assert child.status == TaskStatus.READY


# =============================================================================
# Task.get_all_tasks() Tests
# =============================================================================


class TestGetAllTasks:
    """Tests for Task.get_all_tasks() method."""

    def test_single_task_returns_self(self):
        """get_all_tasks on single task returns just itself."""
        worker = MockWorker()
        task = make_task("Single", worker)

        all_tasks = task.get_all_tasks()

        assert len(all_tasks) == 1
        assert all_tasks[0] == task

    def test_returns_all_descendants(self):
        """get_all_tasks returns self and all descendants."""
        worker = MockWorker()
        c = make_task("C", worker)
        d = make_task("D", worker)
        a = make_task("A", worker, children=[c, d])
        b = make_task("B", worker)
        root = make_task("Root", worker, children=[a, b])

        all_tasks = root.get_all_tasks()

        assert len(all_tasks) == 5
        task_ids = {t.id for t in all_tasks}
        assert task_ids == {root.id, a.id, b.id, c.id, d.id}


# =============================================================================
# DAG Pattern Tests
# =============================================================================


class TestDAGPatterns:
    """Tests for common DAG patterns."""

    def test_linear_dag(self):
        """Linear DAG: A → B → C validates correctly."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        c = make_task("C", worker, depends_on=[b])
        root = make_task("Root", worker, children=[a, b, c])

        validate_task_dag(root)

        # Only A is ready initially
        assert a.status == TaskStatus.READY
        assert b.status == TaskStatus.PENDING
        assert c.status == TaskStatus.PENDING

    def test_diamond_dag(self):
        """Diamond DAG: A → B, A → C, B+C → D validates correctly."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker, depends_on=[a])
        c = make_task("C", worker, depends_on=[a])
        d = make_task("D", worker, depends_on=[b, c])
        root = make_task("Root", worker, children=[a, b, c, d])

        validate_task_dag(root)

        # Only A is ready initially
        assert a.status == TaskStatus.READY
        assert b.status == TaskStatus.PENDING
        assert c.status == TaskStatus.PENDING
        assert d.status == TaskStatus.PENDING

    def test_parallel_tasks(self):
        """Parallel tasks: A, B, C all independent."""
        worker = MockWorker()
        a = make_task("A", worker)
        b = make_task("B", worker)
        c = make_task("C", worker)
        root = make_task("Root", worker, children=[a, b, c])

        validate_task_dag(root)

        # All leaf tasks are ready
        assert a.status == TaskStatus.READY
        assert b.status == TaskStatus.READY
        assert c.status == TaskStatus.READY
        # Root is pending (composite)
        assert root.status == TaskStatus.PENDING
