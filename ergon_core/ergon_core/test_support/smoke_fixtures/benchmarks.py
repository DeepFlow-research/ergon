"""Test-owned benchmarks for canonical E2E smoke runs.

The smoke matrix validates Ergon runtime topology, sandbox resource
publication, evaluation, and dashboard rendering. It should not depend on
network access or private Hugging Face credentials to materialize the root
task, so these fixtures replace the production benchmark loaders only when
``ergon_core.test_support.smoke_fixtures`` is imported by the test harness.
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from pydantic import BaseModel

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.benchmark_deps import BenchmarkDeps
from ergon_core.api.json_types import JsonObject
from ergon_core.api.task_types import BenchmarkTask, EmptyTaskPayload

from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FTaskPayload
from ergon_builtins.benchmarks.researchrubrics.task_schemas import ResearchRubricsTaskPayload
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchTaskPayload


class _SingleTaskSmokeBenchmark(Benchmark):
    """Base class for smoke benchmarks that expose one deterministic task."""

    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(e2b=True)
    task_slug: ClassVar[str]
    task_description: ClassVar[str]
    task_payload: ClassVar[JsonObject] = {}
    task_payload_model = EmptyTaskPayload

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask[BaseModel]]]:
        payload = self.task_payload_model.model_validate(self.task_payload)
        task = BenchmarkTask[BaseModel](
            task_slug=self.task_slug,
            instance_key="default",
            description=self.task_description,
            evaluator_binding_keys=("default", "post-root"),
            task_payload=payload,
        )
        return {"default": [task]}

    def evaluator_requirements(self) -> Sequence[str]:
        return ("default", "post-root")


class ResearchRubricsSmokeBenchmark(_SingleTaskSmokeBenchmark):
    type_slug: ClassVar[str] = "researchrubrics"
    task_payload_model = ResearchRubricsTaskPayload
    task_slug: ClassVar[str] = "smoke-001"
    task_description: ClassVar[str] = "Write a short smoke-test research report."
    task_payload: ClassVar[JsonObject] = {
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
    task_payload_model = MiniF2FTaskPayload
    task_slug: ClassVar[str] = "mathd_algebra_478"
    task_description: ClassVar[str] = "Prove the smoke_trivial theorem in Lean."
    task_payload: ClassVar[JsonObject] = {
        "name": "mathd_algebra_478",
        "informal_statement": "Smoke theorem used by the canonical E2E fixture.",
        "formal_statement": "theorem smoke_trivial : True := by trivial",
        "header": "",
    }


class SweBenchSmokeBenchmark(_SingleTaskSmokeBenchmark):
    type_slug: ClassVar[str] = "swebench-verified"
    task_payload_model = SWEBenchTaskPayload
    task_slug: ClassVar[str] = "astropy__astropy-12907"
    task_description: ClassVar[str] = "Create the simple Python add() patch used by smoke tests."
    task_payload: ClassVar[JsonObject] = {
        "instance_id": "astropy__astropy-12907",
        "repo": "smoke/repo",
        "base_commit": "smoke",
        "version": "smoke",
        "problem_statement": "Create a Python function named add.",
        "hints_text": "",
        "fail_to_pass": [],
        "pass_to_pass": [],
        "environment_setup_commit": "smoke",
        "test_patch": "",
    }
