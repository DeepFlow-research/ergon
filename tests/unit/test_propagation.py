"""Unit tests for the DAG propagation logic."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from h_arcane.core._internal.db.models import TaskStatus


# =============================================================================
# Helper Functions for Tests
# =============================================================================


def make_run(run_id, experiment_id, task_states=None):
    """Create a mock Run object."""
    run = MagicMock()
    run.id = run_id
    run.experiment_id = experiment_id
    run.task_states = task_states or {}
    return run


def make_experiment(experiment_id, task_tree, root_task_id=None):
    """Create a mock Experiment object."""
    exp = MagicMock()
    exp.id = experiment_id
    exp.task_tree = task_tree
    exp.root_task_id = root_task_id or task_tree.get("id")
    return exp


def make_task_tree(task_id, name="Task", children=None, depends_on=None, is_leaf=True, parent_id=None):
    """Create a task_tree dict."""
    return {
        "id": str(task_id),
        "name": name,
        "children": children or [],
        "depends_on": [str(d) for d in (depends_on or [])],
        "is_leaf": is_leaf,
        "parent_id": str(parent_id) if parent_id else None,
    }


# =============================================================================
# get_leaf_descendants Tests
# =============================================================================


class TestGetLeafDescendants:
    """Tests for get_leaf_descendants()."""

    def test_single_leaf_task(self):
        """Single leaf task returns itself."""
        from h_arcane.core._internal.task.propagation import get_leaf_descendants

        task_id = uuid4()
        tree = make_task_tree(task_id, is_leaf=True)

        result = get_leaf_descendants(tree)

        assert result == [str(task_id)]

    def test_composite_with_leaf_children(self):
        """Composite task returns all leaf children."""
        from h_arcane.core._internal.task.propagation import get_leaf_descendants

        child1_id = uuid4()
        child2_id = uuid4()
        parent_id = uuid4()

        tree = make_task_tree(
            parent_id,
            name="Parent",
            is_leaf=False,
            children=[
                make_task_tree(child1_id, name="Child1", is_leaf=True),
                make_task_tree(child2_id, name="Child2", is_leaf=True),
            ],
        )

        result = get_leaf_descendants(tree)

        assert set(result) == {str(child1_id), str(child2_id)}

    def test_nested_tree(self):
        """Nested tree returns deepest leaves."""
        from h_arcane.core._internal.task.propagation import get_leaf_descendants

        leaf1_id = uuid4()
        leaf2_id = uuid4()
        leaf3_id = uuid4()
        mid_id = uuid4()
        root_id = uuid4()

        tree = make_task_tree(
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

        result = get_leaf_descendants(tree)

        assert set(result) == {str(leaf1_id), str(leaf2_id), str(leaf3_id)}


# =============================================================================
# _find_task_in_tree Tests
# =============================================================================


class TestFindTaskInTree:
    """Tests for _find_task_in_tree()."""

    def test_find_root_task(self):
        """Find the root task."""
        from h_arcane.core._internal.task.propagation import _find_task_in_tree

        task_id = uuid4()
        tree = make_task_tree(task_id, name="Root")

        result = _find_task_in_tree(tree, str(task_id))

        assert result is not None
        assert result["name"] == "Root"

    def test_find_nested_task(self):
        """Find a deeply nested task."""
        from h_arcane.core._internal.task.propagation import _find_task_in_tree

        target_id = uuid4()
        root_id = uuid4()
        mid_id = uuid4()

        tree = make_task_tree(
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

        result = _find_task_in_tree(tree, str(target_id))

        assert result is not None
        assert result["name"] == "Target"

    def test_task_not_found(self):
        """Return None if task not in tree."""
        from h_arcane.core._internal.task.propagation import _find_task_in_tree

        tree = make_task_tree(uuid4(), name="Root")
        missing_id = uuid4()

        result = _find_task_in_tree(tree, str(missing_id))

        assert result is None


# =============================================================================
# extract_dependencies_from_tree Tests
# =============================================================================


class TestExtractDependenciesFromTree:
    """Tests for extract_dependencies_from_tree()."""

    def test_no_dependencies(self):
        """Task with no dependencies returns empty list."""
        from h_arcane.core._internal.task.propagation import extract_dependencies_from_tree

        tree = make_task_tree(uuid4(), depends_on=[])

        result = extract_dependencies_from_tree(tree)

        assert result == []

    def test_single_dependency(self):
        """Task with one dependency."""
        from h_arcane.core._internal.task.propagation import extract_dependencies_from_tree

        dep_id = uuid4()
        task_id = uuid4()

        tree = make_task_tree(
            uuid4(),
            name="Root",
            is_leaf=False,
            children=[
                make_task_tree(dep_id, name="Dep"),
                make_task_tree(task_id, name="Task", depends_on=[dep_id]),
            ],
        )

        result = extract_dependencies_from_tree(tree)

        assert (task_id, dep_id) in result

    def test_multiple_dependencies(self):
        """Task with multiple dependencies."""
        from h_arcane.core._internal.task.propagation import extract_dependencies_from_tree

        dep1_id = uuid4()
        dep2_id = uuid4()
        task_id = uuid4()

        tree = make_task_tree(
            uuid4(),
            name="Root",
            is_leaf=False,
            children=[
                make_task_tree(dep1_id, name="Dep1"),
                make_task_tree(dep2_id, name="Dep2"),
                make_task_tree(task_id, name="Task", depends_on=[dep1_id, dep2_id]),
            ],
        )

        result = extract_dependencies_from_tree(tree)

        assert (task_id, dep1_id) in result
        assert (task_id, dep2_id) in result


# =============================================================================
# State Update Functions Tests (with mocking)
# =============================================================================


class TestMarkTaskReady:
    """Tests for mark_task_ready()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_updates_task_state(self, mock_queries):
        """mark_task_ready updates Run.task_states."""
        from h_arcane.core._internal.task.propagation import mark_task_ready

        run_id = uuid4()
        task_id = uuid4()
        run = make_run(run_id, uuid4(), task_states={str(task_id): "pending"})
        mock_queries.runs.get.return_value = run

        mark_task_ready(run_id, task_id, triggered_by="test")

        # Should update task_states
        assert run.task_states[str(task_id)] == "ready"
        mock_queries.runs.update.assert_called_once_with(run)

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_records_state_event(self, mock_queries):
        """mark_task_ready records a TaskStateEvent."""
        from h_arcane.core._internal.task.propagation import mark_task_ready

        run_id = uuid4()
        task_id = uuid4()
        run = make_run(run_id, uuid4(), task_states={})
        mock_queries.runs.get.return_value = run

        mark_task_ready(run_id, task_id, triggered_by="dependency_satisfied")

        mock_queries.task_state_events.record.assert_called_once()
        call_kwargs = mock_queries.task_state_events.record.call_args.kwargs
        assert call_kwargs["run_id"] == run_id
        assert call_kwargs["task_id"] == task_id
        assert call_kwargs["new_status"] == "ready"
        assert call_kwargs["triggered_by"] == "dependency_satisfied"


class TestMarkTaskFailed:
    """Tests for mark_task_failed()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_includes_error_in_metadata(self, mock_queries):
        """mark_task_failed includes error in event metadata."""
        from h_arcane.core._internal.task.propagation import mark_task_failed

        run_id = uuid4()
        task_id = uuid4()
        run = make_run(run_id, uuid4(), task_states={})
        mock_queries.runs.get.return_value = run

        mark_task_failed(run_id, task_id, error="Something went wrong")

        call_kwargs = mock_queries.task_state_events.record.call_args.kwargs
        assert call_kwargs["metadata"] == {"error": "Something went wrong"}


# =============================================================================
# is_task_ready Tests
# =============================================================================


class TestIsTaskReady:
    """Tests for is_task_ready()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_delegates_to_query(self, mock_queries):
        """is_task_ready delegates to TaskDependencyQueries."""
        from h_arcane.core._internal.task.propagation import is_task_ready

        run_id = uuid4()
        task_id = uuid4()
        mock_queries.task_dependencies.is_task_unblocked.return_value = True

        result = is_task_ready(run_id, task_id)

        assert result is True
        mock_queries.task_dependencies.is_task_unblocked.assert_called_once_with(
            run_id, task_id
        )


# =============================================================================
# on_task_completed Tests
# =============================================================================


class TestOnTaskCompleted:
    """Tests for on_task_completed()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_marks_task_completed(self, mock_queries):
        """on_task_completed marks the task as completed."""
        from h_arcane.core._internal.task.propagation import on_task_completed

        run_id = uuid4()
        task_id = uuid4()
        execution_id = uuid4()
        experiment_id = uuid4()

        run = make_run(run_id, experiment_id, task_states={str(task_id): "running"})
        mock_queries.runs.get.return_value = run
        mock_queries.task_dependencies.mark_satisfied.return_value = []
        mock_queries.experiments.get.return_value = make_experiment(
            experiment_id, make_task_tree(task_id), root_task_id=str(task_id)
        )

        on_task_completed(run_id, task_id, execution_id)

        # Task should be marked completed
        assert run.task_states[str(task_id)] == "completed"

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_returns_ready_tasks(self, mock_queries):
        """on_task_completed returns tasks that are now ready."""
        from h_arcane.core._internal.task.propagation import on_task_completed

        run_id = uuid4()
        completed_task_id = uuid4()
        waiting_task_id = uuid4()
        execution_id = uuid4()
        experiment_id = uuid4()

        run = make_run(run_id, experiment_id, task_states={
            str(completed_task_id): "running",
            str(waiting_task_id): "pending",
        })
        mock_queries.runs.get.return_value = run

        # waiting_task_id becomes unblocked when completed_task_id completes
        mock_queries.task_dependencies.mark_satisfied.return_value = [waiting_task_id]
        mock_queries.task_dependencies.is_task_unblocked.return_value = True

        tree = make_task_tree(
            uuid4(),
            is_leaf=False,
            children=[
                make_task_tree(completed_task_id, is_leaf=True),
                make_task_tree(waiting_task_id, is_leaf=True, depends_on=[completed_task_id]),
            ],
        )
        mock_queries.experiments.get.return_value = make_experiment(
            experiment_id, tree, root_task_id=str(tree["id"])
        )

        result = on_task_completed(run_id, completed_task_id, execution_id)

        assert waiting_task_id in result

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_marks_unblocked_tasks_ready(self, mock_queries):
        """on_task_completed marks unblocked tasks as READY."""
        from h_arcane.core._internal.task.propagation import on_task_completed

        run_id = uuid4()
        completed_id = uuid4()
        unblocked_id = uuid4()
        execution_id = uuid4()
        experiment_id = uuid4()

        run = make_run(run_id, experiment_id, task_states={
            str(completed_id): "running",
            str(unblocked_id): "pending",
        })
        mock_queries.runs.get.return_value = run
        mock_queries.task_dependencies.mark_satisfied.return_value = [unblocked_id]
        mock_queries.task_dependencies.is_task_unblocked.return_value = True
        mock_queries.experiments.get.return_value = make_experiment(
            experiment_id, 
            make_task_tree(uuid4(), children=[
                make_task_tree(completed_id),
                make_task_tree(unblocked_id, depends_on=[completed_id]),
            ]),
        )

        on_task_completed(run_id, completed_id, execution_id)

        # Unblocked task should now be READY
        assert run.task_states[str(unblocked_id)] == "ready"


# =============================================================================
# propagate_to_parent Tests
# =============================================================================


class TestPropagateToParent:
    """Tests for propagate_to_parent()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_marks_parent_complete_when_all_children_done(self, mock_queries):
        """Parent is marked complete when all leaf children are complete."""
        from h_arcane.core._internal.task.propagation import propagate_to_parent

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

        # Both children are completed
        run = make_run(run_id, experiment_id, task_states={
            str(parent_id): "pending",
            str(child1_id): "completed",
            str(child2_id): "completed",
        })
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(
            experiment_id, tree, root_task_id=str(parent_id)
        )

        # Call propagate for child1 (child1 just completed)
        result = propagate_to_parent(run_id, child1_id)

        # Parent should be marked completed
        assert result is True
        assert run.task_states[str(parent_id)] == "completed"

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_does_not_mark_parent_if_children_pending(self, mock_queries):
        """Parent stays pending if some children are not complete."""
        from h_arcane.core._internal.task.propagation import propagate_to_parent

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

        # Only child1 is completed
        run = make_run(run_id, experiment_id, task_states={
            str(parent_id): "pending",
            str(child1_id): "completed",
            str(child2_id): "pending",  # Still pending
        })
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(
            experiment_id, tree
        )

        result = propagate_to_parent(run_id, child1_id)

        assert result is False
        assert run.task_states[str(parent_id)] == "pending"


# =============================================================================
# Workflow Status Tests
# =============================================================================


class TestIsWorkflowComplete:
    """Tests for is_workflow_complete()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_returns_true_when_all_leaves_complete(self, mock_queries):
        """Returns True when all leaf tasks are COMPLETED."""
        from h_arcane.core._internal.task.propagation import is_workflow_complete

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

        run = make_run(run_id, experiment_id, task_states={
            str(leaf1_id): "completed",
            str(leaf2_id): "completed",
        })
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(experiment_id, tree)

        result = is_workflow_complete(run_id)

        assert result is True

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_returns_false_when_leaves_pending(self, mock_queries):
        """Returns False when some leaves are not completed."""
        from h_arcane.core._internal.task.propagation import is_workflow_complete

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

        run = make_run(run_id, experiment_id, task_states={
            str(leaf1_id): "completed",
            str(leaf2_id): "running",  # Not complete
        })
        mock_queries.runs.get.return_value = run
        mock_queries.experiments.get.return_value = make_experiment(experiment_id, tree)

        result = is_workflow_complete(run_id)

        assert result is False


class TestIsWorkflowFailed:
    """Tests for is_workflow_failed()."""

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_returns_true_when_any_task_failed(self, mock_queries):
        """Returns True when any task has FAILED status."""
        from h_arcane.core._internal.task.propagation import is_workflow_failed

        run_id = uuid4()
        run = make_run(run_id, uuid4(), task_states={
            str(uuid4()): "completed",
            str(uuid4()): "failed",  # One failed
        })
        mock_queries.runs.get.return_value = run

        result = is_workflow_failed(run_id)

        assert result is True

    @patch("h_arcane.core._internal.task.propagation.queries")
    def test_returns_false_when_no_failures(self, mock_queries):
        """Returns False when no tasks have FAILED status."""
        from h_arcane.core._internal.task.propagation import is_workflow_failed

        run_id = uuid4()
        run = make_run(run_id, uuid4(), task_states={
            str(uuid4()): "completed",
            str(uuid4()): "running",
        })
        mock_queries.runs.get.return_value = run

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
        from h_arcane.core._internal.task.propagation import get_initial_ready_tasks

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

        # leaf1 and leaf2 are ready (no blocking deps), dep_leaf is blocked
        def is_unblocked(rid, tid):
            return tid in [leaf1_id, leaf2_id]

        mock_queries.task_dependencies.is_task_unblocked.side_effect = is_unblocked

        result = get_initial_ready_tasks(run_id)

        assert set(result) == {leaf1_id, leaf2_id}
        assert dep_leaf_id not in result
