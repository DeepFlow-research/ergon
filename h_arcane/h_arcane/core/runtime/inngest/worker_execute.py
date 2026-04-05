"""Inngest child function: worker execution.

Looks up the registered worker, constructs a BenchmarkTask, and runs execute().
"""

import logging

import inngest
from arcane_builtins.registry import WORKERS
from h_arcane.api.task_types import BenchmarkTask
from h_arcane.api.worker_context import WorkerContext
from h_arcane.core.runtime.errors import RegistryLookupError
from h_arcane.core.runtime.inngest_client import inngest_client
from h_arcane.core.runtime.services.child_function_payloads import WorkerExecuteRequest
from h_arcane.core.runtime.services.inngest_function_results import WorkerExecuteResult

logger = logging.getLogger(__name__)


@inngest_client.create_function(
    fn_id="worker-execute",
    trigger=inngest.TriggerEvent(event="task/worker-execute"),
    retries=0,
    output_type=WorkerExecuteResult,
)
async def worker_execute_fn(ctx: inngest.Context) -> WorkerExecuteResult:
    payload = WorkerExecuteRequest(**ctx.event.data)
    logger.info(
        "worker-execute run_id=%s task_id=%s worker_type=%s",
        payload.run_id,
        payload.task_id,
        payload.worker_type,
    )

    worker_cls = WORKERS.get(payload.worker_type)
    if worker_cls is None:
        raise RegistryLookupError(
            registry_name="worker", 
            slug=payload.worker_type,
            run_id=payload.run_id,
            task_id=payload.task_id,
            execution_id=payload.execution_id,
            sandbox_id=payload.sandbox_id,
        )

    worker = worker_cls(
        name=payload.worker_binding_key,
        model=payload.model_target or None,
    )

    task = BenchmarkTask(
        task_key=payload.task_key,
        instance_key=str(payload.execution_id),
        description=payload.task_description,
    )

    worker_context = WorkerContext(
        run_id=payload.run_id,
        task_id=payload.task_id,
        execution_id=payload.execution_id,
        sandbox_id=payload.sandbox_id,
    )

    result = await worker.execute(task, context=worker_context)

    return WorkerExecuteResult(
        success=True,
        output_text=result.output,
    )
