"""Benchmark run start Inngest function.

Handles benchmark run requests from CLI by reconstructing workers server-side.

This solves the process boundary problem where the CLI runs on the host machine
but Inngest functions run in a container - workers stored in memory by the CLI
would not be accessible to worker_execute_fn.

By having this function reconstruct workers server-side, store_workers_from_task()
and get_worker() share the same in-memory dictionary.
"""

from functools import partial
from uuid import UUID

import inngest
from pydantic import BaseModel

from h_arcane.benchmarks.common.workers.react_worker import ReActWorker
from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.registry import get_worker_config, get_workflow_factories
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.task.events import BenchmarkRunRequest, WorkflowStartedEvent
from h_arcane.core._internal.task.persistence import persist_workflow
from h_arcane.core._internal.task.validation import validate_task_dag
from h_arcane.core._internal.task.worker_context import store_workers_from_task


class BenchmarkRunResult(BaseModel):
    """Result of benchmark run initialization."""

    request_id: str
    run_id: str
    experiment_id: str
    success: bool = True
    error: str | None = None


@inngest_client.create_function(
    fn_id="benchmark-run-start",
    trigger=inngest.TriggerEvent(event=BenchmarkRunRequest.name),
    retries=1,
    output_type=BenchmarkRunResult,
)
async def benchmark_run_start(ctx: inngest.Context) -> BenchmarkRunResult:
    """
    Initialize a benchmark run from CLI request.

    This function runs inside the container where worker_execute_fn also runs,
    so workers stored in memory are accessible during execution.

    Steps:
    1. Parse request and get benchmark config from registry
    2. Create worker using ReActWorker with benchmark config
    3. Create workflow using benchmark's workflow factory
    4. Validate DAG, store workers, persist to DB
    5. Emit WorkflowStartedEvent to trigger execution flow
    6. Return run_id for CLI to poll completion
    """
    payload = BenchmarkRunRequest.model_validate(ctx.event.data)

    try:
        # 1. Parse benchmark name and get config
        benchmark_name = BenchmarkName(payload.benchmark_name)
        worker_config = get_worker_config(benchmark_name)

        # Override max_questions if specified in request
        if payload.max_questions != worker_config.max_questions:
            # Create new config with updated max_questions
            worker_config = worker_config.model_copy(
                update={"max_questions": payload.max_questions}
            )

        # 2. Create worker with specified model and benchmark config
        worker = ReActWorker(model=payload.model, config=worker_config)

        # 3. Get workflow factories for this benchmark and create workflow
        workflow_factories = get_workflow_factories(benchmark_name)
        if payload.workflow_name not in workflow_factories:
            available = ", ".join(workflow_factories.keys())
            raise ValueError(
                f"Unknown workflow '{payload.workflow_name}' for benchmark "
                f"'{benchmark_name.value}'. Available: {available}"
            )

        workflow_factory = workflow_factories[payload.workflow_name]
        task = workflow_factory(worker)

        # 4. Validate DAG
        validate_task_dag(task)

        # 5. Store workers in memory (same process as worker_execute!)
        store_workers_from_task(task)

        # 6. Persist to database (wrapped in step for durability)
        persist_result = await ctx.step.run(
            "persist-workflow",
            partial(
                _persist_workflow_step,
                task,
                payload.model,
                payload.max_questions,
                payload.benchmark_name,
                payload.request_id,
            ),
        )
        if persist_result is None:
            raise ValueError("persist-workflow step returned None")

        run_id = UUID(persist_result["run_id"])
        experiment_id = UUID(persist_result["experiment_id"])

        # Note: Agent configs are created by worker_execute when tasks execute,
        # using get_or_create for deduplication. No need to create them here.

        # 8. Emit WorkflowStartedEvent to trigger workflow_start
        await ctx.step.run(
            "emit-workflow-started",
            partial(_emit_workflow_started, run_id, experiment_id),
        )

        return BenchmarkRunResult(
            request_id=payload.request_id,
            run_id=str(run_id),
            experiment_id=str(experiment_id),
            success=True,
        )

    except Exception as e:
        return BenchmarkRunResult(
            request_id=payload.request_id,
            run_id="",
            experiment_id="",
            success=False,
            error=str(e),
        )


async def _persist_workflow_step(
    task,
    worker_model: str,
    max_questions: int,
    benchmark_name: str,
    request_id: str,
) -> dict:
    """Persist workflow to database. Returns run_id and experiment_id."""
    experiment, run, _ = persist_workflow(
        task=task,
        worker_model=worker_model,
        max_questions=max_questions,
        benchmark_name=benchmark_name,
    )

    # Store request_id in run metadata so CLI can poll for this specific run
    run.benchmark_specific_results = run.benchmark_specific_results or {}
    run.benchmark_specific_results["cli_request_id"] = request_id
    queries.runs.update(run)

    return {
        "run_id": str(run.id),
        "experiment_id": str(experiment.id),
    }


async def _emit_workflow_started(run_id: UUID, experiment_id: UUID) -> None:
    """Emit WorkflowStartedEvent to trigger workflow execution."""
    event = WorkflowStartedEvent(
        run_id=str(run_id),
        experiment_id=str(experiment_id),
    )
    await inngest_client.send(
        inngest.Event(name=WorkflowStartedEvent.name, data=event.model_dump())
    )
