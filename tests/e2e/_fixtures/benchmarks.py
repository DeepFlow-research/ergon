"""Test-owned benchmarks for canonical E2E smoke runs.

The smoke matrix validates Ergon runtime topology, sandbox resource
publication, evaluation, and dashboard rendering. It should not depend on
network access or private Hugging Face credentials to materialize the root
task, so these fixtures replace the production benchmark loaders only when
``tests.e2e._fixtures`` is imported by the test harness.
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.benchmark_deps import BenchmarkDeps
from ergon_core.api.task_types import BenchmarkTask


class _SingleTaskSmokeBenchmark(Benchmark):
    """Base class for smoke benchmarks that expose one deterministic task."""

    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(e2b=True)
    task_slug: ClassVar[str]
    task_description: ClassVar[str]
    task_payload: ClassVar[dict[str, object]] = {}

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask]]:
        task = BenchmarkTask(
            task_slug=self.task_slug,
            instance_key="default",
            description=self.task_description,
            evaluator_binding_keys=("default",),
            task_payload=dict(self.task_payload),
        )
        return {"default": [task]}

    def evaluator_requirements(self) -> Sequence[str]:
        return ("default",)


class ResearchRubricsSmokeBenchmark(_SingleTaskSmokeBenchmark):
    type_slug: ClassVar[str] = "researchrubrics"
    task_slug: ClassVar[str] = "smoke-001"
    task_description: ClassVar[str] = "Write a short smoke-test research report."
    task_payload: ClassVar[dict[str, object]] = {
        "sample_id": "smoke-001",
        "domain": "smoke",
        "ablated_prompt": "Write a short smoke-test research report.",
        "rubrics": [
            {
                "criterion": "Report contains the expected smoke-test marker.",
                "axis": "correctness",
                "weight": 1.0,
            },
        ],
    }


class MiniF2FSmokeBenchmark(_SingleTaskSmokeBenchmark):
    type_slug: ClassVar[str] = "minif2f"
    task_slug: ClassVar[str] = "mathd_algebra_478"
    task_description: ClassVar[str] = "Prove the smoke_trivial theorem in Lean."
    task_payload: ClassVar[dict[str, object]] = {
        "name": "mathd_algebra_478",
        "informal_statement": "Smoke theorem used by the canonical E2E fixture.",
        "formal_statement": "theorem smoke_trivial : True := by trivial",
        "header": "",
    }


class SweBenchSmokeBenchmark(_SingleTaskSmokeBenchmark):
    type_slug: ClassVar[str] = "swebench-verified"
    task_slug: ClassVar[str] = "astropy__astropy-12907"
    task_description: ClassVar[str] = "Create the simple Python add() patch used by smoke tests."
    task_payload: ClassVar[dict[str, object]] = {
        "instance_id": "astropy__astropy-12907",
        "repo": "smoke/repo",
        "base_commit": "smoke",
        "problem_statement": "Create a Python function named add.",
        "test_patch": "",
    }
