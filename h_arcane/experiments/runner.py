"""Experiment runner for batch execution."""

import asyncio

import structlog

import inngest

from h_arcane.db.queries import queries
from h_arcane.db.models import RunStatus
from h_arcane.experiments.config import DEFAULT_CONFIG, ExperimentConfig
from h_arcane.benchmarks.registry import get_benchmark_loader
from h_arcane.schemas.base import BenchmarkName
from h_arcane.inngest.client import inngest_client

logger = structlog.get_logger()


class ExperimentRunner:
    """Runs experiments in batches."""

    def __init__(self, config: ExperimentConfig | None = None):
        self.config = config or DEFAULT_CONFIG

    async def run_full_suite(
        self,
        benchmark_name: BenchmarkName,
        task_limit: int | None = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Run experiments for a benchmark.

        Args:
            benchmark_name: Benchmark to run (GDPEVAL, MINIF2F, etc.)
            task_limit: Limit number of tasks (for testing)
            dry_run: If True, don't actually start runs

        Returns:
            Summary of started runs
        """
        # Get benchmark-specific loader from registry
        loader = get_benchmark_loader(benchmark_name)
        logger.info("Loading benchmark tasks", benchmark=benchmark_name.value, limit=task_limit)

        # Load to database (loader handles task loading internally)
        experiment_ids = loader(limit=task_limit)
        logger.info(
            "Loaded experiments to database",
            benchmark=benchmark_name.value,
            count=len(experiment_ids),
        )

        logger.info("Starting runs", count=len(experiment_ids))

        if dry_run:
            return {"dry_run": True, "experiments": len(experiment_ids)}

        # Start runs (fire-and-forget) - run_id will be generated inside worker_execute
        for idx, exp_id in enumerate(experiment_ids, 1):
            logger.debug(
                "Sending run/start event",
                experiment_id=str(exp_id),
                progress=f"{idx}/{len(experiment_ids)}",
            )
            try:
                # Add timeout to prevent hanging
                await asyncio.wait_for(
                    inngest_client.send(
                        inngest.Event(
                            name="run/start",
                            data={
                                "experiment_id": str(exp_id),
                                "worker_model": self.config.worker_model,
                                "max_questions": self.config.max_questions,
                            },
                        )
                    ),
                    timeout=5.0,  # 5 second timeout
                )
                logger.debug("Event sent successfully", experiment_id=str(exp_id))
            except asyncio.TimeoutError:
                logger.warning(
                    "Event send timed out",
                    experiment_id=str(exp_id),
                    message="Continuing anyway (fire-and-forget)",
                )
            except Exception as e:
                logger.error("Failed to send event", experiment_id=str(exp_id), error=str(e))
                # Don't raise - continue with other events (fire-and-forget)

        return {"started": len(experiment_ids), "experiments": len(experiment_ids)}

    async def get_progress(self) -> dict:
        """Get current experiment progress."""
        stats = queries.runs.get_stats()
        completion_rate = stats["completed"] / stats["total"] if stats["total"] > 0 else 0.0
        return {
            "pending": stats["pending"],
            "running": stats["running"],
            "completed": stats["completed"],
            "failed": stats["failed"],
            "total": stats["total"],
            "completion_rate": round(completion_rate, 4),
        }

    async def retry_failed(self) -> int:
        """Retry failed runs."""
        failed_runs = queries.runs.get_by_status(RunStatus.FAILED)
        retried = 0

        for run in failed_runs:
            queries.runs.reset_for_retry(run.id)
            await inngest_client.send(
                inngest.Event(
                    name="run/start",
                    data={
                        "experiment_id": str(run.experiment_id),
                        "worker_model": run.worker_model,
                        "max_questions": run.max_questions,
                    },
                )
            )
            retried += 1

        logger.info("Retried failed runs", count=retried)
        return retried
