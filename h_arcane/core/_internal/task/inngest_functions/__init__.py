"""Inngest functions for DAG-based workflow orchestration.

These functions handle the lifecycle of workflow execution:

Orchestrators (triggered by external events):
- workflow_start: Initialize DAG, create dependencies, start initial tasks
- task_execute: Orchestrate single task execution via child functions
- task_propagate: Handle completion, check dependencies, emit ready events
- workflow_complete: Finalize run, aggregate results, cleanup
- workflow_failed: Handle workflow failure
- benchmark_run_start: Initialize benchmark run from CLI (reconstructs workers server-side)

Child functions (invoked by orchestrators):
- sandbox_setup: Create and configure sandbox for task
- worker_execute: Execute worker agent in sandbox
- persist_outputs: Download and register output resources

Event flow:
    CLI -> benchmark/run-request
           -> benchmark_run_start -> workflow/started
                                     -> workflow_start -> task/ready (for initial tasks)
                                                          -> task_execute
                                                             -> sandbox_setup (invoke)
                                                             -> worker_execute (invoke)
                                                             -> persist_outputs (invoke)
                                                             -> task/completed
                                                                -> task_propagate -> task/ready (next tasks)
                                                                                     ... repeat ...
                                                                                  -> workflow/completed
                                                                                     -> workflow_complete
"""

from h_arcane.core._internal.task.inngest_functions.benchmark_run_start import (
    benchmark_run_start,
)
from h_arcane.core._internal.task.inngest_functions.persist_outputs import (
    persist_outputs_fn,
)
from h_arcane.core._internal.task.inngest_functions.sandbox_setup import sandbox_setup_fn
from h_arcane.core._internal.task.inngest_functions.task_execute import task_execute
from h_arcane.core._internal.task.inngest_functions.task_propagate import task_propagate
from h_arcane.core._internal.task.inngest_functions.worker_execute import worker_execute_fn
from h_arcane.core._internal.task.inngest_functions.workflow_complete import (
    workflow_complete,
)
from h_arcane.core._internal.task.inngest_functions.workflow_failed import workflow_failed
from h_arcane.core._internal.task.inngest_functions.workflow_start import workflow_start

__all__ = [
    # Orchestrators
    "workflow_start",
    "task_execute",
    "task_propagate",
    "workflow_complete",
    "workflow_failed",
    "benchmark_run_start",
    # Child functions
    "sandbox_setup_fn",
    "worker_execute_fn",
    "persist_outputs_fn",
]
