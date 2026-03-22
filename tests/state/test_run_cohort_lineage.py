"""State tests for run lineage and cohort attachment semantics."""

from __future__ import annotations

import asyncio
from uuid import UUID

from h_arcane import Task
from h_arcane.benchmarks.minif2f.rubric import MiniF2FRubric
from h_arcane.core._internal.db.models import RunStatus
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.task.inngest_functions.benchmark_run_start import (
    _persist_workflow_step,
    _start_seeded_experiment_run_step,
)
from h_arcane.core._internal.task.persistence import persist_experiment_definition
from h_arcane.core._internal.task.validation import validate_task_dag
from tests.utils.cohort_helpers import MockWorker


def test_seeding_persists_experiment_but_not_run(clean_db):
    worker = MockWorker("seed-worker")
    task = Task(name="Seed Workflow", description="seed test", assigned_to=worker)
    validate_task_dag(task)

    experiment, resource_mapping = persist_experiment_definition(task, benchmark_name="smoke_test")

    assert experiment is not None
    assert task.id in resource_mapping
    assert resource_mapping[task.id] == []
    assert queries.runs.get_recent(limit=5) == []


def test_benchmark_run_start_persists_run_with_cohort_id_and_reuses_named_cohort(clean_db):
    first_worker = MockWorker("run-worker-1")
    first_task = Task(name="Run Workflow 1", description="run test", assigned_to=first_worker)
    validate_task_dag(first_task)

    first_result = asyncio.run(
        _persist_workflow_step(
            task=first_task,
            worker_model="gpt-4o-mini",
            max_questions=5,
            benchmark_name="smoke_test",
            request_id="req-1",
            cohort_name="lineage-cohort",
        )
    )
    second_worker = MockWorker("run-worker-2")
    second_task = Task(name="Run Workflow 2", description="run test", assigned_to=second_worker)
    validate_task_dag(second_task)
    second_result = asyncio.run(
        _persist_workflow_step(
            task=second_task,
            worker_model="gpt-4o-mini",
            max_questions=5,
            benchmark_name="smoke_test",
            request_id="req-2",
            cohort_name="lineage-cohort",
        )
    )

    first_run = queries.runs.get(UUID(first_result["run_id"]))
    second_run = queries.runs.get(UUID(second_result["run_id"]))

    assert first_run is not None
    assert second_run is not None
    assert first_run.status == RunStatus.PENDING
    assert first_run.cohort_id is not None
    assert second_run.cohort_id == first_run.cohort_id
    assert first_run.parsed_dispatch_metadata().cli_request_id == "req-1"
    assert second_run.parsed_dispatch_metadata().cohort_name == "lineage-cohort"
    assert queries.experiment_cohorts.get_by_name("lineage-cohort") is not None


def test_seeded_experiment_run_start_creates_run_from_existing_experiment(clean_db):
    worker = MockWorker("seeded-run-worker")
    task = Task(
        name="amc12a_2008_p25",
        description="theorem test := by trivial",
        assigned_to=worker,
        benchmark_specific_data={"ground_truth_proof": "theorem test := by trivial"},
        evaluator=MiniF2FRubric(benchmark="minif2f", max_score=1.0, partial_credit_for_syntax=0.2),
    )
    validate_task_dag(task)
    experiment, _ = persist_experiment_definition(task, benchmark_name="minif2f")

    result = asyncio.run(
        _start_seeded_experiment_run_step(
            experiment_id=experiment.id,
            benchmark_name=experiment.benchmark_name,
            worker_model="gpt-4o-mini",
            max_questions=3,
            request_id="seeded-req-1",
            cohort_name="seeded-lineage-cohort",
        )
    )

    run = queries.runs.get(UUID(result["run_id"]))
    refreshed_experiment = queries.experiments.get(experiment.id)

    assert run is not None
    assert run.experiment_id == experiment.id
    assert run.cohort_id is not None
    assert run.parsed_dispatch_metadata().cli_request_id == "seeded-req-1"
    assert run.parsed_dispatch_metadata().cohort_name == "seeded-lineage-cohort"
    assert refreshed_experiment is not None
    assert refreshed_experiment.task_id == "amc12a_2008_p25"
    assert refreshed_experiment.benchmark_specific_data_for()["ground_truth_proof"] == "theorem test := by trivial"
