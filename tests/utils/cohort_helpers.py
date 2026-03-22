"""Shared helpers for experiment cohort backend tests."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from h_arcane import Task
from h_arcane.core.worker import BaseWorker, Tool
from h_arcane.core._internal.cohorts import ResolveCohortRequest, experiment_cohort_service
from h_arcane.core._internal.db.models import CohortMetadata, Run, RunStatus
from h_arcane.core._internal.task.persistence import persist_experiment_definition, persist_run
from h_arcane.core._internal.task.validation import validate_task_dag
from h_arcane.core._internal.utils import utcnow


class MockWorker(BaseWorker):
    """Simple mock worker for cohort backend tests."""

    def __init__(self, name: str = "mock-worker"):
        self.id = uuid4()
        self.name = name
        self.model = "gpt-4o-mini"
        self.tools: list[Tool] = []
        self.system_prompt = "You are a mock worker."

    async def execute(self, task, context):
        raise NotImplementedError


def create_experiment(benchmark_name: str, workflow_name: str):
    """Persist a simple single-task workflow as an Experiment only."""
    worker = MockWorker(workflow_name)
    task = Task(
        name=workflow_name,
        description=f"Workflow for {workflow_name}",
        assigned_to=worker,
    )
    validate_task_dag(task)
    experiment, _ = persist_experiment_definition(task, benchmark_name=benchmark_name)
    return experiment


def resolve_cohort(name: str, *, metadata: CohortMetadata | None = None):
    """Resolve or create a cohort for tests."""
    return experiment_cohort_service.resolve_or_create(
        ResolveCohortRequest(name=name, metadata=metadata or CohortMetadata())
    )


def create_run(
    experiment_id,
    *,
    cohort_id=None,
    cohort_name: str | None = None,
    status: RunStatus = RunStatus.PENDING,
    final_score: float | None = None,
    normalized_score: float | None = None,
    worker_model: str = "gpt-4o-mini",
    max_questions: int = 10,
    started_offset_seconds: int | None = None,
    completed_offset_seconds: int | None = None,
    error_message: str | None = None,
    cli_request_id: str | None = None,
) -> Run:
    """Persist a run row with optional cohort lineage and timing fields."""
    run = persist_run(
        experiment_id,
        worker_model=worker_model,
        max_questions=max_questions,
        cohort_id=cohort_id,
        dispatch_metadata={
            "cohort_name": cohort_name,
            "cli_request_id": cli_request_id,
        },
    )

    now = utcnow()
    if started_offset_seconds is not None:
        run.started_at = now + timedelta(seconds=started_offset_seconds)
    if completed_offset_seconds is not None:
        run.completed_at = now + timedelta(seconds=completed_offset_seconds)
    run.status = status
    run.final_score = final_score
    run.normalized_score = normalized_score
    run.error_message = error_message

    from h_arcane.core._internal.db.queries import queries

    return queries.runs.update(run)
