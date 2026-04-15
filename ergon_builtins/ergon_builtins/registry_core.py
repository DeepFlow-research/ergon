"""Components with no dependencies beyond ergon-core.

All imports are eager and fully typed.  This module is always safe to import
regardless of which optional extras are installed.
"""

from collections.abc import Callable

from ergon_core.api import Benchmark, Evaluator, Worker
from ergon_core.core.providers.generation.model_resolution import ResolvedModel
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

from ergon_builtins.benchmarks.gdpeval.rubric import StagedRubric
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.delegation_smoke.benchmark import DelegationSmokeBenchmark
from ergon_builtins.benchmarks.researchrubrics.smoke import (
    ResearchRubricsSmokeTestBenchmark,
)
from ergon_builtins.benchmarks.researchrubrics.smoke_rubric import (
    ResearchRubricsSmokeRubric,
)
from ergon_builtins.benchmarks.smoke_test.benchmark import SmokeTestBenchmark
from ergon_builtins.benchmarks.smoke_test.rubric import SmokeTestRubric
from ergon_builtins.evaluators.rubrics.stub_rubric import StubRubric
from ergon_builtins.evaluators.rubrics.varied_stub_rubric import VariedStubRubric
from ergon_builtins.models.cloud_passthrough import resolve_cloud
from ergon_builtins.models.vllm_backend import resolve_vllm
from ergon_builtins.workers.baselines.manager_researcher_worker import ManagerResearcherWorker
from ergon_builtins.workers.baselines.react_worker import ReActWorker
from ergon_builtins.workers.baselines.smoke_test_worker import SmokeTestWorker
from ergon_builtins.workers.baselines.stub_worker import StubWorker
from ergon_builtins.workers.baselines.training_stub_worker import TrainingStubWorker
from ergon_builtins.workers.research_rubrics.stub_worker import (
    StubResearchRubricsWorker,
)

WORKERS: dict[str, type[Worker]] = {
    "stub-worker": StubWorker,
    "training-stub": TrainingStubWorker,
    "smoke-test-worker": SmokeTestWorker,
    "react-v1": ReActWorker,
    "manager-researcher": ManagerResearcherWorker,
    "researcher": StubWorker,
    "researchrubrics-stub": StubResearchRubricsWorker,
}

BENCHMARKS: dict[str, type[Benchmark]] = {
    "smoke-test": SmokeTestBenchmark,
    "minif2f": MiniF2FBenchmark,
    "delegation-smoke": DelegationSmokeBenchmark,
    "researchrubrics-smoke": ResearchRubricsSmokeTestBenchmark,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "stub-rubric": StubRubric,
    "varied-stub-rubric": VariedStubRubric,
    "smoke-test-rubric": SmokeTestRubric,
    "staged-rubric": StagedRubric,
    "minif2f-rubric": MiniF2FRubric,
    "researchrubrics-smoke-rubric": ResearchRubricsSmokeRubric,
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
