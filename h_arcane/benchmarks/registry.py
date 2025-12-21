"""Benchmark registry for config, loader, and skills lookup."""

from pathlib import Path
from typing import Callable, TypedDict

from h_arcane.schemas.base import BenchmarkName, WorkerConfig
from h_arcane.benchmarks.gdpeval.config import GDPEVAL_CONFIG
from h_arcane.benchmarks.gdpeval.loader import load_gdpeval_to_database
from h_arcane.benchmarks.minif2f.config import MINIF2F_CONFIG
from h_arcane.benchmarks.minif2f.loader import load_minif2f_to_database


class BenchmarkConfig(TypedDict):
    """Configuration for a benchmark."""

    config: WorkerConfig
    skills_dir: Path
    loader: Callable


# Compute paths relative to this file
_SKILLS_ROOT = Path(__file__).parent.parent / "skills"


BENCHMARK_CONFIGS: dict[BenchmarkName, BenchmarkConfig] = {
    BenchmarkName.GDPEVAL: {
        "config": GDPEVAL_CONFIG,
        "skills_dir": _SKILLS_ROOT / "gdpeval",
        "loader": load_gdpeval_to_database,
    },
    BenchmarkName.MINIF2F: {
        "config": MINIF2F_CONFIG,
        "skills_dir": _SKILLS_ROOT / "minif2f",
        "loader": load_minif2f_to_database,
    },
}


def get_worker_config(benchmark_name: BenchmarkName) -> WorkerConfig:
    """Get worker configuration for a benchmark."""
    return BENCHMARK_CONFIGS[benchmark_name]["config"]


def get_skills_dir(benchmark_name: BenchmarkName) -> Path:
    """Get skills directory for a benchmark."""
    return BENCHMARK_CONFIGS[benchmark_name]["skills_dir"]


def get_benchmark_loader(benchmark_name: BenchmarkName) -> Callable:
    """Get benchmark loader function."""
    return BENCHMARK_CONFIGS[benchmark_name]["loader"]
