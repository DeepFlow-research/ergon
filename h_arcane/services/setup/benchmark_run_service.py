"""Cohort-aware benchmark execution workflows for the magym CLI."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

import inngest

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.core._internal.db.models import Experiment
from h_arcane.benchmarks.registry import get_workflow_factories
from h_arcane.core._internal.db.models import RunStatus
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.events import BenchmarkRunRequest
from h_arcane.core.runner import ExecutionResult
from h_arcane.core.task import TaskStatus
from h_arcane.services.setup.common import (
    RUNNABLE_BENCHMARKS,
    SEEDED_EXPERIMENT_RUN_BENCHMARKS,
    WORKFLOW_RUN_BENCHMARKS,
)


class BenchmarkRunService:
    """Run benchmark workflows into a named cohort via Inngest."""

    def runnable_benchmarks(self) -> tuple[str, ...]:
        """Return benchmarks currently supported by `magym benchmark run`."""
        return RUNNABLE_BENCHMARKS

    def workflows_for_benchmark(self, benchmark: str) -> tuple[str, ...]:
        """Return the available workflow names for a runnable benchmark."""
        benchmark_name = BenchmarkName(benchmark)
        return tuple(get_workflow_factories(benchmark_name).keys())

    def uses_workflow_factories(self, benchmark: str) -> bool:
        """Return True when a benchmark should be launched via workflow factories."""
        return benchmark in WORKFLOW_RUN_BENCHMARKS

    def uses_seeded_experiments(self, benchmark: str) -> bool:
        """Return True when a benchmark should be launched from seeded Experiment rows."""
        return benchmark in SEEDED_EXPERIMENT_RUN_BENCHMARKS

    async def run(
        self,
        benchmark: str,
        cohort_name: str,
        workflow_names: list[str] | None = None,
        experiment_ids: list[UUID] | None = None,
        task_ids: list[str] | None = None,
        limit: int | None = None,
        model: str = "gpt-4o",
        timeout: int = 300,
        max_questions: int = 10,
    ) -> dict[str, ExecutionResult]:
        """Run one or more benchmark workflows and return per-workflow results."""
        benchmark_name = BenchmarkName(benchmark)
        if benchmark not in self.runnable_benchmarks():
            supported = ", ".join(self.runnable_benchmarks())
            raise ValueError(f"Benchmark '{benchmark}' is not runnable via magym. Supported: {supported}")

        if self.uses_workflow_factories(benchmark):
            workflow_names = workflow_names or []
            available_workflows = self.workflows_for_benchmark(benchmark)
            for workflow_name in workflow_names:
                if workflow_name not in available_workflows:
                    available = ", ".join(available_workflows)
                    raise ValueError(
                        f"Unknown workflow '{workflow_name}' for benchmark '{benchmark}'. Available: {available}"
                    )

            results: dict[str, ExecutionResult] = {}
            for workflow_name in workflow_names:
                started_at = datetime.now(timezone.utc)
                try:
                    results[workflow_name] = await self._run_single_workflow(
                        benchmark_name=benchmark_name,
                        workflow_name=workflow_name,
                        experiment_id=None,
                        cohort_name=cohort_name,
                        model=model,
                        timeout=timeout,
                        max_questions=max_questions,
                        started_at=started_at,
                    )
                except Exception as exc:
                    results[workflow_name] = ExecutionResult(
                        success=False,
                        status=TaskStatus.FAILED,
                        error=str(exc),
                        started_at=started_at,
                        duration_seconds=0.0,
                    )
            return results

        experiments = self.select_seeded_experiments(
            benchmark=benchmark_name,
            experiment_ids=experiment_ids or [],
            task_ids=task_ids or [],
            limit=limit,
        )
        results: dict[str, ExecutionResult] = {}
        for experiment in experiments:
            result_label = experiment.task_id
            started_at = datetime.now(timezone.utc)
            try:
                results[result_label] = await self._run_single_workflow(
                    benchmark_name=benchmark_name,
                    workflow_name=None,
                    experiment_id=experiment.id,
                    cohort_name=cohort_name,
                    model=model,
                    timeout=timeout,
                    max_questions=max_questions,
                    started_at=started_at,
                )
            except Exception as exc:
                results[result_label] = ExecutionResult(
                    success=False,
                    status=TaskStatus.FAILED,
                    error=str(exc),
                    started_at=started_at,
                    duration_seconds=0.0,
                )
        return results

    def select_seeded_experiments(
        self,
        benchmark: BenchmarkName,
        experiment_ids: list[UUID],
        task_ids: list[str],
        limit: int | None,
    ) -> list[Experiment]:
        """Select seeded experiments for a dataset-driven benchmark run."""
        selector_count = sum(
            [
                1 if experiment_ids else 0,
                1 if task_ids else 0,
                1 if limit is not None else 0,
            ]
        )
        if selector_count != 1:
            raise ValueError(
                "Seeded benchmark runs require exactly one selector: "
                "--experiment-id, --task-id, or --limit"
            )

        if experiment_ids:
            experiments = queries.experiments.get_many(experiment_ids)
            by_id = {experiment.id: experiment for experiment in experiments}
            missing_ids = [experiment_id for experiment_id in experiment_ids if experiment_id not in by_id]
            if missing_ids:
                missing = ", ".join(str(experiment_id) for experiment_id in missing_ids)
                raise ValueError(f"Experiment(s) not found: {missing}")
            ordered = [by_id[experiment_id] for experiment_id in experiment_ids]
            self._validate_selected_benchmark(ordered, benchmark)
            return ordered

        if task_ids:
            experiments = queries.experiments.get_by_task_ids(task_ids, benchmark)
            by_task_id = {experiment.task_id: experiment for experiment in experiments}
            missing_task_ids = [task_id for task_id in task_ids if task_id not in by_task_id]
            if missing_task_ids:
                missing = ", ".join(missing_task_ids)
                raise ValueError(f"Experiment task_id(s) not found for {benchmark.value}: {missing}")
            return [by_task_id[task_id] for task_id in task_ids]

        experiments = queries.experiments.list_by_benchmark(benchmark, limit=limit)
        if not experiments:
            raise ValueError(f"No seeded experiments found for benchmark '{benchmark.value}'")
        return list(reversed(experiments))

    @staticmethod
    def _validate_selected_benchmark(experiments: list[Experiment], benchmark: BenchmarkName) -> None:
        """Ensure all selected experiments belong to the requested benchmark."""
        mismatched = [experiment.id for experiment in experiments if experiment.benchmark_name != benchmark]
        if mismatched:
            ids = ", ".join(str(experiment_id) for experiment_id in mismatched)
            raise ValueError(f"Selected experiments do not belong to benchmark '{benchmark.value}': {ids}")

    async def _run_single_workflow(
        self,
        benchmark_name: BenchmarkName,
        workflow_name: str | None,
        experiment_id: UUID | None,
        cohort_name: str,
        model: str,
        timeout: int,
        max_questions: int,
        started_at: datetime,
    ) -> ExecutionResult:
        """Run a single benchmark workflow via BenchmarkRunRequest."""
        request_id = str(uuid4())
        event = BenchmarkRunRequest(
            request_id=request_id,
            cohort_name=cohort_name,
            benchmark_name=benchmark_name.value,
            workflow_name=workflow_name,
            experiment_id=experiment_id,
            model=model,
            timeout_seconds=timeout,
            max_questions=max_questions,
        )
        await inngest_client.send(
            inngest.Event(name=BenchmarkRunRequest.name, data=event.model_dump(mode="json"))
        )
        run_id = await self._poll_for_run_creation(request_id, timeout)
        if run_id is None:
            return ExecutionResult(
                success=False,
                status=TaskStatus.FAILED,
                error="Timeout waiting for run to be created",
                started_at=started_at,
                duration_seconds=(datetime.now(timezone.utc) - started_at).total_seconds(),
                experiment_id=experiment_id,
            )
        return await self._poll_for_completion(run_id, timeout, started_at)

    async def _poll_for_run_creation(
        self,
        request_id: str,
        timeout: int,
        poll_interval: float = 1.0,
    ) -> UUID | None:
        """Poll for creation of a run tied to the request ID."""
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            runs = queries.runs.get_recent(limit=20)
            for run in runs:
                if run.cli_request_id() == request_id:
                    return run.id
            await asyncio.sleep(poll_interval)
        return None

    async def _poll_for_completion(
        self,
        run_id: UUID,
        timeout: int,
        started_at: datetime,
        poll_interval: float = 1.0,
    ) -> ExecutionResult:
        """Poll until the run reaches a terminal state or times out."""
        start_time = time.time()
        terminal_statuses = {RunStatus.COMPLETED, RunStatus.FAILED}
        while True:
            run = queries.runs.get(run_id)
            if run is None:
                return ExecutionResult(
                    success=False,
                    status=TaskStatus.FAILED,
                    error=f"Run {run_id} not found",
                    started_at=started_at,
                    duration_seconds=(datetime.now(timezone.utc) - started_at).total_seconds(),
                    run_id=run_id,
                )

            if run.status in terminal_statuses:
                execution_result = run.parsed_execution_result()
                if execution_result is not None:
                    return execution_result

                completed_at = run.completed_at or datetime.now(timezone.utc)
                duration_seconds = (completed_at - started_at).total_seconds()
                return ExecutionResult(
                    success=run.status == RunStatus.COMPLETED,
                    status=(
                        TaskStatus.COMPLETED
                        if run.status == RunStatus.COMPLETED
                        else TaskStatus.FAILED
                    ),
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_seconds=duration_seconds,
                    run_id=run.id,
                    experiment_id=run.experiment_id,
                    error=run.error_message,
                )

            if (time.time() - start_time) >= timeout:
                return ExecutionResult(
                    success=False,
                    status=TaskStatus.FAILED,
                    error="Timeout waiting for run completion",
                    started_at=started_at,
                    duration_seconds=(datetime.now(timezone.utc) - started_at).total_seconds(),
                    run_id=run_id,
                    experiment_id=run.experiment_id,
                )

            await asyncio.sleep(poll_interval)
