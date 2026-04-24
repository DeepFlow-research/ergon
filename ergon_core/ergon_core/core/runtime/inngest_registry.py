"""Central registry of all Inngest functions for the ergon-core app.

Pass ALL_FUNCTIONS to inngest.serve() or the framework integration.
"""

from ergon_core.core.runtime.inngest.benchmark_run_start import benchmark_run_start_fn
from ergon_core.core.runtime.inngest.cancel_orphan_subtasks import (
    block_descendants_on_failed_fn,
    cancel_orphans_on_cancelled_fn,
)
from ergon_core.core.runtime.inngest.cleanup_cancelled_task import cleanup_cancelled_task_fn
from ergon_core.core.runtime.inngest.check_evaluators import check_and_run_evaluators
from ergon_core.core.runtime.inngest.complete_workflow import complete_workflow_fn
from ergon_core.core.runtime.inngest.evaluate_task_run import evaluate_task_run
from ergon_core.core.runtime.inngest.execute_task import execute_task_fn
from ergon_core.core.runtime.inngest.fail_workflow import fail_workflow_fn
from ergon_core.core.runtime.inngest.persist_outputs import persist_outputs_fn
from ergon_core.core.runtime.inngest.propagate_execution import (
    propagate_task_failure_fn,
    propagate_task_fn,
)
from ergon_core.core.runtime.inngest.run_cleanup import run_cleanup_fn
from ergon_core.core.runtime.inngest.sandbox_setup import sandbox_setup_fn
from ergon_core.core.runtime.inngest.start_workflow import start_workflow_fn
from ergon_core.core.runtime.inngest.worker_execute import worker_execute_fn

ALL_FUNCTIONS = [
    # Benchmark entry point
    benchmark_run_start_fn,
    # Task orchestration
    start_workflow_fn,
    execute_task_fn,
    propagate_task_fn,
    propagate_task_failure_fn,
    complete_workflow_fn,
    fail_workflow_fn,
    # Task child functions
    sandbox_setup_fn,
    worker_execute_fn,
    persist_outputs_fn,
    # Evaluation
    check_and_run_evaluators,
    evaluate_task_run,
    # Subtask lifecycle
    block_descendants_on_failed_fn,
    cancel_orphans_on_cancelled_fn,
    cleanup_cancelled_task_fn,
    # Infrastructure
    run_cleanup_fn,
]
