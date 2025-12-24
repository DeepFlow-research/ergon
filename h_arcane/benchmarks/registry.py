"""Benchmark registry for config, loader, factories, and evaluator lookup."""

from pathlib import Path
from typing import Callable, TypedDict

from h_arcane.core.models.enums import BenchmarkName
from h_arcane.benchmarks.common.workers.config import WorkerConfig

# Import benchmark implementations
from h_arcane.benchmarks.gdpeval.config import GDPEVAL_CONFIG
from h_arcane.benchmarks.gdpeval.loader import load_gdpeval_to_database
from h_arcane.benchmarks.gdpeval.factories import (
    create_stakeholder as gdpeval_create_stakeholder,
    create_toolkit as gdpeval_create_toolkit,
)

from h_arcane.benchmarks.minif2f.config import MINIF2F_CONFIG
from h_arcane.benchmarks.minif2f.loader import load_minif2f_to_database
from h_arcane.benchmarks.minif2f.factories import (
    create_stakeholder as minif2f_create_stakeholder,
    create_toolkit as minif2f_create_toolkit,
)


class BenchmarkConfig(TypedDict):
    """Full configuration for a benchmark."""

    config: WorkerConfig
    skills_dir: Path
    loader: Callable
    stakeholder_factory: Callable  # (Experiment) -> BaseStakeholder
    toolkit_factory: Callable  # (run_id, stakeholder, sandbox, max_q) -> BaseToolkit
    # NOTE: No rubric_evaluator - evaluation logic is on BaseRubric.compute_scores()


# Compute paths relative to this file
_BENCHMARKS_DIR = Path(__file__).parent


BENCHMARK_CONFIGS: dict[BenchmarkName, BenchmarkConfig] = {
    BenchmarkName.GDPEVAL: {
        "config": GDPEVAL_CONFIG,
        "skills_dir": _BENCHMARKS_DIR / "gdpeval" / "skills",
        "loader": load_gdpeval_to_database,
        "stakeholder_factory": gdpeval_create_stakeholder,
        "toolkit_factory": gdpeval_create_toolkit,
    },
    BenchmarkName.MINIF2F: {
        "config": MINIF2F_CONFIG,
        "skills_dir": _BENCHMARKS_DIR / "minif2f" / "skills",
        "loader": load_minif2f_to_database,
        "stakeholder_factory": minif2f_create_stakeholder,
        "toolkit_factory": minif2f_create_toolkit,
    },
}


def _get_config(benchmark_name: BenchmarkName) -> BenchmarkConfig:
    """Get config for benchmark, raising clear error if not implemented."""
    if benchmark_name not in BENCHMARK_CONFIGS:
        implemented = [b.value for b in BENCHMARK_CONFIGS.keys()]
        raise NotImplementedError(
            f"Benchmark '{benchmark_name.value}' is not implemented. "
            f"Implemented benchmarks: {implemented}"
        )
    return BENCHMARK_CONFIGS[benchmark_name]


# Getters - all raise NotImplementedError for unknown benchmarks
def get_worker_config(benchmark_name: BenchmarkName) -> WorkerConfig:
    """Get worker configuration for a benchmark."""
    return _get_config(benchmark_name)["config"]


def get_skills_dir(benchmark_name: BenchmarkName) -> Path:
    """Get skills directory for a benchmark."""
    return _get_config(benchmark_name)["skills_dir"]


def get_benchmark_loader(benchmark_name: BenchmarkName) -> Callable:
    """Get benchmark loader function."""
    return _get_config(benchmark_name)["loader"]


def get_stakeholder_factory(benchmark_name: BenchmarkName) -> Callable:
    """Get factory function: (Experiment) -> BaseStakeholder."""
    return _get_config(benchmark_name)["stakeholder_factory"]


def get_toolkit_factory(benchmark_name: BenchmarkName) -> Callable:
    """Get factory function: (run_id, stakeholder, sandbox, max_q) -> BaseToolkit."""
    return _get_config(benchmark_name)["toolkit_factory"]
