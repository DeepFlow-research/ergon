"""Experiment runner for batch execution."""

from uuid import UUID

import structlog

import inngest

from h_arcane.db.queries import queries
from h_arcane.db.models import RunStatus
from h_arcane.experiments.config import BaselineType, DEFAULT_CONFIG, ExperimentConfig
from h_arcane.experiments.loader import load_gdpeval_tasks, load_to_database
from h_arcane.inngest.client import inngest_client

logger = structlog.get_logger()


class ExperimentRunner:
    """Runs experiments in batches."""

    def __init__(self, config: ExperimentConfig | None = None):
        self.config = config or DEFAULT_CONFIG

    async def run_full_suite(
        self,
        task_limit: int | None = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Run all GDPEval experiments.

        Args:
            task_limit: Limit number of tasks (for testing)
            dry_run: If True, don't actually start runs

        Returns:
            Summary of started runs
        """
        # Load tasks
        logger.info("Loading GDPEval tasks", limit=task_limit)
        tasks = load_gdpeval_tasks(limit=task_limit)

        # Load to database
        logger.info("Loading tasks to database", count=len(tasks))
        experiment_ids = load_to_database(tasks)

        # Create one run per experiment
        run_ids = []
        for exp_id in experiment_ids:
            run_id = await self._create_run(exp_id)
            run_ids.append(run_id)

        logger.info("Created runs", count=len(run_ids))

        if dry_run:
            return {"dry_run": True, "experiments": len(experiment_ids), "runs": len(run_ids)}

        # Start runs (fire-and-forget)
        import asyncio

        logger.info("Starting runs", count=len(run_ids))
        for idx, run_id in enumerate(run_ids, 1):
            logger.debug(
                "Sending run/start event", run_id=str(run_id), progress=f"{idx}/{len(run_ids)}"
            )
            try:
                # Add timeout to prevent hanging
                await asyncio.wait_for(
                    inngest_client.send(
                        inngest.Event(
                            name="run/start",
                            data={"run_id": str(run_id)},
                        )
                    ),
                    timeout=5.0,  # 5 second timeout
                )
                logger.debug("Event sent successfully", run_id=str(run_id))
            except asyncio.TimeoutError:
                logger.warning(
                    "Event send timed out",
                    run_id=str(run_id),
                    message="Continuing anyway (fire-and-forget)",
                )
            except Exception as e:
                logger.error("Failed to send event", run_id=str(run_id), error=str(e))
                # Don't raise - continue with other events (fire-and-forget)

        return {"started": len(run_ids), "experiments": len(experiment_ids)}

    async def _create_run(self, experiment_id: UUID) -> UUID:
        """Create a run record with configured baseline."""
        # Select worker based on baseline type
        # For now, only ReActWorker is available
        if self.config.baseline == BaselineType.REACT:
            worker_model = self.config.worker_model
        else:
            raise ValueError(f"Unknown baseline: {self.config.baseline}")

        run = queries.runs.create(
            experiment_id=experiment_id,
            worker_model=worker_model,
            max_questions=self.config.max_questions,
        )
        return run.id

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
                    data={"run_id": str(run.id)},
                )
            )
            retried += 1

        logger.info("Retried failed runs", count=retried)
        return retried
