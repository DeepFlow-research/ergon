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
from h_arcane.core._internal.cohorts import ResolveCohortRequest, experiment_cohort_service
from h_arcane.core._internal.db.models import CohortMetadata, DispatchConfigSnapshot
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.events import BenchmarkRunRequest, WorkflowStartedEvent
from h_arcane.core._internal.task.persistence import persist_run, persist_workflow
from h_arcane.core._internal.task.validation import validate_task_dag
from h_arcane.core._internal.task.worker_context import store_worker_for_tree, store_workers_from_task
from h_arcane.core._internal.utils import require_not_none


class BenchmarkRunResult(BaseModel):
    """Result of benchmark run initialization."""

    request_id: str
    run_id: UUID | None = None
    experiment_id: UUID | None = None
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

        if payload.experiment_id is not None:
            persist_result = await ctx.step.run(
                "start-seeded-experiment-run",
                partial(
                    _start_seeded_experiment_run_step,
                    payload.experiment_id,
                    benchmark_name,
                    payload.model,
                    payload.max_questions,
                    payload.request_id,
                    payload.cohort_name,
                ),
            )
        else:
            workflow_name = require_not_none(payload.workflow_name, "workflow_name missing")

            # 3. Get workflow factories for this benchmark and create workflow
            workflow_factories = get_workflow_factories(benchmark_name)
            if workflow_name not in workflow_factories:
                available = ", ".join(workflow_factories.keys())
                raise ValueError(
                    f"Unknown workflow '{workflow_name}' for benchmark "
                    f"'{benchmark_name.value}'. Available: {available}"
                )

            workflow_factory = workflow_factories[workflow_name]
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
                    payload.cohort_name,
                ),
            )
        if persist_result is None:
            raise ValueError("persist-workflow step returned None")

        # Step output is JSON-deserialized; coerce str back to UUID
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
            run_id=run_id,
            experiment_id=experiment_id,
            success=True,
        )

    except Exception as e:
        return BenchmarkRunResult(
            request_id=payload.request_id,
            run_id=None,
            experiment_id=None,
            success=False,
            error=str(e),
        )


async def _persist_workflow_step(
    task,
    worker_model: str,
    max_questions: int,
    benchmark_name: str,
    request_id: str,
    cohort_name: str,
) -> dict:
    """Persist workflow to database. Returns run_id and experiment_id."""
    cohort = experiment_cohort_service.resolve_or_create(
        ResolveCohortRequest(
            name=cohort_name,
            metadata=CohortMetadata(
                model_name=worker_model,
                dispatch_config=DispatchConfigSnapshot(
                    worker_model=worker_model,
                    max_questions=max_questions,
                ),
            ),
        )
    )
    experiment, run, _ = persist_workflow(
        task=task,
        worker_model=worker_model,
        max_questions=max_questions,
        benchmark_name=benchmark_name,
        **{
            "cohort_id": cohort.id,
            "dispatch_metadata": {
                "cli_request_id": request_id,
                "cohort_name": cohort_name,
            },
        },
    )

    # Step output is JSON-serialized; use str for wire format
    return {
        "run_id": str(run.id),
        "experiment_id": str(experiment.id),
    }


async def _start_seeded_experiment_run_step(
    experiment_id: UUID,
    benchmark_name: BenchmarkName,
    worker_model: str,
    max_questions: int,
    request_id: str,
    cohort_name: str,
) -> dict:
    """Create a cohort-backed run from a previously seeded Experiment row."""
    experiment = require_not_none(
        queries.experiments.get(experiment_id),
        f"Experiment {experiment_id} not found",
    )
    if experiment.benchmark_name != benchmark_name:
        raise ValueError(
            f"Experiment {experiment_id} belongs to benchmark '{experiment.benchmark_name.value}', "
            f"not '{benchmark_name.value}'"
        )

    task_tree = require_not_none(
        experiment.parsed_task_tree(),
        f"Experiment {experiment_id} has no task_tree",
    )
    worker_config = get_worker_config(benchmark_name)
    if max_questions != worker_config.max_questions:
        worker_config = worker_config.model_copy(update={"max_questions": max_questions})
    worker = ReActWorker(model=worker_model, config=worker_config)
    store_worker_for_tree(task_tree, worker)

    cohort = experiment_cohort_service.resolve_or_create(
        ResolveCohortRequest(
            name=cohort_name,
            metadata=CohortMetadata(
                model_name=worker_model,
                dispatch_config=DispatchConfigSnapshot(
                    worker_model=worker_model,
                    max_questions=max_questions,
                ),
            ),
        )
    )
    run = persist_run(
        experiment_id=experiment.id,
        worker_model=worker_model,
        max_questions=max_questions,
        **{
            "cohort_id": cohort.id,
            "dispatch_metadata": {
                "cli_request_id": request_id,
                "cohort_name": cohort_name,
                "extras": {
                    "launch_mode": "seeded_experiment",
                },
            },
        },
    )
    return {
        "run_id": str(run.id),
        "experiment_id": str(experiment.id),
    }


async def _emit_workflow_started(run_id: UUID, experiment_id: UUID) -> None:
    """Emit WorkflowStartedEvent to trigger workflow execution."""
    event = WorkflowStartedEvent(
        run_id=run_id,
        experiment_id=experiment_id,
    )
    await inngest_client.send(
        inngest.Event(name=WorkflowStartedEvent.name, data=event.model_dump(mode="json"))
    )
