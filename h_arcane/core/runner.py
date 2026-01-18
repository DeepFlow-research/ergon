"""
User-facing execute_task() function and ExecutionResult.

This is the PUBLIC API for executing tasks and workflows.

Usage:
    from h_arcane import Task, execute_task

    worker = MyWorker(model="gpt-4o", tools=[...])
    task = Task(name="...", description="...", assigned_to=worker)
    result = await execute_task(task)

    if result.success:
        print(f"Score: {result.score}")
    else:
        print(f"Error: {result.error}")
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import inngest
from pydantic import BaseModel, Field

from h_arcane.core._internal.db.models import RunStatus
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.events import WorkflowStartedEvent
from h_arcane.core.task import Resource, Task, TaskStatus


class TaskResult(BaseModel):
    """
    Result for a single task in a DAG.

    When executing a workflow (Task with children), each subtask
    produces its own TaskResult. These are collected in
    ExecutionResult.task_results.

    Attributes:
        task_id: UUID of the task
        name: Task name (for display)
        status: Final status (COMPLETED, FAILED)
        score: Evaluation score (if evaluator was provided)
        outputs: List of output artifacts
        error: Error message if task failed
    """

    task_id: UUID
    name: str
    status: TaskStatus
    score: float | None = None
    outputs: list[Resource] = Field(default_factory=list)
    error: str | None = None


class ExecutionResult(BaseModel):
    """
    Result of running a task or workflow via execute_task().

    This is the user-facing result type. It aggregates results from
    all tasks in a DAG and provides overall status and metrics.

    Attributes:
        success: True if all tasks completed successfully
        status: Overall workflow status
        outputs: Outputs from the root task
        score: Aggregate evaluation score (if evaluator provided)
        evaluation_details: Detailed evaluation results
        started_at: When execution began
        completed_at: When execution finished
        duration_seconds: Total execution time
        total_cost_usd: Total API costs
        task_results: Per-task results (for DAGs)
        run_id: The database Run ID (for debugging/inspection)
        experiment_id: The database Experiment ID
        error: Error message if execution failed

    Example:
        result = await execute_task(workflow)
        if result.success:
            print(f"Completed in {result.duration_seconds:.1f}s")
            print(f"Score: {result.score}")
            for task_id, task_result in result.task_results.items():
                print(f"  {task_result.name}: {task_result.status}")
    """

    success: bool
    status: TaskStatus

    # Outputs from root task
    outputs: list[Resource] = Field(default_factory=list)

    # Evaluation
    score: float | None = None
    evaluation_details: dict = Field(default_factory=dict)

    # Timing
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    duration_seconds: float = 0.0

    # Cost
    total_cost_usd: float = 0.0

    # Per-task results (for DAGs)
    task_results: dict[UUID, TaskResult] = Field(default_factory=dict)

    # Database references (for debugging/inspection)
    run_id: UUID | None = None
    experiment_id: UUID | None = None

    # Error info
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}


async def execute_task(
    task: Task,
    evaluator: Any = None,  # AnyRubric has heavy benchmark dependencies
    timeout_seconds: float | None = None,
    max_concurrent_tasks: int = 10,
    worker_model: str = "gpt-4o",
    max_questions: int = 10,
    benchmark_name: str = "CUSTOM",
    **config: Any,
) -> ExecutionResult:
    """
    Execute a task (single or DAG workflow).

    Workers are attached directly to tasks via `assigned_to` and `full_team`.
    No worker argument needed - tasks carry their workers.

    Args:
        task: The task to execute (with assigned workers)
        evaluator: Optional workflow-level evaluator (overrides task.evaluator)
        timeout_seconds: Maximum execution time (None = no timeout)
        max_concurrent_tasks: Concurrency limit for parallel task execution
        worker_model: Default model for workers (default: gpt-4o)
        max_questions: Maximum questions workers can ask (default: 10)
        benchmark_name: Name of the benchmark (default: CUSTOM)
        **config: Additional configuration passed to the execution engine

    Returns:
        ExecutionResult with success status, outputs, and scores

    Example:
        # Single task
        worker = ReactWorker(model="gpt-4o", tools=[...])
        task = Task(name="...", assigned_to=worker, ...)
        result = await execute_task(task)

        # DAG workflow
        a = Task(name="A", assigned_to=worker)
        b = Task(name="B", assigned_to=worker, depends_on=[a])
        workflow = Task(name="Root", assigned_to=worker, children=[a, b])
        result = await execute_task(workflow, timeout_seconds=300)
    """
    from h_arcane.core._internal.agents.registry import AgentRegistry
    from h_arcane.core._internal.task.persistence import (
        persist_agent_mapping,
        persist_workflow,
    )
    from h_arcane.core._internal.task.registry import TaskRegistry

    started_at = datetime.now(timezone.utc)

    try:
        # 1. Validate and process task tree (TaskRegistry)
        registry = TaskRegistry(task)

        # 2. Build agent registry (collect all workers)
        agent_registry = AgentRegistry()
        agent_registry.register_from_task(task)

        # 3. Persist to database (Experiment, Run, Resources, AgentConfigs)
        experiment, run, resource_mapping = persist_workflow(
            task=task,
            registry=registry,
            worker_model=worker_model,
            max_questions=max_questions,
            benchmark_name=benchmark_name,
        )

        # Persist agent configs
        agent_registry.persist(run.id)
        persist_agent_mapping(run.id, agent_registry)

        # 4. Trigger execution via Inngest
        event = WorkflowStartedEvent(
            run_id=str(run.id),
            experiment_id=str(experiment.id),
        )
        await inngest_client.send(
            inngest.Event(name=WorkflowStartedEvent.name, data=event.model_dump())
        )

        # 5. Wait for completion
        result = await _wait_for_completion(
            run_id=run.id,
            experiment_id=experiment.id,
            timeout=timeout_seconds,
            started_at=started_at,
        )

        return result

    except Exception as exc:
        completed_at = datetime.now(timezone.utc)
        duration = (completed_at - started_at).total_seconds()

        return ExecutionResult(
            success=False,
            status=TaskStatus.FAILED,
            outputs=[],
            score=None,
            evaluation_details={},
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            total_cost_usd=0.0,
            task_results={},
            error=f"Workflow failed to start: {exc}",
        )


async def _wait_for_completion(
    run_id: UUID,
    experiment_id: UUID,
    timeout: float | None,
    started_at: datetime,
    poll_interval: float = 1.0,
) -> ExecutionResult:
    """
    Poll database until run completes or times out.

    Args:
        run_id: The Run UUID to monitor
        experiment_id: The Experiment UUID
        timeout: Maximum seconds to wait (None = no timeout)
        started_at: When execution started (for duration calculation)
        poll_interval: Seconds between polls (default: 1.0)

    Returns:
        ExecutionResult with final status and results
    """
    start_time = time.time()
    terminal_statuses = {RunStatus.COMPLETED, RunStatus.FAILED}

    while True:
        # Get current run status
        run = queries.runs.get(run_id)
        if run is None:
            return _build_error_result(
                started_at=started_at,
                error=f"Run {run_id} not found",
                run_id=run_id,
                experiment_id=experiment_id,
            )

        # Check if terminal state
        if run.status in terminal_statuses:
            return _build_result_from_run(run, started_at, experiment_id)

        # Check timeout
        if timeout and (time.time() - start_time) > timeout:
            return _build_error_result(
                started_at=started_at,
                error=f"Workflow timed out after {timeout} seconds",
                run_id=run_id,
                experiment_id=experiment_id,
            )

        # Wait before next poll
        await asyncio.sleep(poll_interval)


def _build_result_from_run(
    run: Any,  # Run model
    started_at: datetime,
    experiment_id: UUID,
) -> ExecutionResult:
    """Build ExecutionResult from a completed Run."""
    completed_at = run.completed_at or datetime.now(timezone.utc)
    duration = (completed_at - started_at).total_seconds()

    # Determine success and status
    success = run.status == RunStatus.COMPLETED
    status = TaskStatus.COMPLETED if success else TaskStatus.FAILED

    # Load output resources
    output_resources: list[Resource] = []
    if run.output_resource_ids:
        for res_id_str in run.output_resource_ids:
            try:
                db_resource = queries.resources.get(UUID(res_id_str))
                if db_resource:
                    # Convert DB Resource to SDK Resource
                    output_resources.append(
                        Resource(
                            name=db_resource.name,
                            path=db_resource.file_path,
                        )
                    )
            except Exception:
                pass  # Skip invalid resource IDs

    # Build task results from task_executions
    # Track the highest attempt number seen for each task
    task_results: dict[UUID, TaskResult] = {}
    task_attempts: dict[UUID, int] = {}
    executions = queries.task_executions.get_by_run(run.id)
    for exec in executions:
        # Get the latest execution for each task (by attempt number)
        current_attempt = task_attempts.get(exec.task_id, 0)
        if exec.attempt_number > current_attempt:
            task_status = TaskStatus.COMPLETED if exec.status == "completed" else TaskStatus.FAILED
            task_results[exec.task_id] = TaskResult(
                task_id=exec.task_id,
                name=f"Task-{exec.task_id}",  # TODO: Get name from task_tree
                status=task_status,
                score=exec.score,
                outputs=[],  # TODO: Load task-specific outputs
                error=exec.error_message,
            )
            task_attempts[exec.task_id] = exec.attempt_number

    return ExecutionResult(
        success=success,
        status=status,
        outputs=output_resources,
        score=run.final_score,
        evaluation_details=run.benchmark_specific_results or {},
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration,
        total_cost_usd=run.total_cost_usd or 0.0,
        task_results=task_results,
        run_id=run.id,
        experiment_id=experiment_id,
        error=run.error_message,
    )


def _build_error_result(
    started_at: datetime,
    error: str,
    run_id: UUID | None = None,
    experiment_id: UUID | None = None,
) -> ExecutionResult:
    """Build an error ExecutionResult."""
    completed_at = datetime.now(timezone.utc)
    duration = (completed_at - started_at).total_seconds()

    return ExecutionResult(
        success=False,
        status=TaskStatus.FAILED,
        outputs=[],
        score=None,
        evaluation_details={},
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration,
        total_cost_usd=0.0,
        task_results={},
        run_id=run_id,
        experiment_id=experiment_id,
        error=error,
    )
