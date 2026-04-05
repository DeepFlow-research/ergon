"""Explicit registries: slug -> class.

No decorators, no scanning. Adding a built-in = one import + one dict entry.
Keeps registration discoverable and prevents action-at-a-distance.
"""

from __future__ import annotations

from h_arcane.api import Benchmark, Evaluator, Worker
from h_arcane.core.providers.sandbox.manager import BaseSandboxManager, DefaultSandboxManager

from arcane_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark
from arcane_builtins.benchmarks.gdpeval.rubric import StagedRubric
from arcane_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from arcane_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from arcane_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from arcane_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from arcane_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from arcane_builtins.benchmarks.smoke_test.benchmark import SmokeTestBenchmark
from arcane_builtins.benchmarks.smoke_test.rubric import SmokeTestRubric
from arcane_builtins.evaluators.rubrics.stub_rubric import StubRubric
from arcane_builtins.workers.baselines.react_worker import ReActWorker
from arcane_builtins.workers.baselines.smoke_test_worker import SmokeTestWorker
from arcane_builtins.workers.baselines.stub_worker import StubWorker


BENCHMARKS: dict[str, type[Benchmark]] = {
    "smoke-test": SmokeTestBenchmark,
    "gdpeval": GDPEvalBenchmark,
    "researchrubrics": ResearchRubricsBenchmark,
    "minif2f": MiniF2FBenchmark,
}

WORKERS: dict[str, type[Worker]] = {
    "stub-worker": StubWorker,
    "smoke-test-worker": SmokeTestWorker,
    "react-v1": ReActWorker,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "stub-rubric": StubRubric,
    "smoke-test-rubric": SmokeTestRubric,
    "staged-rubric": StagedRubric,
    "research-rubric": ResearchRubricsRubric,
    "minif2f-rubric": MiniF2FRubric,
}

SANDBOX_MANAGERS: dict[str, type[BaseSandboxManager]] = {
    "gdpeval": GDPEvalSandboxManager,
}
