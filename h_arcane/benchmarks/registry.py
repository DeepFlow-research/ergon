"""Benchmark registry for config and loader lookup."""

from h_arcane.schemas.base import BenchmarkName, WorkerConfig
from h_arcane.benchmarks.gdpeval.config import GDPEVAL_CONFIG
from h_arcane.benchmarks.gdpeval.loader import load_gdpeval_to_database
from h_arcane.benchmarks.minif2f.config import MINIF2F_CONFIG
from h_arcane.benchmarks.minif2f.loader import load_minif2f_to_database

WORKER_CONFIGS: dict[BenchmarkName, WorkerConfig] = {
    BenchmarkName.GDPEVAL: GDPEVAL_CONFIG,
    BenchmarkName.MINIF2F: MINIF2F_CONFIG,
}


def get_worker_config(benchmark_name: BenchmarkName) -> WorkerConfig:
    """Get worker configuration for a benchmark."""
    return WORKER_CONFIGS[benchmark_name]


def get_benchmark_loader(benchmark_name: BenchmarkName):
    """Get benchmark loader function."""
    if benchmark_name == BenchmarkName.GDPEVAL:
        return load_gdpeval_to_database
    elif benchmark_name == BenchmarkName.MINIF2F:
        return load_minif2f_to_database
    raise ValueError(f"Unknown benchmark: {benchmark_name}")
