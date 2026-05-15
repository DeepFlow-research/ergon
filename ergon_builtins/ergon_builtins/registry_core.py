"""Components with no dependencies beyond ergon-core.

All imports are eager and fully typed.  This module is always safe to import
regardless of which optional extras are installed.
"""

from collections.abc import Callable
from pathlib import Path

from ergon_core.api import Benchmark, Worker
from ergon_core.api.registry import ComponentRegistry, registry
from ergon_core.api.rubric import Evaluator
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager

from ergon_builtins.benchmarks.gdpeval.rubric import StagedRubric
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.benchmarks.minif2f._legacy_workers import MiniF2FReactWorker
from ergon_builtins.benchmarks.swebench_verified.benchmark import SweBenchVerifiedBenchmark
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.benchmarks.swebench_verified.rubric import SWEBenchRubric
from ergon_builtins.benchmarks.swebench_verified.worker_factory import SWEBenchReactWorker
from ergon_builtins.models.cloud_passthrough import resolve_cloud
from ergon_builtins.models.openrouter_backend import resolve_openrouter
from ergon_builtins.models.openrouter_responses_backend import resolve_openrouter_responses
from ergon_builtins.models.resolution import ResolvedModel, register_model_backend
from ergon_builtins.models.vllm_backend import resolve_vllm
from ergon_builtins.shared.workers.training_stub_worker import TrainingStubWorker

WORKERS: dict[str, type[Worker]] = {
    "training-stub": TrainingStubWorker,
    "minif2f-react": MiniF2FReactWorker,
    "swebench-react": SWEBenchReactWorker,
    # Test-only smoke workers register via tests/e2e/_fixtures/__init__.py;
    # they do NOT appear here (production CLI paths don't import tests).
}

BENCHMARKS: dict[str, type[Benchmark]] = {
    "minif2f": MiniF2FBenchmark,
    "swebench-verified": SweBenchVerifiedBenchmark,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "staged-rubric": StagedRubric,
    "gdpeval-staged-rubric": StagedRubric,
    "minif2f-rubric": MiniF2FRubric,
    "swebench-rubric": SWEBenchRubric,
}

SANDBOX_MANAGERS: dict[str, type[BaseSandboxManager]] = {
    "gdpeval": GDPEvalSandboxManager,
    "minif2f": MiniF2FSandboxManager,
    "swebench-verified": SWEBenchSandboxManager,
}

SANDBOX_TEMPLATES: dict[str, Path] = {
    "minif2f": Path(__file__).parent / "benchmarks/minif2f/sandbox_template",
    "swebench-verified": Path(__file__).parent / "benchmarks/swebench_verified/sandbox",
}

MODEL_BACKENDS: dict[str, Callable[..., ResolvedModel]] = {
    "vllm": resolve_vllm,
    "openai": resolve_cloud,
    "anthropic": resolve_cloud,
    "google": resolve_cloud,
    "openrouter": resolve_openrouter,
    "openai-responses": resolve_openrouter_responses,
}


def register_core_builtins(target: ComponentRegistry = registry) -> None:
    """Register builtins that are safe without optional dependency extras."""

    for slug, worker_factory in WORKERS.items():
        target.register_worker(slug, worker_factory)
    for benchmark_cls in BENCHMARKS.values():
        target.register_benchmark(benchmark_cls)
    for slug, evaluator_cls in EVALUATORS.items():
        target.register_evaluator(evaluator_cls, slug=slug)
    for slug, manager_cls in SANDBOX_MANAGERS.items():
        target.register_sandbox_manager(slug, manager_cls)
    for prefix, resolver in MODEL_BACKENDS.items():
        register_model_backend(prefix, resolver)
