"""Components with no dependencies beyond ergon-core.

All imports are eager and fully typed.  This module is always safe to import
regardless of which optional extras are installed.
"""

from collections.abc import Callable
from pathlib import Path

from ergon_core.api import Benchmark, Evaluator, Worker
from ergon_core.core.providers.generation.model_resolution import ResolvedModel
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

from ergon_builtins.benchmarks.delegation_smoke.benchmark import DelegationSmokeBenchmark
from ergon_builtins.benchmarks.gdpeval.rubric import StagedRubric
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.benchmarks.minif2f.smoke_rubric import MiniF2FSmokeRubric
from ergon_builtins.benchmarks.swebench_verified.benchmark import SweBenchVerifiedBenchmark
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.benchmarks.swebench_verified.smoke_rubric import SweBenchSmokeRubric
from ergon_builtins.benchmarks.researchrubrics.smoke import (
    ResearchRubricsSmokeTestBenchmark,
)
from ergon_builtins.benchmarks.researchrubrics.smoke_rubric import (
    ResearchRubricsSmokeRubric,
)
from ergon_builtins.benchmarks.smoke_test.benchmark import SmokeTestBenchmark
from ergon_builtins.benchmarks.smoke_test.rubric import SmokeTestRubric
from ergon_builtins.evaluators.rubrics.stub_rubric import StubRubric
from ergon_builtins.evaluators.rubrics.swebench_rubric import SWEBenchRubric
from ergon_builtins.evaluators.rubrics.varied_stub_rubric import VariedStubRubric
from ergon_builtins.models.cloud_passthrough import resolve_cloud
from ergon_builtins.models.vllm_backend import resolve_vllm
from ergon_builtins.workers.baselines.manager_researcher_worker import ManagerResearcherWorker
from ergon_builtins.workers.baselines.minif2f_react_worker import MiniF2FReActWorker
from ergon_builtins.workers.baselines.react_generic_worker import ReActGenericWorker
from ergon_builtins.workers.baselines.react_worker import ReActWorker
from ergon_builtins.workers.baselines.smoke_test_worker import SmokeTestWorker
from ergon_builtins.workers.baselines.stub_worker import StubWorker
from ergon_builtins.workers.baselines.swebench_worker import SWEBenchReActWorker
from ergon_builtins.workers.baselines.training_stub_worker import TrainingStubWorker
from ergon_builtins.workers.research_rubrics.stub_worker import (
    StubResearchRubricsWorker,
)
from ergon_builtins.workers.stubs.canonical_smoke_worker import CanonicalSmokeWorker

WORKERS: dict[str, type[Worker]] = {
    "stub-worker": StubWorker,
    "training-stub": TrainingStubWorker,
    "smoke-test-worker": SmokeTestWorker,
    "react-v1": ReActWorker,
    "react-generic": ReActGenericWorker,
    "minif2f-react": MiniF2FReActWorker,
    "swebench-react": SWEBenchReActWorker,
    "manager-researcher": ManagerResearcherWorker,
    "researcher": StubWorker,
    "researchrubrics-stub": StubResearchRubricsWorker,
    "canonical-smoke": CanonicalSmokeWorker,
}

BENCHMARKS: dict[str, type[Benchmark]] = {
    "smoke-test": SmokeTestBenchmark,
    "minif2f": MiniF2FBenchmark,
    "delegation-smoke": DelegationSmokeBenchmark,
    "researchrubrics-smoke": ResearchRubricsSmokeTestBenchmark,
    "swebench-verified": SweBenchVerifiedBenchmark,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "stub-rubric": StubRubric,
    "varied-stub-rubric": VariedStubRubric,
    "smoke-test-rubric": SmokeTestRubric,
    "staged-rubric": StagedRubric,
    "minif2f-rubric": MiniF2FRubric,
    "swebench-rubric": SWEBenchRubric,
    "researchrubrics-smoke-rubric": ResearchRubricsSmokeRubric,
    "minif2f-smoke-rubric": MiniF2FSmokeRubric,
    "swebench-smoke-rubric": SweBenchSmokeRubric,
}

SANDBOX_MANAGERS: dict[str, type[BaseSandboxManager]] = {
    "gdpeval": GDPEvalSandboxManager,
    "minif2f": MiniF2FSandboxManager,
    "swebench-verified": SWEBenchSandboxManager,
}

SANDBOX_TEMPLATES: dict[str, Path] = {
    "minif2f": Path(__file__).parent / "benchmarks/minif2f/sandbox",
    "swebench-verified": Path(__file__).parent / "benchmarks/swebench_verified/sandbox",
}

MODEL_BACKENDS: dict[str, Callable[..., ResolvedModel]] = {
    "vllm": resolve_vllm,
    "openai": resolve_cloud,
    "anthropic": resolve_cloud,
    "google": resolve_cloud,
}
