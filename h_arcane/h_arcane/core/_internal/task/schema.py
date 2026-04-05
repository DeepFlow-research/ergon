"""
Typed schema for serialized task trees.

This module provides Pydantic models for the JSON-serialized task tree
structure stored in Experiment.task_tree. Using typed models instead of
raw dicts enables static type checking and catches typos/refactoring errors.

The TaskTreeNode mirrors the structure created by serialize_task_tree()
in persistence.py.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class WorkerRef(BaseModel):
    """
    Serialized reference to a worker.

    This is the JSON representation of a BaseWorker for storage/display.
    The actual worker instance is retrieved from worker_context at runtime.
    """

    id: UUID = Field(description="Worker UUID")
    name: str = Field(description="Human-readable worker name")
    type: str = Field(description="Worker class name for display/debugging")


class ResourceRef(BaseModel):
    """
    Serialized reference to a resource.

    This mirrors the SDK Resource model's JSON representation.
    """

    path: str | None = None
    name: str
    content: str | None = None
    url: str | None = None
    mime_type: str | None = Field(default=None, alias="mime_type_override")

    model_config = {"populate_by_name": True}


class EvaluatorRef(BaseModel):
    """
    Serialized reference to an evaluator/rubric.

    Contains the evaluator type and its full configuration.
    The 'type' field is the discriminator for deserialization.
    """

    type: str = Field(description="Evaluator type (e.g., 'StagedRubric', 'MiniF2FRubric')")

    model_config = {"extra": "allow"}  # Allow additional config fields


class TaskTreeNode(BaseModel):
    """
    Typed representation of a serialized task in the task tree.

    This model represents the JSON structure stored in Experiment.task_tree.
    It enables type-safe access to task properties without using dict.get()
    with string keys.

    The structure mirrors what serialize_task_tree() produces from a Task.
    """

    # === Identity ===
    id: UUID = Field(description="Task UUID")
    name: str = Field(description="Human-readable task name")
    description: str = Field(description="Task description/instructions")

    # === Worker Assignment ===
    assigned_to: WorkerRef = Field(description="Primary worker assigned to this task")
    full_team: list[WorkerRef] | None = Field(
        default=None,
        description="Full team of workers (if collaborative task)",
    )

    # === DAG Structure ===
    children: list[TaskTreeNode] = Field(
        default_factory=list,
        description="Child tasks (empty for leaf tasks)",
    )
    depends_on: list[UUID] = Field(
        default_factory=list,
        description="Task UUIDs this task depends on",
    )
    parent_id: UUID | None = Field(
        default=None,
        description="Parent task UUID (None for root)",
    )

    # === Computed Properties ===
    is_leaf: bool = Field(
        default=True,
        description="True if this is an atomic task with no children",
    )

    # === I/O ===
    resources: list[ResourceRef] = Field(
        default_factory=list,
        description="Input resources for this task",
    )

    # === Evaluation ===
    evaluator: EvaluatorRef | None = Field(
        default=None,
        description="Evaluator/rubric configuration (if any)",
    )
    evaluator_type: str | None = Field(
        default=None,
        description="Evaluator class name for quick reference",
    )

    model_config = {"extra": "ignore"}  # Ignore unexpected fields for forward compatibility

    # === Tree Traversal Helpers ===

    def find_by_id(self, task_id: UUID | str) -> TaskTreeNode | None:
        """
        Find a task by ID in this subtree.

        Args:
            task_id: The task UUID or string to find

        Returns:
            TaskTreeNode if found, None otherwise
        """
        tid = task_id if isinstance(task_id, UUID) else UUID(task_id)
        if self.id == tid:
            return self
        for child in self.children:
            found = child.find_by_id(tid)
            if found:
                return found
        return None

    def get_all_leaves(self) -> list[TaskTreeNode]:
        """
        Get all leaf tasks in this subtree.

        Returns:
            List of TaskTreeNode instances that are leaves (is_leaf=True)
        """
        if self.is_leaf or not self.children:
            return [self]
        leaves: list[TaskTreeNode] = []
        for child in self.children:
            leaves.extend(child.get_all_leaves())
        return leaves

    def get_leaf_ids(self) -> list[UUID]:
        """
        Get all leaf task IDs in this subtree.

        Returns:
            List of task UUIDs for all leaf tasks
        """
        return [leaf.id for leaf in self.get_all_leaves()]

    def walk(self) -> list[TaskTreeNode]:
        """
        Walk the tree depth-first, yielding all nodes.

        Returns:
            List of all TaskTreeNode instances in the subtree
        """
        nodes = [self]
        for child in self.children:
            nodes.extend(child.walk())
        return nodes

    def extract_dependencies(self) -> list[tuple[UUID, UUID]]:
        """
        Extract all dependency edges from this subtree.

        Returns:
            List of (dependent_task_id, dependency_task_id) tuples
        """
        dependencies: list[tuple[UUID, UUID]] = []
        for node in self.walk():
            for dep_id in node.depends_on:
                dependencies.append((node.id, dep_id))
        return dependencies

    def extract_evaluators(self) -> list[tuple[UUID, EvaluatorRef]]:
        """
        Extract all evaluator configs from this subtree.

        Returns:
            List of (task_id, evaluator_config) tuples for tasks with evaluators
        """
        evaluators: list[tuple[UUID, EvaluatorRef]] = []
        for node in self.walk():
            if node.evaluator:
                evaluators.append((node.id, node.evaluator))
        return evaluators

    def get_dependents(self, task_id: UUID | str) -> list[UUID]:
        """
        Find all task IDs that depend on the given task.

        This is the reverse lookup of depends_on - finds all tasks
        that have task_id in their depends_on list.

        Args:
            task_id: The task UUID or string to find dependents for

        Returns:
            List of task UUIDs that depend on task_id
        """
        tid = task_id if isinstance(task_id, UUID) else UUID(task_id)
        dependents: list[UUID] = []
        for node in self.walk():
            if tid in node.depends_on:
                dependents.append(node.id)
        return dependents

    def get_dependencies(self, task_id: UUID | str) -> list[UUID]:
        """
        Get the dependencies for a specific task.

        Args:
            task_id: The task UUID or string

        Returns:
            List of task UUIDs this task depends on, or empty list if not found
        """
        node = self.find_by_id(task_id)
        if node is None:
            return []
        return node.depends_on


def parse_task_tree(data: dict | None) -> TaskTreeNode | None:
    """
    Parse a raw dict task_tree into a typed TaskTreeNode.

    This is the primary entry point for converting untyped task_tree
    data (from database) into typed objects.

    Args:
        data: Raw dict from Experiment.task_tree, or None

    Returns:
        TaskTreeNode if data is valid, None if data is None or empty
    """
    if not data:
        return None
    return TaskTreeNode.model_validate(data)
