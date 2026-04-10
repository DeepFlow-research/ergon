"""Components with no dependencies beyond h-arcane.

All imports are eager and fully typed.  This module is always safe to import
regardless of which optional extras are installed.
"""

from collections.abc import Callable

from h_arcane.api import Benchmark, Evaluator, Worker
from h_arcane.core.providers.generation.model_resolution import ResolvedModel
from h_arcane.core.providers.sandbox.manager import BaseSandboxManager

from arcane_builtins.benchmarks.gdpeval.rubric import StagedRubric
from arcane_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from arcane_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from arcane_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from arcane_builtins.benchmarks.smoke_test.benchmark import SmokeTestBenchmark
from arcane_builtins.benchmarks.smoke_test.rubric import SmokeTestRubric
from arcane_builtins.evaluators.rubrics.stub_rubric import StubRubric
from arcane_builtins.evaluators.rubrics.varied_stub_rubric import VariedStubRubric
from arcane_builtins.models.cloud_passthrough import resolve_cloud
from arcane_builtins.models.vllm_backend import resolve_vllm
from arcane_builtins.workers.baselines.react_worker import ReActWorker
from arcane_builtins.workers.baselines.smoke_test_worker import SmokeTestWorker
from arcane_builtins.workers.baselines.stub_worker import StubWorker
from arcane_builtins.workers.baselines.training_stub_worker import TrainingStubWorker

WORKERS: dict[str, type[Worker]] = {
    "stub-worker": StubWorker,
    "training-stub": TrainingStubWorker,
    "smoke-test-worker": SmokeTestWorker,
    "react-v1": ReActWorker,
}

BENCHMARKS: dict[str, type[Benchmark]] = {
    "smoke-test": SmokeTestBenchmark,
    "minif2f": MiniF2FBenchmark,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "stub-rubric": StubRubric,
    "varied-stub-rubric": VariedStubRubric,
    "smoke-test-rubric": SmokeTestRubric,
    "staged-rubric": StagedRubric,
    "minif2f-rubric": MiniF2FRubric,
}

SANDBOX_MANAGERS: dict[str, type[BaseSandboxManager]] = {
    "gdpeval": GDPEvalSandboxManager,
}

MODEL_BACKENDS: dict[str, Callable[..., ResolvedModel]] = {
    "vllm": resolve_vllm,
    "openai": resolve_cloud,
    "anthropic": resolve_cloud,
    "google": resolve_cloud,
}
