"""Central registry of all Inngest functions for the ergon-core app.

Pass ALL_FUNCTIONS to inngest.serve() or the framework integration.

**Notable omission:** the legacy per-evaluator dispatch handler that
used to listen on `task/completed` is intentionally absent from this
list. PR 4 moved both of its responsibilities (per-evaluator fanout
and terminal sandbox release) to the current `execute_task` plus
`sandbox_cleanup` ownership boundary.
"""

from ergon_core.core.infrastructure.inngest.handlers.cancel_orphan_subtasks import (
    block_descendants_on_failed_fn,
    cancel_orphans_on_cancelled_fn,
)
from ergon_core.core.infrastructure.inngest.handlers.cleanup_cancelled_task import (
    cleanup_cancelled_task_fn,
)
from ergon_core.core.infrastructure.inngest.handlers.complete_workflow import complete_workflow_fn
from ergon_core.core.infrastructure.inngest.handlers.evaluate_task_run import evaluate_task_run
from ergon_core.core.infrastructure.inngest.handlers.execute_task import execute_task_fn
from ergon_core.core.infrastructure.inngest.handlers.fail_workflow import fail_workflow_fn
from ergon_core.core.infrastructure.inngest.handlers.persist_outputs import persist_outputs_fn
from ergon_core.core.infrastructure.inngest.handlers.propagate_execution import (
    propagate_task_failure_fn,
    propagate_task_fn,
)
from ergon_core.core.infrastructure.inngest.handlers.run_cleanup import run_cleanup_fn
from ergon_core.core.infrastructure.inngest.handlers.sandbox_cleanup import (
    sandbox_cleanup_on_completed_fn,
    sandbox_cleanup_on_failed_fn,
)
from ergon_core.core.infrastructure.inngest.handlers.sandbox_setup import sandbox_setup_fn
from ergon_core.core.infrastructure.inngest.handlers.start_workflow import start_workflow_fn
from ergon_core.core.infrastructure.inngest.handlers.worker_execute import worker_execute_fn

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
    run_cleanup_fn,
    sandbox_cleanup_on_completed_fn,
    sandbox_cleanup_on_failed_fn,
]
