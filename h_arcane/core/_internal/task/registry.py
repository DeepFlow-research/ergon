"""
TaskRegistry - DAG processing and validation for task trees.

The TaskRegistry is responsible for:
1. Flattening a hierarchical task tree into a flat registry (id → Task)
2. Resolving dependencies (Task objects → UUIDs)
3. Validating the DAG (no cycles, all deps exist)
4. Computing initial task statuses (which tasks are READY)
5. Providing queries over the task graph
"""

from __future__ import annotations

from uuid import UUID

from h_arcane.core.task import Task, TaskStatus


class TaskRegistryError(Exception):
    """Base exception for TaskRegistry errors."""

    pass


class CycleDetectedError(TaskRegistryError):
    """Raised when a cycle is detected in the task dependency graph."""

    def __init__(self, cycle_path: list[str] | None = None):
        self.cycle_path = cycle_path
        if cycle_path:
            msg = f"Cycle detected in task dependency graph: {' → '.join(cycle_path)}"
        else:
            msg = "Cycle detected in task dependency graph"
        super().__init__(msg)


class MissingDependencyError(TaskRegistryError):
    """Raised when a task depends on a non-existent task."""

    def __init__(self, task_name: str, task_id: UUID, missing_dep_id: UUID):
        self.task_name = task_name
        self.task_id = task_id
        self.missing_dep_id = missing_dep_id
        super().__init__(
            f"Task '{task_name}' (id={task_id}) depends on task ID {missing_dep_id} "
            f"which is not in the task tree"
        )


class TaskRegistry:
    """
    Manages the flattened view of a task tree.

    Handles resolution, validation, and status computation for a DAG of tasks.

    Usage:
        root = Task(name="Root", children=[a, b, c])
        registry = TaskRegistry(root)

        # Query the registry
        ready_tasks = registry.get_ready_tasks()
        leaf_tasks = registry.get_leaf_tasks()
        task = registry.get_task(some_uuid)

    Attributes:
        root_id: UUID of the root task
        tasks: Mapping of task_id → Task for all tasks in the tree
    """

    def __init__(self, root_task: Task):
        """
        Initialize registry from a root task.

        Performs full DAG processing:
        1. Flatten tree into registry
        2. Resolve dependencies (Task → UUID)
        3. Validate DAG (no cycles, deps exist)
        4. Compute initial statuses

        Args:
            root_task: The root task (may have children)

        Raises:
            CycleDetectedError: If dependency graph contains a cycle
            MissingDependencyError: If a task depends on non-existent task
        """
        self.root_id = root_task.id
        self.tasks: dict[UUID, Task] = {}

        # Process the tree
        self._flatten_tree(root_task, parent_id=None)
        self._resolve_dependencies()
        self._validate_dag()
        self._compute_initial_statuses()

    def _flatten_tree(self, task: Task, parent_id: UUID | None) -> None:
        """
        Recursively flatten task tree into registry.

        Sets parent_id on each task and adds to self.tasks.
        """
        task.parent_id = parent_id
        self.tasks[task.id] = task

        for child in task.children:
            self._flatten_tree(child, parent_id=task.id)

    def _resolve_dependencies(self) -> None:
        """
        Convert Task object dependencies to UUIDs and validate they exist.

        Populates task._resolved_dependency_ids for each task.

        Raises:
            MissingDependencyError: If a dependency doesn't exist in tree
        """
        for task in self.tasks.values():
            resolved_deps: list[UUID] = []

            for dep in task.depends_on:
                if isinstance(dep, Task):
                    dep_id = dep.id
                else:
                    dep_id = dep  # Already a UUID

                # Validate dependency exists in tree
                if dep_id not in self.tasks:
                    raise MissingDependencyError(
                        task_name=task.name,
                        task_id=task.id,
                        missing_dep_id=dep_id,
                    )

                resolved_deps.append(dep_id)

            # Store resolved UUIDs
            task._resolved_dependency_ids = resolved_deps

    def _validate_dag(self) -> None:
        """
        Ensure no cycles in dependency graph using DFS.

        Raises:
            CycleDetectedError: If a cycle is detected
        """
        visited: set[UUID] = set()
        rec_stack: set[UUID] = set()
        path: list[str] = []

        def has_cycle(task_id: UUID) -> bool:
            """DFS to detect cycles."""
            task = self.tasks[task_id]
            visited.add(task_id)
            rec_stack.add(task_id)
            path.append(task.name)

            for dep_id in task._resolved_dependency_ids:
                if dep_id not in visited:
                    if has_cycle(dep_id):
                        return True
                elif dep_id in rec_stack:
                    # Found a cycle - dep is in current recursion stack
                    # Try to find the cycle path
                    dep_task = self.tasks[dep_id]
                    path.append(dep_task.name)
                    return True

            rec_stack.remove(task_id)
            path.pop()
            return False

        for task_id in self.tasks:
            if task_id not in visited:
                if has_cycle(task_id):
                    raise CycleDetectedError(cycle_path=path if path else None)

    def _compute_initial_statuses(self) -> None:
        """
        Mark tasks with no dependencies as READY.

        Only leaf tasks can be READY initially.
        Composite tasks wait for their children.
        """
        for task in self.tasks.values():
            # Only leaf tasks can be immediately READY
            if task.is_leaf and not task._resolved_dependency_ids:
                task.status = TaskStatus.READY
            else:
                task.status = TaskStatus.PENDING

    # === Query Methods ===

    def get_task(self, task_id: UUID) -> Task | None:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def get_root(self) -> Task:
        """Get the root task."""
        return self.tasks[self.root_id]

    def get_leaf_tasks(self) -> list[Task]:
        """Get all leaf (atomic) tasks."""
        return [t for t in self.tasks.values() if t.is_leaf]

    def get_ready_tasks(self) -> list[Task]:
        """Get tasks that are ready to execute."""
        return [t for t in self.tasks.values() if t.status == TaskStatus.READY]

    def get_pending_tasks(self) -> list[Task]:
        """Get tasks that are pending (waiting on dependencies)."""
        return [t for t in self.tasks.values() if t.status == TaskStatus.PENDING]

    def get_running_tasks(self) -> list[Task]:
        """Get tasks that are currently running."""
        return [t for t in self.tasks.values() if t.status == TaskStatus.RUNNING]

    def get_completed_tasks(self) -> list[Task]:
        """Get tasks that have completed."""
        return [t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED]

    def get_failed_tasks(self) -> list[Task]:
        """Get tasks that have failed."""
        return [t for t in self.tasks.values() if t.status == TaskStatus.FAILED]

    def get_dependents(self, task_id: UUID) -> list[Task]:
        """
        Get tasks that depend on the given task.

        These are the tasks that are waiting for task_id to complete.
        """
        return [t for t in self.tasks.values() if task_id in t._resolved_dependency_ids]

    def get_dependencies(self, task_id: UUID) -> list[Task]:
        """
        Get tasks that the given task depends on.

        These are the tasks that must complete before task_id can run.
        """
        task = self.tasks.get(task_id)
        if not task:
            return []
        return [self.tasks[dep_id] for dep_id in task._resolved_dependency_ids]

    def get_children(self, task_id: UUID) -> list[Task]:
        """Get direct children of a task."""
        task = self.tasks.get(task_id)
        if not task:
            return []
        return task.children

    def get_parent(self, task_id: UUID) -> Task | None:
        """Get the parent of a task."""
        task = self.tasks.get(task_id)
        if not task or not task.parent_id:
            return None
        return self.tasks.get(task.parent_id)

    def is_all_complete(self) -> bool:
        """Check if all tasks are completed."""
        return all(t.status == TaskStatus.COMPLETED for t in self.tasks.values())

    def is_any_failed(self) -> bool:
        """Check if any task has failed."""
        return any(t.status == TaskStatus.FAILED for t in self.tasks.values())

    def get_blocking_dependencies(self, task_id: UUID) -> list[Task]:
        """
        Get dependencies that are blocking a task from running.

        Returns dependencies that are not yet COMPLETED.
        """
        task = self.tasks.get(task_id)
        if not task:
            return []

        return [
            self.tasks[dep_id]
            for dep_id in task._resolved_dependency_ids
            if self.tasks[dep_id].status != TaskStatus.COMPLETED
        ]

    def can_run(self, task_id: UUID) -> bool:
        """
        Check if a task can run (all dependencies satisfied).

        A task can run if:
        1. It's a leaf task (or we're executing composites)
        2. All its dependencies are COMPLETED
        """
        task = self.tasks.get(task_id)
        if not task:
            return False

        # Already running or done
        if task.status in (TaskStatus.RUNNING, TaskStatus.COMPLETED, TaskStatus.FAILED):
            return False

        # Check dependencies
        return len(self.get_blocking_dependencies(task_id)) == 0

    # === Serialization ===

    def to_dict(self) -> dict:
        """
        Serialize the task tree to a dict.

        Useful for persisting to database.
        """
        return self._serialize_task(self.get_root())

    def _serialize_task(self, task: Task) -> dict:
        """Recursively serialize a task to dict."""
        return {
            "id": str(task.id),
            "name": task.name,
            "description": task.description,
            "depends_on": [str(dep_id) for dep_id in task._resolved_dependency_ids],
            "resources": [
                {
                    "name": r.name,
                    "path": str(r.path) if r.path else None,
                    "mime_type": r.mime_type,
                }
                for r in task.resources
            ],
            "children": [self._serialize_task(child) for child in task.children],
            "is_leaf": task.is_leaf,
            "parent_id": str(task.parent_id) if task.parent_id else None,
        }

    def __len__(self) -> int:
        """Number of tasks in the registry."""
        return len(self.tasks)

    def __contains__(self, task_id: UUID) -> bool:
        """Check if a task ID is in the registry."""
        return task_id in self.tasks

    def __iter__(self):
        """Iterate over all tasks."""
        return iter(self.tasks.values())
