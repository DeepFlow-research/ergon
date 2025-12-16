"""Benchmark registry for config and loader lookup."""

from h_arcane.schemas.base import BenchmarkName, WorkerConfig
from h_arcane.benchmarks.gdpeval.config import GDPEVAL_CONFIG
from h_arcane.benchmarks.gdpeval.loader import load_gdpeval_to_database

WORKER_CONFIGS: dict[BenchmarkName, WorkerConfig] = {
    BenchmarkName.GDPEVAL: GDPEVAL_CONFIG,
}


def get_worker_config(benchmark_name: BenchmarkName) -> WorkerConfig:
    """Get worker configuration for a benchmark."""
    return WORKER_CONFIGS[benchmark_name]


def get_benchmark_loader(benchmark_name: BenchmarkName):
    """Get benchmark loader function."""
    if benchmark_name == BenchmarkName.GDPEVAL:
        return load_gdpeval_to_database
    raise ValueError(f"Unknown benchmark: {benchmark_name}")
