"""
User-facing Task model and related types.

This is the PUBLIC API for defining tasks and workflows.

Usage:
    from h_arcane import Task, Resource, TaskStatus
    
    task = Task(
        name="Analyze Data",
        description="Process the quarterly report",
        assigned_to=worker,
        resources=[Resource(path="data/report.xlsx", name="Quarterly Report")],
    )
"""

from __future__ import annotations

import mimetypes
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_serializer

if TYPE_CHECKING:
    from h_arcane.core.worker import BaseWorker


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"  # Not ready (dependencies not met)
    READY = "ready"  # Dependencies satisfied, waiting for execution
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Execution failed


class Resource(BaseModel):
    """
    A file resource for task input.

    Users provide path, name, content, or url.
    MIME type is derived from file extension if path provided.

    NOTE: This is the SDK type. The DB type with the same name lives in
    h_arcane._internal.db.models (namespace separation pattern).

    Examples:
        # From file path
        Resource(path="data/report.xlsx", name="Quarterly Report")

        # From inline content
        Resource(name="config.json", content='{"key": "value"}')

        # With explicit MIME type
        Resource(path="data/custom.bin", name="Binary Data", mime_type="application/octet-stream")
    """

    path: str | Path | None = None
    name: str
    content: str | bytes | None = None
    url: str | None = None
    mime_type_override: str | None = Field(default=None, alias="mime_type")

    model_config = {"populate_by_name": True}

    @property
    def mime_type(self) -> str:
        """Derive MIME type from file extension or use override."""
        if self.mime_type_override:
            return self.mime_type_override
        if self.path:
            mime, _ = mimetypes.guess_type(str(self.path))
            return mime or "application/octet-stream"
        return "text/plain"


class Task(BaseModel):
    """
    A unit of work - can be atomic or a DAG of subtasks.

    This is the core primitive for defining both single tasks and complex workflows.
    A "workflow" is simply a Task with children.

    Examples:
        # Single task
        task = Task(
            name="Analyze sales data",
            description="Load the Q4 sales data and compute year-over-year growth rates.",
            assigned_to=analyst_worker,
            resources=[Resource(path="data/sales_q4.xlsx", name="Q4 Sales")],
        )

        # Workflow with dependencies
        research = Task(
            name="Research",
            description="Gather data on competitor pricing from the provided URLs.",
            assigned_to=researcher,
        )
        write = Task(
            name="Write Report",
            description="Synthesize research findings into a 2-page executive summary.",
            assigned_to=writer,
            depends_on=[research],  # Waits for research to complete
        )
        workflow = Task(
            name="Competitive Analysis",
            description="Full competitive analysis workflow.",
            assigned_to=manager,
            children=[research, write],
        )

        # Collaborative task (multiple workers)
        task = Task(
            name="Code Review",
            description="Review PR #123 for security issues.",
            assigned_to=lead_reviewer,
            full_team=[lead_reviewer, security_expert, junior_dev],
        )
    """

    # === Identity ===
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique task identifier. Auto-generated if not provided.",
    )
    name: str = Field(
        ...,
        description="Short, human-readable task name for display and logging.",
    )
    description: str = Field(
        ...,
        description=(
            "Detailed instructions for the worker. This is the main input the worker "
            "receives - be specific about what outcome you expect."
        ),
    )

    # === Worker Assignment ===
    assigned_to: "BaseWorker" = Field(
        ...,
        description=(
            "The worker responsible for executing this task. Pass a worker instance "
            "(e.g., ReactWorker, DummyWorker) that implements the BaseWorker protocol."
        ),
    )
    full_team: list["BaseWorker"] | None = Field(
        default=None,
        description=(
            "Use when multiple workers need to collaborate on a single task. "
            "All workers in the team can contribute actions. If not set, only "
            "assigned_to executes. Example: a researcher and writer collaborating."
        ),
    )

    # === DAG Structure ===
    children: list["Task"] = Field(
        default_factory=list,
        description=(
            "Subtasks that make this a composite task (workflow). Use when a task "
            "naturally breaks into sequential or parallel steps. The parent task "
            "completes when all children complete."
        ),
    )
    depends_on: list["Task | UUID"] = Field(
        default_factory=list,
        description=(
            "Tasks that must complete before this one starts. Use for ordering "
            "between sibling tasks. Pass Task objects directly - UUIDs are resolved "
            "internally. Example: writing depends on research completing first."
        ),
    )

    # === I/O ===
    resources: list[Resource] = Field(
        default_factory=list,
        description=(
            "Input files/data for the worker. These become available in the worker's "
            "sandbox. Use Resource(path=...) for files, Resource(content=...) for inline data."
        ),
    )

    # === Evaluation ===
    # Note: typed as Any because AnyRubric has heavy benchmark dependencies
    evaluator: Any = Field(
        default=None,
        description=(
            "Rubric to score task outputs on completion. Use when you need automated "
            "quality assessment. Pass a StagedRubric, MiniF2FRubric, or custom evaluator."
        ),
    )

    # === Internal State (managed by system, not user) ===
    parent_id: UUID | None = Field(default=None, exclude=True)
    status: TaskStatus = Field(default=TaskStatus.PENDING, exclude=True)

    # Resolved dependency IDs (set by TaskRegistry during processing)
    _resolved_dependency_ids: list[UUID] = []

    model_config = {"arbitrary_types_allowed": True}

    # === Field Serializers (for model_dump()) ===

    @field_serializer("assigned_to")
    @staticmethod
    def serialize_assigned_to(worker: "BaseWorker") -> dict:
        """Serialize worker to ID + metadata for reconstruction."""
        return {
            "id": str(worker.id),
            "name": getattr(worker, "name", "unknown"),
            "type": type(worker).__name__,
        }

    @field_serializer("full_team")
    @staticmethod
    def serialize_full_team(team: list["BaseWorker"] | None) -> list[dict] | None:
        """Serialize team of workers."""
        if team is None:
            return None
        return [
            {
                "id": str(w.id),
                "name": getattr(w, "name", "unknown"),
                "type": type(w).__name__,
            }
            for w in team
        ]

    @field_serializer("depends_on")
    @staticmethod
    def serialize_depends_on(deps: list["Task | UUID"]) -> list[str]:
        """Serialize dependencies to UUIDs."""
        return [str(dep.id) if isinstance(dep, Task) else str(dep) for dep in deps]

    @field_serializer("evaluator")
    @staticmethod
    def serialize_evaluator(evaluator: Any) -> dict | None:
        """Serialize evaluator to type info."""
        if evaluator is None:
            return None
        return {"type": type(evaluator).__name__}

    # === Computed Properties ===

    @property
    def is_leaf(self) -> bool:
        """True if this is an atomic task with no children."""
        return len(self.children) == 0

    @property
    def is_composite(self) -> bool:
        """True if this task has children (is a sub-workflow)."""
        return len(self.children) > 0

    @property
    def dependency_ids(self) -> list[UUID]:
        """Resolve depends_on to UUIDs."""
        return [dep.id if isinstance(dep, Task) else dep for dep in self.depends_on]

    @property
    def effective_team(self) -> list["BaseWorker"]:
        """Get all workers that can work on this task."""
        if self.full_team:
            return self.full_team
        return [self.assigned_to]

    def get_all_descendants(self) -> list["Task"]:
        """Get all descendant tasks (children, grandchildren, etc.)."""
        descendants = []
        for child in self.children:
            descendants.append(child)
            descendants.extend(child.get_all_descendants())
        return descendants

    def get_leaf_descendants(self) -> list["Task"]:
        """Get all leaf (atomic) tasks in this subtree."""
        if self.is_leaf:
            return [self]
        leaves = []
        for child in self.children:
            leaves.extend(child.get_leaf_descendants())
        return leaves
