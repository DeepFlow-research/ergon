"""Preparation workflows for benchmark assets."""

from __future__ import annotations

from datasets import load_dataset

from h_arcane.core.settings import settings
from h_arcane.services.setup.common import DEFAULT_RESEARCHRUBRICS_DATASET, SUPPORTED_BENCHMARKS
from h_arcane.services.setup.schemas import BenchmarkPrepareResult, BenchmarkStatus


class BenchmarkPreparationService:
    """Prepare local or remote assets for supported benchmarks."""

    def supported_benchmarks(self) -> tuple[str, ...]:
        return SUPPORTED_BENCHMARKS

    def status(self, benchmark: str, researchrubrics_dataset_name: str | None = None) -> BenchmarkStatus:
        if benchmark == "minif2f":
            from h_arcane.services.setup.readiness_service import ReadinessService

            return ReadinessService()._minif2f_status()
        if benchmark == "researchrubrics":
            from h_arcane.services.setup.readiness_service import ReadinessService

            dataset_name = researchrubrics_dataset_name or DEFAULT_RESEARCHRUBRICS_DATASET
            return ReadinessService()._researchrubrics_status(dataset_name, None)
        raise ValueError(f"Unsupported benchmark: {benchmark}")

    def prepare(
        self,
        benchmark: str,
        researchrubrics_dataset_name: str | None = None,
    ) -> BenchmarkPrepareResult:
        if benchmark == "minif2f":
            return self._prepare_minif2f()
        if benchmark == "researchrubrics":
            dataset_name = researchrubrics_dataset_name or DEFAULT_RESEARCHRUBRICS_DATASET
            return self._prepare_researchrubrics(dataset_name)
        raise ValueError(f"Unsupported benchmark: {benchmark}")

    def _prepare_minif2f(self) -> BenchmarkPrepareResult:
        from h_arcane.benchmarks.minif2f.loader import download_minif2f

        minif2f_dir = download_minif2f(settings.data_dir)
        return BenchmarkPrepareResult(
            benchmark="minif2f",
            prepared=True,
            detail="MiniF2F repository is available locally",
            location=str(minif2f_dir),
        )

    def _prepare_researchrubrics(self, dataset_name: str) -> BenchmarkPrepareResult:
        dataset = load_dataset(dataset_name, split="train")
        return BenchmarkPrepareResult(
            benchmark="researchrubrics",
            prepared=True,
            detail=f"cached {len(dataset)} ResearchRubrics samples from {dataset_name}",
            location=dataset_name,
        )
