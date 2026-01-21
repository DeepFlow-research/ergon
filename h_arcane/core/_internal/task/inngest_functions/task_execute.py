"""Task execution Inngest function.

Orchestrates single task execution by invoking child functions.
"""

from uuid import UUID

import inngest

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.core._internal.db.models import TaskExecution
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
)
from h_arcane.core._internal.task.inngest_functions.persist_outputs import persist_outputs_fn
from h_arcane.core._internal.task.inngest_functions.sandbox_setup import sandbox_setup_fn
from h_arcane.core._internal.task.inngest_functions.worker_execute import worker_execute_fn
from h_arcane.core._internal.task.persistence import (
    complete_task_execution,
    create_task_execution,
)
from h_arcane.core._internal.task.propagation import mark_task_failed, mark_task_running
from h_arcane.core._internal.task.requests import (
    PersistOutputsRequest,
    SandboxSetupRequest,
    WorkerExecuteRequest,
)
from h_arcane.core._internal.task.results import (
    PersistOutputsResult,
    SandboxReadyResult,
    TaskExecuteResult,
    WorkerExecuteResult,
)
from h_arcane.core._internal.task.schema import parse_task_tree
from h_arcane.core._internal.utils import require_not_none
from h_arcane.core.settings import settings
from h_arcane.core.status import TaskStatus, TaskTrigger
from h_arcane.dashboard import dashboard_emitter


@inngest_client.create_function(
    fn_id="task-execute",
    trigger=inngest.TriggerEvent(event=TaskReadyEvent.name),
    retries=0,  # Tasks should not auto-retry (user decides retry strategy)
    concurrency=[inngest.Concurrency(limit=15, scope="fn")],
    output_type=TaskExecuteResult,
)
async def task_execute(ctx: inngest.Context) -> TaskExecuteResult:
    """
    Orchestrate single task execution.

    This function:
    1. Loads context and validates task (inlined)
    2. Creates execution record and marks running
    3. Invokes sandbox_setup child function
    4. Invokes worker_execute child function
    5. Invokes persist_outputs child function
    6. Completes execution and emits event
    """
    payload = TaskReadyEvent.model_validate(ctx.event.data)
    run_id = UUID(payload.run_id)
    experiment_id = UUID(payload.experiment_id)
    task_id = UUID(payload.task_id)

    # Inline: Load context (pure reads, safe to re-run)
    run = require_not_none(queries.runs.get(run_id), f"Run {run_id} not found")
    experiment = require_not_none(
        queries.experiments.get(experiment_id),
        f"Experiment {experiment_id} not found",
    )

    # Parse task tree and find this task
    tree = parse_task_tree(experiment.task_tree)
    if not tree:
        raise ValueError(f"Experiment {experiment_id} has no task_tree")
    task_node = tree.find_by_id(str(task_id))
    if not task_node:
        raise ValueError(f"Task {task_id} not found in task_tree")

    # Early return for composite tasks
    if not task_node.is_leaf:
        return TaskExecuteResult(
            run_id=run_id,
            task_id=task_id,
            success=True,
            skipped=True,
            skip_reason="composite_task",
        )

    # Get benchmark name
    benchmark_name = (
        BenchmarkName(experiment.benchmark_name)
        if isinstance(experiment.benchmark_name, str)
        else experiment.benchmark_name
    )

    # Load input resources (inlined - pure read)
    input_resources = queries.resources.get_inputs_for_task(experiment_id, task_id)
    input_resource_ids = [r.id for r in input_resources]

    # Create execution and mark running (combined step)
    async def create_running_execution() -> TaskExecution:
        execution = create_task_execution(run_id, task_id)
        mark_task_running(run_id, task_id, execution.id)
        return execution

    execution = await ctx.step.run(
        "create-running-execution", create_running_execution, output_type=TaskExecution
    )
    execution = require_not_none(execution, "create-running-execution returned None")
    execution_id = execution.id

    # Emit dashboard task running event
    async def emit_dashboard_task_running() -> None:
        await dashboard_emitter.task_status_changed(
            run_id=run_id,
            task_id=task_id,
            task_name=task_node.name,
            old_status=TaskStatus.READY,
            new_status=TaskStatus.RUNNING,
            parent_task_id=task_node.parent_id,
            triggered_by=TaskTrigger.WORKER_STARTED,
        )

    await ctx.step.run("emit-dashboard-task-running", emit_dashboard_task_running)

    try:
        # Invoke: Setup sandbox
        sandbox_result: SandboxReadyResult = await ctx.step.invoke(
            step_id="invoke-sandbox-setup",
            function=sandbox_setup_fn,
            data=SandboxSetupRequest(
                run_id=run_id,
                experiment_id=experiment_id,
                task_id=task_id,
                benchmark_name=benchmark_name.value,
                envs={"EXA_API_KEY": settings.exa_api_key},
            ).model_dump(mode="json"),
        )

        # Invoke: Execute worker
        worker_result: WorkerExecuteResult = await ctx.step.invoke(
            step_id="invoke-worker-execute",
            function=worker_execute_fn,
            data=WorkerExecuteRequest(
                run_id=run_id,
                task_id=task_id,
                execution_id=execution_id,
                sandbox_id=sandbox_result.sandbox_id,
                task_description=task_node.description,
                input_resource_ids=input_resource_ids,
                benchmark_name=benchmark_name.value,
                max_questions=run.max_questions,
            ).model_dump(mode="json"),
        )

        # Check if worker execution failed
        if not worker_result.success:
            raise Exception(worker_result.error or "Worker execution failed")

        # Invoke: Persist outputs
        persist_result: PersistOutputsResult = await ctx.step.invoke(
            step_id="invoke-persist-outputs",
            function=persist_outputs_fn,
            data=PersistOutputsRequest(
                run_id=run_id,
                task_id=task_id,
                execution_id=execution_id,
                sandbox_id=sandbox_result.sandbox_id,
                output_dir=sandbox_result.output_dir,
                input_resource_ids=input_resource_ids,
            ).model_dump(mode="json"),
        )

        # Complete execution and emit event (combined step)
        async def complete_and_emit() -> None:
            complete_task_execution(
                execution_id=execution_id,
                success=True,
                output_text=worker_result.output_text,
                output_resource_ids=persist_result.output_resource_ids,
            )
            event = TaskCompletedEvent(
                run_id=str(run_id),
                experiment_id=str(experiment_id),
                task_id=str(task_id),
                execution_id=str(execution_id),
            )
            await inngest_client.send(
                inngest.Event(name=TaskCompletedEvent.name, data=event.model_dump())
            )
            # Emit dashboard task completed event
            await dashboard_emitter.task_status_changed(
                run_id=run_id,
                task_id=task_id,
                task_name=task_node.name,
                old_status=TaskStatus.RUNNING,
                new_status=TaskStatus.COMPLETED,
                parent_task_id=task_node.parent_id,
                triggered_by=TaskTrigger.EXECUTION_SUCCEEDED,
            )

        await ctx.step.run("complete-and-emit", complete_and_emit)

        return TaskExecuteResult(
            run_id=run_id,
            task_id=task_id,
            execution_id=execution_id,
            success=True,
            outputs_count=persist_result.outputs_count,
            questions_asked=worker_result.questions_asked,
        )

    except Exception as exc:
        error_msg = str(exc)

        # Mark failed and emit event (combined step)
        async def fail_and_emit() -> None:
            mark_task_failed(run_id, task_id, error=error_msg, execution_id=execution_id)
            complete_task_execution(
                execution_id=execution_id,
                success=False,
                error_message=error_msg,
            )
            event = TaskFailedEvent(
                run_id=str(run_id),
                experiment_id=str(experiment_id),
                task_id=str(task_id),
                execution_id=str(execution_id),
                error=error_msg,
            )
            await inngest_client.send(
                inngest.Event(name=TaskFailedEvent.name, data=event.model_dump())
            )
            # Emit dashboard task failed event
            await dashboard_emitter.task_status_changed(
                run_id=run_id,
                task_id=task_id,
                task_name=task_node.name,
                old_status=TaskStatus.RUNNING,
                new_status=TaskStatus.FAILED,
                parent_task_id=task_node.parent_id,
                triggered_by=TaskTrigger.EXECUTION_FAILED,
            )

        await ctx.step.run("fail-and-emit", fail_and_emit)

        raise inngest.NonRetriableError(f"Task execution failed: {error_msg}")
