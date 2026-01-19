"""
Persistence layer for converting SDK types to DB records.

This module handles the conversion of user-facing SDK types (Task, Resource)
to database records (Experiment, Run, Resource).
"""

from __future__ import annotations

import mimetypes
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from h_arcane.core._internal.db.models import (
    Action,
    Experiment,
    ResourceRecord,
    Run,
    TaskExecution,
)
from h_arcane.core._internal.db.queries import queries
from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.core.task import Resource as SDKResource
from h_arcane.core.task import Task
from h_arcane.core._internal.task.schema import TaskTreeNode

if TYPE_CHECKING:
    from h_arcane.core._internal.agents.registry import AgentRegistry
    from h_arcane.core._internal.task.registry import TaskRegistry


# =============================================================================
# Task Tree Serialization
# =============================================================================


def serialize_task_tree(task: Task) -> TaskTreeNode:
    """
    Serialize a task tree to a typed TaskTreeNode.

    Uses Pydantic's model_dump() with field serializers defined on Task.
    Recursively serializes children and validates against TaskTreeNode schema.

    Args:
        task: The root task to serialize

    Returns:
        TaskTreeNode representation of the task tree

    Example:
        >>> task = Task(name="Root", children=[child1, child2])
        >>> tree = serialize_task_tree(task)
        >>> # tree.model_dump() can be stored as JSON in Experiment.task_tree
    """
    # Use model_dump() - field serializers handle workers, depends_on, etc.
    # Exclude status and children (children handled separately)
    data = task.model_dump(
        exclude={"status", "children"},
        mode="json",  # Ensures UUIDs become strings
    )

    # Recursively serialize children
    data["children"] = [serialize_task_tree(child).model_dump() for child in task.children]

    # Add computed property
    data["is_leaf"] = task.is_leaf

    # Add parent_id explicitly (excluded by Pydantic field config but needed for DB)
    data["parent_id"] = str(task.parent_id) if task.parent_id else None

    # Add evaluator type for reference
    data["evaluator_type"] = type(task.evaluator).__name__ if task.evaluator else None

    # Validate and return as typed model
    return TaskTreeNode.model_validate(data)


def compute_initial_task_states(registry: "TaskRegistry") -> dict[str, str]:
    """
    Compute initial task states from a TaskRegistry.

    Returns a dict mapping task_id (as string) -> status (as string).

    Args:
        registry: The TaskRegistry containing processed tasks

    Returns:
        Dictionary of task_id -> status
    """
    return {str(task.id): task.status.value for task in registry.tasks.values()}


# =============================================================================
# Experiment Persistence
# =============================================================================


def create_experiment_from_task(
    task: Task,
    registry: "TaskRegistry",
    benchmark_name: str = "CUSTOM",
) -> dict:
    """
    Create an Experiment record dict from a Task.

    This function creates the data needed for an Experiment record,
    but does not actually persist it (to allow for synchronous testing).

    Args:
        task: The root task
        registry: The TaskRegistry containing processed task tree
        benchmark_name: The benchmark name (default: "CUSTOM")

    Returns:
        Dictionary suitable for creating an Experiment record
    """
    task_tree = serialize_task_tree(task)

    # Try to parse benchmark_name as enum, fallback to CUSTOM
    try:
        benchmark = BenchmarkName(benchmark_name.lower())
    except ValueError:
        benchmark = BenchmarkName.CUSTOM

    return {
        "benchmark_name": benchmark,
        "task_id": str(task.id),
        "task_description": task.description,
        "ground_truth_rubric": {},
        "task_tree": task_tree.model_dump(),  # Store as dict in DB
        "root_task_id": str(task.id),
        "category": "custom",
    }


def persist_experiment(
    task: Task,
    registry: "TaskRegistry",
    benchmark_name: str = "CUSTOM",
) -> Any:
    """
    Create and persist an Experiment record from a Task.

    Args:
        task: The root task
        registry: The TaskRegistry containing processed task tree
        benchmark_name: The benchmark name (default: "CUSTOM")

    Returns:
        The created Experiment record
    """
    experiment_data = create_experiment_from_task(task, registry, benchmark_name)
    experiment = Experiment(**experiment_data)
    return queries.experiments.create(experiment)


# =============================================================================
# Run Persistence
# =============================================================================


def create_run_from_config(
    experiment_id: UUID,
    registry: "TaskRegistry",
    worker_model: str = "gpt-4o",
    max_questions: int = 10,
    **extra_config: Any,
) -> dict:
    """
    Create a Run record dict from configuration.

    This function creates the data needed for a Run record,
    but does not actually persist it.

    Args:
        experiment_id: The experiment ID
        registry: The TaskRegistry containing processed task tree
        worker_model: The model to use for workers
        max_questions: Maximum questions allowed
        **extra_config: Additional configuration

    Returns:
        Dictionary suitable for creating a Run record
    """
    task_states = compute_initial_task_states(registry)

    return {
        "experiment_id": experiment_id,
        "worker_model": worker_model,
        "max_questions": max_questions,
        "task_states": task_states,
    }


def persist_run(
    experiment_id: UUID,
    registry: "TaskRegistry",
    worker_model: str = "gpt-4o",
    max_questions: int = 10,
    **extra_config: Any,
) -> Any:
    """
    Create and persist a Run record.

    Args:
        experiment_id: The experiment ID
        registry: The TaskRegistry containing processed task tree
        worker_model: The model to use for workers
        max_questions: Maximum questions allowed
        **extra_config: Additional configuration

    Returns:
        The created Run record
    """
    run_data = create_run_from_config(
        experiment_id, registry, worker_model, max_questions, **extra_config
    )
    run = Run(**run_data)
    return queries.runs.create(run)


# =============================================================================
# Resource Persistence
# =============================================================================


def create_resource_from_sdk(
    sdk_resource: SDKResource,
    experiment_id: UUID,
    task_id: UUID,
) -> dict:
    """
    Convert an SDK Resource to a DB Resource dict.

    Handles three types of resources:
    - File paths: Validates existence, uses absolute path
    - Inline content: Writes to temp file, stores path
    - URLs: Stores URL reference (download deferred)

    Args:
        sdk_resource: The SDK Resource to convert
        experiment_id: The experiment ID
        task_id: The task ID this resource belongs to

    Returns:
        Dictionary suitable for creating a Resource record

    Raises:
        FileNotFoundError: If path resource doesn't exist
        ValueError: If resource has no path, content, or url
    """
    if sdk_resource.path:
        # File path resource
        path = Path(sdk_resource.path)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {sdk_resource.path}")

        return {
            "experiment_id": experiment_id,
            "task_id": task_id,
            "is_input": True,
            "name": sdk_resource.name,
            "mime_type": sdk_resource.mime_type,
            "file_path": str(path.absolute()),
            "size_bytes": path.stat().st_size,
        }

    elif sdk_resource.content:
        # Inline content - write to temp file
        content = sdk_resource.content
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        # Create a temp file to store the content
        suffix = _get_extension_from_mime(sdk_resource.mime_type)
        with tempfile.NamedTemporaryFile(mode="wb", suffix=suffix, delete=False) as f:
            f.write(content_bytes)
            temp_path = f.name

        return {
            "experiment_id": experiment_id,
            "task_id": task_id,
            "is_input": True,
            "name": sdk_resource.name,
            "mime_type": sdk_resource.mime_type,
            "file_path": temp_path,
            "size_bytes": len(content_bytes),
        }

    elif sdk_resource.url:
        # URL resource - store reference, defer download
        return {
            "experiment_id": experiment_id,
            "task_id": task_id,
            "is_input": True,
            "name": sdk_resource.name,
            "mime_type": sdk_resource.mime_type,
            "file_path": sdk_resource.url,  # Store URL as path for now
            "size_bytes": 0,  # Unknown until downloaded
        }

    else:
        raise ValueError("Resource must have path, content, or url")


def _get_extension_from_mime(mime_type: str) -> str:
    """Get a file extension from a MIME type."""
    ext = mimetypes.guess_extension(mime_type)
    return ext or ".bin"


def persist_input_resources(
    experiment_id: UUID,
    registry: "TaskRegistry",
) -> dict[UUID, list[UUID]]:
    """
    Create Resource records for all task inputs.

    Args:
        experiment_id: The experiment ID
        registry: The TaskRegistry containing tasks with resources

    Returns:
        Mapping of task_id -> list of created resource IDs
    """
    task_to_resources: dict[UUID, list[UUID]] = {}

    for task in registry.tasks.values():
        resource_ids: list[UUID] = []

        for sdk_resource in task.resources:
            resource_data = create_resource_from_sdk(sdk_resource, experiment_id, task.id)
            db_resource = ResourceRecord(**resource_data)
            created = queries.resources.create(db_resource)
            resource_ids.append(created.id)

        task_to_resources[task.id] = resource_ids

    return task_to_resources


# =============================================================================
# Action Persistence
# =============================================================================


def persist_actions(
    run_id: UUID,
    agent_config_id: UUID,
    actions: list[Action],
) -> list[Action]:
    """
    Persist actions from a WorkerResult.

    Sets run_id, agent_id, and action_num on each action before saving.
    Actions are numbered sequentially starting from the current max action_num
    for this run.

    Args:
        run_id: The run ID
        agent_config_id: The AgentConfig ID for the worker
        actions: List of Action instances (from WorkerResult.actions)

    Returns:
        List of persisted Action records with IDs populated
    """
    if not actions:
        return []

    # Get the current max action_num for this run to continue numbering
    existing_actions = queries.actions.get_all(run_id)
    start_num = len(existing_actions)

    persisted: list[Action] = []
    for i, action in enumerate(actions):
        # Set the required fields
        action.run_id = run_id
        action.agent_id = agent_config_id
        action.action_num = start_num + i

        created = queries.actions.create(action)
        persisted.append(created)

    return persisted


# =============================================================================
# Output Resource Persistence
# =============================================================================


def create_output_resource_from_sdk(
    sdk_resource: SDKResource,
    run_id: UUID,
    task_id: UUID,
    task_execution_id: UUID,
) -> dict:
    """
    Convert an SDK Resource (output) to a DB Resource dict.

    Similar to create_resource_from_sdk but for outputs:
    - Sets is_input=False
    - Links to task_execution_id

    Args:
        sdk_resource: The SDK Resource to convert
        run_id: The run ID
        task_id: The task ID
        task_execution_id: The TaskExecution ID that produced this output

    Returns:
        Dictionary suitable for creating a Resource record
    """
    if sdk_resource.path:
        path = Path(sdk_resource.path)
        if not path.exists():
            raise FileNotFoundError(f"Output file not found: {sdk_resource.path}")

        return {
            "run_id": run_id,
            "task_id": task_id,
            "task_execution_id": task_execution_id,
            "is_input": False,
            "name": sdk_resource.name,
            "mime_type": sdk_resource.mime_type,
            "file_path": str(path.absolute()),
            "size_bytes": path.stat().st_size,
        }

    elif sdk_resource.content:
        content = sdk_resource.content
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        suffix = _get_extension_from_mime(sdk_resource.mime_type)
        with tempfile.NamedTemporaryFile(mode="wb", suffix=suffix, delete=False) as f:
            f.write(content_bytes)
            temp_path = f.name

        return {
            "run_id": run_id,
            "task_id": task_id,
            "task_execution_id": task_execution_id,
            "is_input": False,
            "name": sdk_resource.name,
            "mime_type": sdk_resource.mime_type,
            "file_path": temp_path,
            "size_bytes": len(content_bytes),
        }

    elif sdk_resource.url:
        return {
            "run_id": run_id,
            "task_id": task_id,
            "task_execution_id": task_execution_id,
            "is_input": False,
            "name": sdk_resource.name,
            "mime_type": sdk_resource.mime_type,
            "file_path": sdk_resource.url,
            "size_bytes": 0,
        }

    else:
        raise ValueError("Resource must have path, content, or url")


def persist_output_resources(
    run_id: UUID,
    task_id: UUID,
    task_execution_id: UUID,
    outputs: list[SDKResource],
) -> list[UUID]:
    """
    Persist output resources from a WorkerResult.

    Args:
        run_id: The run ID
        task_id: The task ID
        task_execution_id: The TaskExecution ID that produced these outputs
        outputs: List of SDK Resource instances (from WorkerResult.outputs)

    Returns:
        List of created resource IDs
    """
    resource_ids: list[UUID] = []

    for sdk_resource in outputs:
        resource_data = create_output_resource_from_sdk(
            sdk_resource, run_id, task_id, task_execution_id
        )
        db_resource = ResourceRecord(**resource_data)
        created = queries.resources.create(db_resource)
        resource_ids.append(created.id)

    return resource_ids


# =============================================================================
# Task Execution Persistence
# =============================================================================


def create_task_execution(
    run_id: UUID,
    task_id: UUID,
    agent_config_id: UUID | None = None,
) -> TaskExecution:
    """
    Create a TaskExecution record when a task starts.

    Args:
        run_id: The run ID
        task_id: The task ID (from Task.id)
        agent_config_id: The AgentConfig ID for the assigned worker

    Returns:
        The created TaskExecution record
    """

    return queries.task_executions.create_execution(
        run_id=run_id,
        task_id=task_id,
        agent_id=agent_config_id,
    )


def complete_task_execution(
    execution_id: UUID,
    success: bool,
    output_text: str | None = None,
    output_resource_ids: list[UUID] | None = None,
    score: float | None = None,
    evaluation_details: dict | None = None,
    error_message: str | None = None,
) -> TaskExecution:
    """
    Update a TaskExecution with results when task completes.

    Args:
        execution_id: The TaskExecution ID
        success: Whether the task succeeded
        output_text: Text output from the worker
        output_resource_ids: IDs of output resources
        score: Evaluation score (if evaluator was run)
        evaluation_details: Detailed evaluation results
        error_message: Error message if task failed

    Returns:
        The updated TaskExecution record
    """

    from h_arcane.core.task import TaskStatus

    status = TaskStatus.COMPLETED if success else TaskStatus.FAILED

    return queries.task_executions.update_status(
        execution_id=execution_id,
        status=status,
        completed_at=datetime.now(timezone.utc),
        output_text=output_text,
        output_resource_ids=[str(rid) for rid in (output_resource_ids or [])],
        score=score,
        evaluation_details=evaluation_details or {},
        error_message=error_message,
    )


# =============================================================================
# Agent Mapping Persistence
# =============================================================================


def persist_agent_mapping(
    run_id: UUID,
    agent_registry: "AgentRegistry",
) -> None:
    """
    Store worker_id -> agent_config_id mapping in Run for recovery.

    This allows the mapping to survive orchestrator restarts.
    Stores in Run.benchmark_specific_results under "agent_mapping" key.

    Args:
        run_id: The run ID
        agent_registry: The AgentRegistry with persisted config IDs
    """
    # Build mapping: worker_id (str) -> agent_config_id (str)
    mapping = {
        str(worker_id): str(config_id)
        for worker_id, config_id in agent_registry._config_ids.items()
    }

    # Get current run and update benchmark_specific_results
    run = queries.runs.get(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id}")

    # Merge with existing data
    results = run.benchmark_specific_results or {}
    results["agent_mapping"] = mapping

    # Update the run by modifying and passing the entity
    run.benchmark_specific_results = results
    queries.runs.update(run)


def load_agent_mapping(run_id: UUID) -> dict[UUID, UUID]:
    """
    Load worker_id -> agent_config_id mapping from Run.

    Args:
        run_id: The run ID

    Returns:
        Mapping of worker_id -> agent_config_id
    """
    run = queries.runs.get(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id}")

    results = run.benchmark_specific_results or {}
    mapping_data = results.get("agent_mapping", {})

    return {UUID(k): UUID(v) for k, v in mapping_data.items()}


# =============================================================================
# Full Workflow Persistence
# =============================================================================


def persist_workflow(
    task: Task,
    registry: "TaskRegistry",
    worker_model: str = "gpt-4o",
    max_questions: int = 10,
    benchmark_name: str = "CUSTOM",
) -> tuple[Any, Any, dict[UUID, list[UUID]]]:
    """
    Persist a complete workflow: Experiment, Run, and input Resources.

    This is a convenience function that calls persist_experiment,
    persist_run, and persist_input_resources in sequence.

    Args:
        task: The root task
        registry: The TaskRegistry containing processed task tree
        worker_model: The model to use for workers
        max_questions: Maximum questions allowed
        benchmark_name: The benchmark name

    Returns:
        Tuple of (experiment, run, task_to_resource_ids)
    """
    # 1. Create experiment
    experiment = persist_experiment(task, registry, benchmark_name)

    # 2. Create run
    run = persist_run(experiment.id, registry, worker_model, max_questions)

    # 3. Create input resources
    resource_mapping = persist_input_resources(experiment.id, registry)

    return experiment, run, resource_mapping
