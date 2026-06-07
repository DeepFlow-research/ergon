"""Central registry of all Inngest functions for the ergon-core app.

Pass ALL_FUNCTIONS to inngest.serve() or the framework integration.

**Notable omission:** evaluator fanout is synchronous inside `execute_task`,
and terminal sandbox release is owned by `sandbox_cleanup`.
"""

from ergon_core.core.jobs.task.cancel_orphans.inngest import (
    block_descendants_on_failed_fn,
    cancel_orphans_on_cancelled_fn,
)
from ergon_core.core.jobs.task.cleanup_cancelled.inngest import (
    cleanup_cancelled_task_fn,
)
from ergon_core.core.jobs.resources.persist_outputs.inngest import persist_outputs_fn
from ergon_core.core.jobs.run.cleanup.inngest import sample_cleanup_fn
from ergon_core.core.jobs.sandbox.cleanup.inngest import (
    sandbox_cleanup_on_completed_fn,
    sandbox_cleanup_on_failed_fn,
)
from ergon_core.core.jobs.sandbox.setup.inngest import sandbox_setup_fn
from ergon_core.core.jobs.task.evaluate.inngest import evaluate_task_run
from ergon_core.core.jobs.task.execute.inngest import execute_task_fn
from ergon_core.core.jobs.task.propagate.inngest import (
    propagate_task_failure_fn,
    propagate_task_fn,
)
from ergon_core.core.jobs.task.worker_execute.inngest import worker_execute_fn
from ergon_core.core.jobs.workflow.complete.inngest import complete_workflow_fn
from ergon_core.core.jobs.workflow.fail.inngest import fail_workflow_fn
from ergon_core.core.jobs.workflow.start.inngest import start_workflow_fn

ALL_FUNCTIONS = [
    start_workflow_fn,
    execute_task_fn,
    propagate_task_fn,
    propagate_task_failure_fn,
    complete_workflow_fn,
    fail_workflow_fn,
    sandbox_setup_fn,
    worker_execute_fn,
    persist_outputs_fn,
    evaluate_task_run,
    block_descendants_on_failed_fn,
    cancel_orphans_on_cancelled_fn,
    cleanup_cancelled_task_fn,
    sample_cleanup_fn,
    sandbox_cleanup_on_completed_fn,
    sandbox_cleanup_on_failed_fn,
]
