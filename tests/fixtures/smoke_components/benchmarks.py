"""Test-owned benchmarks for canonical E2E smoke runs.

The smoke matrix validates Ergon runtime topology, sandbox resource
publication, evaluation, and dashboard rendering. It should not depend on
network access or private Hugging Face credentials to materialize the root
task, so these fixtures replace the production benchmark loaders only when
``tests.fixtures.smoke_components`` is imported by the test harness.
"""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from ergon_core.api import Evaluator, Sandbox, Worker
from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements, EmptyTaskPayload, Task
from ergon_core.api.registry import registry
from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel
from tests.fixtures.smoke_components.sandbox import SmokeSandboxDefinition


class ResearchRubricsTaskPayload(BaseModel):
    sample_id: str
    domain: str
    prompt: str
    rubrics: list[JsonObject]


class MiniF2FTaskPayload(BaseModel):
    name: str
    informal_statement: str
    formal_statement: str
    header: str


class SWEBenchTaskPayload(BaseModel):
    instance_id: str
    repo: str
    base_commit: str
    version: str
    problem_statement: str
    hints_text: str
    fail_to_pass: list[str]
    pass_to_pass: list[str]
    environment_setup_commit: str
    test_patch: str


class _SingleTaskSmokeBenchmark(Benchmark):
    """Base class for smoke benchmarks that expose one deterministic task."""

    onboarding_deps: ClassVar[BenchmarkRequirements] = BenchmarkRequirements(e2b=True)
    task_slug: ClassVar[str]
    task_description: ClassVar[str]
    task_payload: ClassVar[JsonObject] = {}
    task_payload_model = EmptyTaskPayload
    worker_slug: ClassVar[str]
    worker: Worker | None = None
    sandbox: Sandbox | None = None
    evaluators: tuple[Evaluator, ...] = ()

    def __init__(
        self,
        *,
        worker: Worker | None = None,
        sandbox: Sandbox | None = None,
        evaluators: tuple[Evaluator, ...] | None = None,
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            worker=worker,
            sandbox=sandbox,
            evaluators=evaluators or (),
            **kwargs,
        )

    def build_instances(self) -> Mapping[str, Sequence[Task[BaseModel]]]:
        payload = self.task_payload_model.model_validate(self.task_payload)
        worker = self.worker
        if worker is None:
            worker_cls = registry.require_worker(self.worker_slug)
            worker = worker_cls(name=self.worker_slug, model=None)
        task = Task[BaseModel](
            task_slug=self.task_slug,
            instance_key="default",
            description=self.task_description,
            worker=worker,
            sandbox=self.sandbox or SmokeSandboxDefinition(),
            evaluators=tuple(self.evaluators),
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
    worker_slug: ClassVar[str] = "researchrubrics-smoke-worker"
    task_payload: ClassVar[JsonObject] = {
        "sample_id": "smoke-001",
        "domain": "smoke",
        "prompt": "Write a short smoke-test research report.",
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
    worker_slug: ClassVar[str] = "minif2f-smoke-worker"
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
    worker_slug: ClassVar[str] = "swebench-smoke-worker"
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
