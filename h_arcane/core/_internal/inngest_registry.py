"""Central registry for all Inngest functions.

This module aggregates Inngest functions from across domains,
providing a single import point for api/main.py.

Convention:
- Each domain with Inngest functions has an `inngest_functions.py` module
- Each domain has an `events.py` module for input/output schemas (contracts)
- Domain logic (base.py, schemas.py, rules/) stays separate from Inngest wiring
"""

from typing import Any

from inngest import Function

from h_arcane.core._internal.agents.inngest_functions import worker_execute
from h_arcane.core._internal.evaluation.inngest_functions import (
    evaluate_criterion_fn,
    evaluate_task_run,
    run_evaluate,
)
from h_arcane.core._internal.infrastructure.inngest_functions import run_cleanup
from h_arcane.core._internal.task.inngest_functions import (
    task_execute,
    task_propagate,
    workflow_complete,
    workflow_failed,
    workflow_start,
)

# All Inngest functions for registration with FastAPI/Inngest
ALL_FUNCTIONS: list[Function[Any]] = [
    # Legacy single-task execution
    worker_execute,
    # DAG workflow orchestration
    workflow_start,
    task_execute,
    task_propagate,
    workflow_complete,
    workflow_failed,
    # Evaluation
    run_evaluate,
    evaluate_task_run,
    evaluate_criterion_fn,
    # Infrastructure
    run_cleanup,
]

__all__ = [
    "ALL_FUNCTIONS",
    # Agents (legacy)
    "worker_execute",
    # Task/Workflow orchestration (new DAG)
    "workflow_start",
    "task_execute",
    "task_propagate",
    "workflow_complete",
    "workflow_failed",
    # Evaluation
    "run_evaluate",
    "evaluate_task_run",
    "evaluate_criterion_fn",
    # Infrastructure
    "run_cleanup",
]
