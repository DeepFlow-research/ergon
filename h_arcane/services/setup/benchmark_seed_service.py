"""Benchmark seeding workflows for the magym CLI."""

from __future__ import annotations

from typing import Literal

from h_arcane.benchmarks.common.workers.react_worker import ReActWorker
from h_arcane.benchmarks.minif2f.config import MINIF2F_CONFIG
from h_arcane.benchmarks.minif2f.loader import load_minif2f_to_database
from h_arcane.benchmarks.researchrubrics.config import RESEARCHRUBRICS_CONFIG
from h_arcane.benchmarks.researchrubrics.loader import load_researchrubrics_to_database
from h_arcane.core._internal.db.connection import configure_database, init_db
from h_arcane.core.settings import settings
from h_arcane.services.setup.common import DEFAULT_RESEARCHRUBRICS_DATASET
from h_arcane.services.setup.schemas import BenchmarkSeedResult


class BenchmarkSeedService:
    """Seed supported benchmarks into the selected database."""

    def seed(
        self,
        benchmark: str,
        limit: int | None = None,
        database_target: Literal["main", "test"] = "main",
        model: str = "gpt-4o-mini",
        researchrubrics_dataset_name: str | None = None,
    ) -> BenchmarkSeedResult:
        original_database_url = settings.database_url
        try:
            configure_database(settings.get_database_url(database_target))
            init_db()

            if benchmark == "minif2f":
                worker = ReActWorker(model=model, config=MINIF2F_CONFIG)
                created = load_minif2f_to_database(
                    data_dir=settings.data_dir,
                    limit=limit,
                    worker=worker,
                )
            elif benchmark == "researchrubrics":
                worker = ReActWorker(model=model, config=RESEARCHRUBRICS_CONFIG)
                created = load_researchrubrics_to_database(
                    ablated_dataset_name=(
                        researchrubrics_dataset_name or DEFAULT_RESEARCHRUBRICS_DATASET
                    ),
                    limit=limit,
                    worker=worker,
                )
            else:
                raise ValueError(f"Unsupported benchmark: {benchmark}")

            return BenchmarkSeedResult(
                benchmark=benchmark,
                database_target=database_target,
                created_experiment_ids=[str(experiment_id) for experiment_id in created],
                detail=f"created {len(created)} experiments",
            )
        finally:
            configure_database(original_database_url)
