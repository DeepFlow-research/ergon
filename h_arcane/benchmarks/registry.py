"""Benchmark registry for config, loader, factories, and evaluator lookup."""

from pathlib import Path
from typing import Callable, TypedDict

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.common.workers.config import WorkerConfig
from h_arcane.core.infrastructure.sandbox import BaseSandboxManager

# Import benchmark implementations
from h_arcane.benchmarks.gdpeval.config import GDPEVAL_CONFIG
from h_arcane.benchmarks.gdpeval.loader import load_gdpeval_to_database
from h_arcane.benchmarks.gdpeval.factories import (
    create_stakeholder as gdpeval_create_stakeholder,
    create_toolkit as gdpeval_create_toolkit,
)
from h_arcane.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager

from h_arcane.benchmarks.minif2f.config import MINIF2F_CONFIG
from h_arcane.benchmarks.minif2f.loader import load_minif2f_to_database
from h_arcane.benchmarks.minif2f.factories import (
    create_stakeholder as minif2f_create_stakeholder,
    create_toolkit as minif2f_create_toolkit,
)
from h_arcane.benchmarks.minif2f.sandbox import MiniF2FSandboxManager

from h_arcane.benchmarks.researchrubrics.config import RESEARCHRUBRICS_CONFIG
from h_arcane.benchmarks.researchrubrics.loader import load_researchrubrics_to_database
from h_arcane.benchmarks.researchrubrics.factories import (
    create_stakeholder as researchrubrics_create_stakeholder,
    create_toolkit as researchrubrics_create_toolkit,
)
from h_arcane.benchmarks.researchrubrics.sandbox import ResearchRubricsSandboxManager


class BenchmarkConfig(TypedDict):
    """Full configuration for a benchmark."""

    config: WorkerConfig
    skills_dir: Path
    loader: Callable
    stakeholder_factory: Callable  # (Experiment) -> BaseStakeholder
    toolkit_factory: Callable  # (run_id, experiment_id, stakeholder, sandbox, max_q) -> BaseToolkit
    sandbox_manager_class: type[BaseSandboxManager]
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
        "sandbox_manager_class": GDPEvalSandboxManager,
    },
    BenchmarkName.MINIF2F: {
        "config": MINIF2F_CONFIG,
        "skills_dir": _BENCHMARKS_DIR / "minif2f" / "skills",
        "loader": load_minif2f_to_database,
        "stakeholder_factory": minif2f_create_stakeholder,
        "toolkit_factory": minif2f_create_toolkit,
        "sandbox_manager_class": MiniF2FSandboxManager,
    },
    BenchmarkName.RESEARCHRUBRICS: {
        "config": RESEARCHRUBRICS_CONFIG,
        "skills_dir": _BENCHMARKS_DIR / "researchrubrics" / "skills",
        "loader": load_researchrubrics_to_database,
        "stakeholder_factory": researchrubrics_create_stakeholder,
        "toolkit_factory": researchrubrics_create_toolkit,
        "sandbox_manager_class": ResearchRubricsSandboxManager,
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
    """Get factory function: (run_id, experiment_id, stakeholder, sandbox, max_q) -> BaseToolkit."""
    return _get_config(benchmark_name)["toolkit_factory"]


def get_sandbox_manager(benchmark_name: BenchmarkName) -> BaseSandboxManager:
    """Get sandbox manager for benchmark (singleton per benchmark type).

    Each benchmark has its own sandbox manager subclass that handles
    benchmark-specific dependency installation.

    Args:
        benchmark_name: The benchmark to get manager for

    Returns:
        Singleton instance of the benchmark's sandbox manager
    """
    return _get_config(benchmark_name)["sandbox_manager_class"]()
