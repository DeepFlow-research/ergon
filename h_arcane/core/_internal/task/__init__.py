"""
Task processing internals.

This module contains the internal machinery for processing task DAGs:
- TaskRegistry: Flattens, validates, and manages task trees
- TaskEvents/WorkflowEvents: Event constants for Inngest
- Persistence functions: SDK types -> DB records
"""

from h_arcane.core._internal.task.registry import TaskRegistry
from h_arcane.core._internal.task.persistence import (
    # Task tree serialization
    serialize_task_tree,
    compute_initial_task_states,
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
    # Registry
    "TaskRegistry",
    # Events
    "TaskEvents",
    "WorkflowEvents",
    # Task tree serialization
    "serialize_task_tree",
    "compute_initial_task_states",
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
