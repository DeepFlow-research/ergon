"""Components with no dependencies beyond ergon-core.

All imports are eager and fully typed.  This module is always safe to import
regardless of which optional extras are installed.
"""

from collections.abc import Callable
from pathlib import Path

from ergon_core.api import Benchmark, Evaluator, Worker
from ergon_core.core.providers.generation.model_resolution import ResolvedModel
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

from ergon_builtins.benchmarks.gdpeval.rubric import StagedRubric
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.benchmarks.minif2f.smoke import MiniF2FSmokeBenchmark
from ergon_builtins.benchmarks.swebench_verified.benchmark import SweBenchVerifiedBenchmark
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.evaluators.rubrics.stub_rubric import StubRubric
from ergon_builtins.evaluators.rubrics.swebench_rubric import SWEBenchRubric
from ergon_builtins.evaluators.rubrics.varied_stub_rubric import VariedStubRubric
from ergon_builtins.models.cloud_passthrough import resolve_cloud
from ergon_builtins.models.vllm_backend import resolve_vllm
from ergon_builtins.workers.baselines.manager_researcher_worker import ManagerResearcherWorker
from ergon_builtins.workers.baselines.minif2f_react_worker import MiniF2FReActWorker
from ergon_builtins.workers.baselines.react_worker import ReActWorker
from ergon_builtins.workers.baselines.swebench_worker import SWEBenchReActWorker
from ergon_builtins.workers.baselines.training_stub_worker import TrainingStubWorker
from ergon_builtins.workers.minif2f import MiniF2FManagerWorker, MiniF2FProverWorker

# NOTE: ``StubWorker`` is intentionally *not* registered here.  The class is
# still importable from ``ergon_builtins.workers.baselines`` for use as an
# internal test fixture (see tests/state), but it is not a CLI-visible slug.
# See ergon_paper_plans/roadmap/code/backlog/stub-consolidation/RFC.md §2.

WORKERS: dict[str, type[Worker]] = {
    "training-stub": TrainingStubWorker,
    "react-v1": ReActWorker,
    "minif2f-react": MiniF2FReActWorker,
    "minif2f-manager": MiniF2FManagerWorker,
    "minif2f-prover": MiniF2FProverWorker,
    "swebench-react": SWEBenchReActWorker,
    "manager-researcher": ManagerResearcherWorker,
}

BENCHMARKS: dict[str, type[Benchmark]] = {
    "minif2f": MiniF2FBenchmark,
    "minif2f-smoke": MiniF2FSmokeBenchmark,
    "swebench-verified": SweBenchVerifiedBenchmark,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "stub-rubric": StubRubric,
    "varied-stub-rubric": VariedStubRubric,
    "staged-rubric": StagedRubric,
    "minif2f-rubric": MiniF2FRubric,
    "swebench-rubric": SWEBenchRubric,
}

SANDBOX_MANAGERS: dict[str, type[BaseSandboxManager]] = {
    "gdpeval": GDPEvalSandboxManager,
    "minif2f": MiniF2FSandboxManager,
    "minif2f-smoke": MiniF2FSandboxManager,
    "swebench-verified": SWEBenchSandboxManager,
}

SANDBOX_TEMPLATES: dict[str, Path] = {
    "minif2f": Path(__file__).parent / "benchmarks/minif2f/sandbox",
    "minif2f-smoke": Path(__file__).parent / "benchmarks/minif2f/sandbox",
    "swebench-verified": Path(__file__).parent / "benchmarks/swebench_verified/sandbox",
}

MODEL_BACKENDS: dict[str, Callable[..., ResolvedModel]] = {
    "vllm": resolve_vllm,
    "openai": resolve_cloud,
    "anthropic": resolve_cloud,
    "google": resolve_cloud,
}
