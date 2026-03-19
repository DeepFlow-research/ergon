"""Unit tests for the DAG propagation logic."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from h_arcane.core.status import TaskStatus, TaskTrigger
from h_arcane.core._internal.task.propagation import (
    mark_task_ready,
    mark_task_failed,
    is_task_ready,
    on_task_completed,
    propagate_to_parent,
    is_workflow_complete,
    is_workflow_failed,
    get_initial_ready_tasks,
)
from h_arcane.core._internal.task.schema import parse_task_tree


# =============================================================================
# Helper Functions for Tests
# =============================================================================


def make_run(run_id, experiment_id):
    """Create a mock Run object."""
    run = MagicMock()
    run.id = run_id
    run.experiment_id = experiment_id
    return run


def make_experiment(experiment_id, task_tree, root_task_id=None):
    """Create a mock Experiment object."""
    exp = MagicMock()
    exp.id = experiment_id
    exp.task_tree = task_tree
    exp.root_task_id = root_task_id or task_tree.get("id")
    exp.parsed_task_tree.return_value = parse_task_tree(task_tree) if task_tree else None
    return exp


def make_task_tree(
    task_id, name="Task", children=None, depends_on=None, is_leaf=True, parent_id=None
):
    """Create a task_tree dict with all required fields for TaskTreeNode."""
    return {
        "id": str(task_id),
        "name": name,
        "description": f"Description for {name}",
        "assigned_to": {"id": str(uuid4()), "name": "test_worker", "type": "TestWorker"},
        "children": children or [],
        "depends_on": [str(d) for d in (depends_on or [])],
        "is_leaf": is_leaf,
        "parent_id": str(parent_id) if parent_id else None,
        "resources": [],
    }


# =============================================================================
# TaskTreeNode.get_leaf_ids Tests
# =============================================================================


class TestGetLeafDescendants:
    """Tests for TaskTreeNode.get_leaf_ids()."""

    def test_single_leaf_task(self):
        """Single leaf task returns itself."""

        task_id = uuid4()
        tree_data = make_task_tree(task_id, is_leaf=True)

        tree = parse_task_tree(tree_data)
        assert tree is not None
        result = tree.get_leaf_ids()

        assert result == [task_id]

    def test_composite_with_leaf_children(self):
        """Composite task returns all leaf children."""

        child1_id = uuid4()
        child2_id = uuid4()
        parent_id = uuid4()

        tree_data = make_task_tree(
            parent_id,
            name="Parent",
            is_leaf=False,
            children=[
                make_task_tree(child1_id, name="Child1", is_leaf=True),
                make_task_tree(child2_id, name="Child2", is_leaf=True),
            ],
        )

        tree = parse_task_tree(tree_data)
        assert tree is not None
        result = tree.get_leaf_ids()

        assert set(result) == {child1_id, child2_id}

    def test_nested_tree(self):
        """Nested tree returns deepest leaves."""

        leaf1_id = uuid4()
        leaf2_id = uuid4()
        leaf3_id = uuid4()
        mid_id = uuid4()
        root_id = uuid4()

        tree_data = make_task_tree(
            root_id,
            name="Root",
            is_leaf=False,
            children=[
                make_task_tree(
                    mid_id,
                    name="Middle",
                    is_leaf=False,
                    children=[
                        make_task_tree(leaf1_id, name="Leaf1", is_leaf=True),
                        make_task_tree(leaf2_id, name="Leaf2", is_leaf=True),
                    ],
                ),
                make_task_tree(leaf3_id, name="Leaf3", is_leaf=True),
            ],
        )

        tree = parse_task_tree(tree_data)
        assert tree is not None
        result = tree.get_leaf_ids()

        assert set(result) == {leaf1_id, leaf2_id, leaf3_id}


# =============================================================================
# _find_task_in_tree Tests
# =============================================================================


class TestFindTaskInTree:
    """Tests for TaskTreeNode.find_by_id()."""

    def test_find_root_task(self):
        """Find the root task."""

        task_id = uuid4()
        tree_data = make_task_tree(task_id, name="Root")

        tree = parse_task_tree(tree_data)
        assert tree is not None
        result = tree.find_by_id(task_id)

        assert result is not None
        assert result.name == "Root"

    def test_find_nested_task(self):
        """Find a deeply nested task."""

        target_id = uuid4()
        root_id = uuid4()
        mid_id = uuid4()

        tree_data = make_task_tree(
            root_id,
            name="Root",
            is_leaf=False,
            children=[
                make_task_tree(
                    mid_id,
                    name="Middle",
                    is_leaf=False,
                    children=[
                        make_task_tree(target_id, name="Target", is_leaf=True),
                    ],
                ),
            ],
        )

        tree = parse_task_tree(tree_data)
        assert tree is not None
        result = tree.find_by_id(target_id)

        assert result is not None
        assert result.name == "Target"

    def test_task_not_found(self):
        """Return None if task not in tree."""

        tree_data = make_task_tree(uuid4(), name="Root")
        missing_id = uuid4()

        tree = parse_task_tree(tree_data)
        assert tree is not None
        result = tree.find_by_id(missing_id)

        assert result is None


# =============================================================================
# TaskTreeNode.extract_dependencies Tests
# =============================================================================


class TestExtractDependenciesFromTree:
    """Tests for TaskTreeNode.extract_dependencies()."""

    def test_no_dependencies(self):
        """Task with no dependencies returns empty list."""

        tree_data = make_task_tree(uuid4(), depends_on=[])

        tree = parse_task_tree(tree_data)
        assert tree is not None
        result = tree.extract_dependencies()

        assert result == []

    def test_single_dependency(self):
        """Task with one dependency."""

        dep_id = uuid4()
        task_id = uuid4()

        tree_data = make_task_tree(
            uuid4(),
            name="Root",
            is_leaf=False,
            children=[
                make_task_tree(dep_id, name="Dep"),
                make_task_tree(task_id, name="Task", depends_on=[dep_id]),
            ],
        )

        tree = parse_task_tree(tree_data)
        assert tree is not None
        result = tree.extract_dependencies()

        assert (task_id, dep_id) in result

    def test_multiple_dependencies(self):
        """Task with multiple dependencies."""

        dep1_id = uuid4()
        dep2_id = uuid4()
        task_id = uuid4()

        tree_data = make_task_tree(
            uuid4(),
            name="Root",
            is_leaf=False,
            children=[
                make_task_tree(dep1_id, name="Dep1"),
                make_task_tree(dep2_id, name="Dep2"),
                make_task_tree(task_id, name="Task", depends_on=[dep1_id, dep2_id]),
            ],
        )

        tree = parse_task_tree(tree_data)
        assert tree is not None

        result = tree.extract_dependencies()

        assert (task_id, dep1_id) in result
        assert (task_id, dep2_id) in result


# =============================================================================
# State Update Functions Tests (with mocking)
# =============================================================================


class TestMarkTaskReady:
    """Tests for mark_task_ready()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_records_state_change_event(self, mock_queries):
        """mark_task_ready records a TaskStateEvent via record_state_change."""

        run_id = uuid4()
        task_id = uuid4()

        mark_task_ready(run_id, task_id, triggered_by=TaskTrigger.DEPENDENCY_SATISFIED)

        mock_queries.task_state_events.record_state_change.assert_called_once()
        call_kwargs = mock_queries.task_state_events.record_state_change.call_args.kwargs
        assert call_kwargs["run_id"] == run_id
        assert call_kwargs["task_id"] == task_id
        assert call_kwargs["new_status"] == "ready"
        assert call_kwargs["triggered_by"] == TaskTrigger.DEPENDENCY_SATISFIED.value


class TestMarkTaskFailed:
    """Tests for mark_task_failed()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_includes_error_in_metadata(self, mock_queries):
        """mark_task_failed includes error in event metadata."""

        run_id = uuid4()
        task_id = uuid4()

        mark_task_failed(run_id, task_id, error="Something went wrong")

        call_kwargs = mock_queries.task_state_events.record_state_change.call_args.kwargs
        assert call_kwargs["metadata"] == {"error": "Something went wrong"}


# =============================================================================
# is_task_ready Tests
# =============================================================================


class TestIsTaskReady:
    """Tests for is_task_ready()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_task_with_no_deps_is_ready(self, mock_queries):
        """Task with no dependencies is ready."""

        run_id = uuid4()
        task_id = uuid4()
        experiment_id = uuid4()

        tree = make_task_tree(task_id, depends_on=[])
        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(experiment_id, tree)

        result = is_task_ready(run_id, task_id)

        assert result is True

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_task_with_completed_deps_is_ready(self, mock_queries):
        """Task is ready when all dependencies are completed."""

        run_id = uuid4()
        dep_id = uuid4()
        task_id = uuid4()
        experiment_id = uuid4()

        tree = make_task_tree(
            uuid4(),
            is_leaf=False,
            children=[
                make_task_tree(dep_id, is_leaf=True),
                make_task_tree(task_id, is_leaf=True, depends_on=[dep_id]),
            ],
        )
        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(experiment_id, tree)
        mock_queries.task_state_events.get_current_states.return_value = {
            dep_id: TaskStatus.COMPLETED,
        }

        result = is_task_ready(run_id, task_id)

        assert result is True

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_task_with_pending_deps_is_not_ready(self, mock_queries):
        """Task is not ready when dependencies are not completed."""

        run_id = uuid4()
        dep_id = uuid4()
        task_id = uuid4()
        experiment_id = uuid4()

        tree = make_task_tree(
            uuid4(),
            is_leaf=False,
            children=[
                make_task_tree(dep_id, is_leaf=True),
                make_task_tree(task_id, is_leaf=True, depends_on=[dep_id]),
            ],
        )
        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(experiment_id, tree)
        mock_queries.task_state_events.get_current_states.return_value = {
            dep_id: TaskStatus.PENDING,
        }

        result = is_task_ready(run_id, task_id)

        assert result is False


# =============================================================================
# on_task_completed Tests
# =============================================================================


class TestOnTaskCompleted:
    """Tests for on_task_completed()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_marks_task_completed(self, mock_queries):
        """on_task_completed records a completed state event."""

        run_id = uuid4()
        task_id = uuid4()
        execution_id = uuid4()
        experiment_id = uuid4()

        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(
            experiment_id, make_task_tree(task_id), root_task_id=str(task_id)
        )
        # Mock get_current_states to return task as completed (for propagate_to_parent check)
        mock_queries.task_state_events.get_current_states.return_value = {
            task_id: TaskStatus.COMPLETED
        }

        on_task_completed(run_id, task_id, execution_id)

        # Verify completed event was recorded
        calls = mock_queries.task_state_events.record_state_change.call_args_list
        completed_calls = [c for c in calls if c.kwargs.get("new_status") == "completed"]
        assert len(completed_calls) >= 1

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_returns_ready_tasks(self, mock_queries):
        """on_task_completed returns tasks that are now ready."""

        run_id = uuid4()
        completed_task_id = uuid4()
        waiting_task_id = uuid4()
        execution_id = uuid4()
        experiment_id = uuid4()

        tree = make_task_tree(
            uuid4(),
            is_leaf=False,
            children=[
                make_task_tree(completed_task_id, is_leaf=True),
                make_task_tree(waiting_task_id, is_leaf=True, depends_on=[completed_task_id]),
            ],
        )

        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(
            experiment_id, tree, root_task_id=str(tree["id"])
        )
        # completed_task_id is completed, so waiting_task_id becomes ready
        mock_queries.task_state_events.get_current_states.return_value = {
            completed_task_id: TaskStatus.COMPLETED,
            waiting_task_id: TaskStatus.PENDING,
        }

        result = on_task_completed(run_id, completed_task_id, execution_id)

        assert waiting_task_id in result

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_marks_unblocked_tasks_ready(self, mock_queries):
        """on_task_completed records ready events for unblocked tasks."""

        run_id = uuid4()
        completed_id = uuid4()
        unblocked_id = uuid4()
        execution_id = uuid4()
        experiment_id = uuid4()

        tree = make_task_tree(
            uuid4(),
            is_leaf=False,
            children=[
                make_task_tree(completed_id, is_leaf=True),
                make_task_tree(unblocked_id, is_leaf=True, depends_on=[completed_id]),
            ],
        )

        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(experiment_id, tree)
        # Mock current states: completed_id is done, unblocked_id is pending
        mock_queries.task_state_events.get_current_states.return_value = {
            completed_id: TaskStatus.COMPLETED,
            unblocked_id: TaskStatus.PENDING,
        }

        on_task_completed(run_id, completed_id, execution_id)

        # Verify ready event was recorded for unblocked task
        calls = mock_queries.task_state_events.record_state_change.call_args_list
        ready_calls = [
            c
            for c in calls
            if c.kwargs.get("new_status") == "ready" and c.kwargs.get("task_id") == unblocked_id
        ]
        assert len(ready_calls) == 1

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_does_not_return_task_with_unsatisfied_deps(self, mock_queries):
        """on_task_completed doesn't return tasks that still have unsatisfied dependencies."""

        run_id = uuid4()
        dep1_id = uuid4()
        dep2_id = uuid4()
        waiting_id = uuid4()
        execution_id = uuid4()
        experiment_id = uuid4()

        # waiting_id depends on both dep1 and dep2
        tree = make_task_tree(
            uuid4(),
            is_leaf=False,
            children=[
                make_task_tree(dep1_id, is_leaf=True),
                make_task_tree(dep2_id, is_leaf=True),
                make_task_tree(waiting_id, is_leaf=True, depends_on=[dep1_id, dep2_id]),
            ],
        )

        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(experiment_id, tree)
        # Only dep1 is completed, dep2 is still pending
        mock_queries.task_state_events.get_current_states.return_value = {
            dep1_id: TaskStatus.COMPLETED,
            dep2_id: TaskStatus.PENDING,
            waiting_id: TaskStatus.PENDING,
        }

        result = on_task_completed(run_id, dep1_id, execution_id)

        # waiting_id should NOT be ready (still waiting on dep2)
        assert waiting_id not in result


# =============================================================================
# propagate_to_parent Tests
# =============================================================================


class TestPropagateToParent:
    """Tests for propagate_to_parent()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_marks_parent_complete_when_all_children_done(self, mock_queries):
        """Parent is marked complete when all leaf children are complete."""

        run_id = uuid4()
        parent_id = uuid4()
        child1_id = uuid4()
        child2_id = uuid4()
        experiment_id = uuid4()

        # Build tree: parent has two leaf children
        tree = make_task_tree(
            parent_id,
            name="Parent",
            is_leaf=False,
            children=[
                make_task_tree(child1_id, name="Child1", is_leaf=True, parent_id=parent_id),
                make_task_tree(child2_id, name="Child2", is_leaf=True, parent_id=parent_id),
            ],
        )
        # Set parent_id on children
        tree["children"][0]["parent_id"] = str(parent_id)
        tree["children"][1]["parent_id"] = str(parent_id)

        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(
            experiment_id, tree, root_task_id=str(parent_id)
        )
        # Both children are completed (via event log)
        mock_queries.task_state_events.get_current_states.return_value = {
            parent_id: TaskStatus.PENDING,
            child1_id: TaskStatus.COMPLETED,
            child2_id: TaskStatus.COMPLETED,
        }

        # Call propagate for child1 (child1 just completed)
        result = propagate_to_parent(run_id, child1_id)

        # Parent should be marked completed
        assert result is True
        # Verify completed event was recorded for parent
        calls = mock_queries.task_state_events.record_state_change.call_args_list
        parent_completed = [
            c
            for c in calls
            if c.kwargs.get("task_id") == parent_id and c.kwargs.get("new_status") == "completed"
        ]
        assert len(parent_completed) == 1

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_does_not_mark_parent_if_children_pending(self, mock_queries):
        """Parent stays pending if some children are not complete."""

        run_id = uuid4()
        parent_id = uuid4()
        child1_id = uuid4()
        child2_id = uuid4()
        experiment_id = uuid4()

        tree = make_task_tree(
            parent_id,
            is_leaf=False,
            children=[
                make_task_tree(child1_id, is_leaf=True, parent_id=parent_id),
                make_task_tree(child2_id, is_leaf=True, parent_id=parent_id),
            ],
        )
        tree["children"][0]["parent_id"] = str(parent_id)
        tree["children"][1]["parent_id"] = str(parent_id)

        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(experiment_id, tree)
        # Only child1 is completed
        mock_queries.task_state_events.get_current_states.return_value = {
            parent_id: TaskStatus.PENDING,
            child1_id: TaskStatus.COMPLETED,
            child2_id: TaskStatus.PENDING,  # Still pending
        }

        result = propagate_to_parent(run_id, child1_id)

        assert result is False
        # Verify no completed event was recorded for parent
        calls = mock_queries.task_state_events.record_state_change.call_args_list
        parent_completed = [
            c
            for c in calls
            if c.kwargs.get("task_id") == parent_id and c.kwargs.get("new_status") == "completed"
        ]
        assert len(parent_completed) == 0


# =============================================================================
# Workflow Status Tests
# =============================================================================


class TestIsWorkflowComplete:
    """Tests for is_workflow_complete()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_returns_true_when_all_leaves_complete(self, mock_queries):
        """Returns True when all leaf tasks are COMPLETED."""

        run_id = uuid4()
        leaf1_id = uuid4()
        leaf2_id = uuid4()
        experiment_id = uuid4()

        tree = make_task_tree(
            uuid4(),
            is_leaf=False,
            children=[
                make_task_tree(leaf1_id, is_leaf=True),
                make_task_tree(leaf2_id, is_leaf=True),
            ],
        )

        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(experiment_id, tree)
        # Both leaves completed via event log
        mock_queries.task_state_events.get_current_states.return_value = {
            leaf1_id: TaskStatus.COMPLETED,
            leaf2_id: TaskStatus.COMPLETED,
        }

        result = is_workflow_complete(run_id)

        assert result is True

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_returns_false_when_leaves_pending(self, mock_queries):
        """Returns False when some leaves are not completed."""

        run_id = uuid4()
        leaf1_id = uuid4()
        leaf2_id = uuid4()
        experiment_id = uuid4()

        tree = make_task_tree(
            uuid4(),
            is_leaf=False,
            children=[
                make_task_tree(leaf1_id, is_leaf=True),
                make_task_tree(leaf2_id, is_leaf=True),
            ],
        )

        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(experiment_id, tree)
        # One leaf still running via event log
        mock_queries.task_state_events.get_current_states.return_value = {
            leaf1_id: TaskStatus.COMPLETED,
            leaf2_id: TaskStatus.RUNNING,  # Not complete
        }

        result = is_workflow_complete(run_id)

        assert result is False


class TestIsWorkflowFailed:
    """Tests for is_workflow_failed()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_returns_true_when_any_task_failed(self, mock_queries):
        """Returns True when any task has FAILED status."""

        run_id = uuid4()
        # State from event log shows one failed
        mock_queries.task_state_events.get_current_states.return_value = {
            uuid4(): TaskStatus.COMPLETED,
            uuid4(): TaskStatus.FAILED,  # One failed
        }

        result = is_workflow_failed(run_id)

        assert result is True

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_returns_false_when_no_failures(self, mock_queries):
        """Returns False when no tasks have FAILED status."""

        run_id = uuid4()
        # State from event log shows no failures
        mock_queries.task_state_events.get_current_states.return_value = {
            uuid4(): TaskStatus.COMPLETED,
            uuid4(): TaskStatus.RUNNING,
        }

        result = is_workflow_failed(run_id)

        assert result is False


# =============================================================================
# get_initial_ready_tasks Tests
# =============================================================================


class TestGetInitialReadyTasks:
    """Tests for get_initial_ready_tasks()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_returns_leaves_with_no_deps(self, mock_queries):
        """Returns leaf tasks that have no dependencies."""

        run_id = uuid4()
        leaf1_id = uuid4()
        leaf2_id = uuid4()
        dep_leaf_id = uuid4()
        experiment_id = uuid4()

        # leaf1 and leaf2 have no deps, dep_leaf depends on leaf1
        tree = make_task_tree(
            uuid4(),
            is_leaf=False,
            children=[
                make_task_tree(leaf1_id, is_leaf=True),
                make_task_tree(leaf2_id, is_leaf=True),
                make_task_tree(dep_leaf_id, is_leaf=True, depends_on=[leaf1_id]),
            ],
        )

        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(experiment_id, tree)

        result = get_initial_ready_tasks(run_id)

        # leaf1 and leaf2 have no deps so are ready, dep_leaf has a dep so is not ready
        assert set(result) == {leaf1_id, leaf2_id}
        assert dep_leaf_id not in result

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_returns_empty_when_no_tree(self, mock_queries):
        """Returns empty list when there's no task tree."""

        run_id = uuid4()
        experiment_id = uuid4()

        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(experiment_id, {})

        result = get_initial_ready_tasks(run_id)

        assert result == []

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_single_leaf_with_no_deps(self, mock_queries):
        """Single leaf task with no dependencies is ready."""

        run_id = uuid4()
        task_id = uuid4()
        experiment_id = uuid4()

        tree = make_task_tree(task_id, is_leaf=True, depends_on=[])

        run = make_run(run_id, experiment_id)
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(experiment_id, tree)

        result = get_initial_ready_tasks(run_id)

        assert result == [task_id]
