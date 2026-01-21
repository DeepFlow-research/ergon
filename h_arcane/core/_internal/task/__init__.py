"""
Task processing internals.

This module contains the internal machinery for processing task DAGs:
- validate_task_dag: Validates and prepares task trees for execution
- TaskTreeNode: Typed schema for serialized task trees
- TaskEvents/WorkflowEvents: Event constants for Inngest
- Persistence functions: SDK types -> DB records
- Worker context: In-memory task_id -> worker mapping
"""

from h_arcane.core._internal.task.validation import (
    validate_task_dag,
    CycleDetectedError,
    MissingDependencyError,
    TaskValidationError,
)
from h_arcane.core._internal.task.schema import (
    # Typed task tree schema
    TaskTreeNode,
    WorkerRef,
    ResourceRef,
    EvaluatorRef,
    parse_task_tree,
)
from h_arcane.core._internal.task.worker_context import (
    store_worker,
    get_worker,
    clear_worker,
    clear_all_workers,
    store_workers_from_task,
)
from h_arcane.core._internal.task.persistence import (
    # Task tree serialization
    serialize_task_tree,
    # Experiment/Run persistence
    create_experiment_from_task,
    persist_experiment,
    create_run_from_config,
    persist_run,
    # Resource persistence
    create_resource_from_sdk,
    persist_input_resources,
    create_output_resource_from_sdk,
    persist_output_resources,
    # Action persistence
    persist_actions,
    # Task execution persistence
    create_task_execution,
    complete_task_execution,
    # Agent mapping persistence
    persist_agent_mapping,
    load_agent_mapping,
    # Full workflow
    persist_workflow,
)

__all__ = [
    # Validation
    "validate_task_dag",
    "CycleDetectedError",
    "MissingDependencyError",
    "TaskValidationError",
    # Schema
    "TaskTreeNode",
    "WorkerRef",
    "ResourceRef",
    "EvaluatorRef",
    "parse_task_tree",
    # Worker context
    "store_worker",
    "get_worker",
    "clear_worker",
    "clear_all_workers",
    "store_workers_from_task",
    # Events
    "TaskEvents",
    "WorkflowEvents",
    # Task tree serialization
    "serialize_task_tree",
    # Experiment/Run persistence
    "create_experiment_from_task",
    "persist_experiment",
    "create_run_from_config",
    "persist_run",
    # Resource persistence
    "create_resource_from_sdk",
    "persist_input_resources",
    "create_output_resource_from_sdk",
    "persist_output_resources",
    # Action persistence
    "persist_actions",
    # Task execution persistence
    "create_task_execution",
    "complete_task_execution",
    # Agent mapping persistence
    "persist_agent_mapping",
    "load_agent_mapping",
    # Full workflow
    "persist_workflow",
]
