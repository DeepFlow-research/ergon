"""Test-owned benchmarks for canonical E2E smoke runs.

The smoke matrix validates Ergon runtime topology, sandbox resource
publication, evaluation, and dashboard rendering. It should not depend on
network access or private Hugging Face credentials to materialize the root
task, so these fixtures replace the production benchmark loaders only when
``tests.fixtures.smoke_components`` is imported by the test harness.
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from ergon_core.api.benchmark import (
    Benchmark,
    BenchmarkRequirements,
    EmptyTaskPayload,
    Task,
    TaskSpec,
)
from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel


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

    def build_instances(self) -> Mapping[str, Sequence[TaskSpec[BaseModel]]]:
        payload = self.task_payload_model.model_validate(self.task_payload)
        task = TaskSpec[BaseModel](
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
    task_payload: ClassVar[JsonObject] = {
        "name": "mathd_algebra_478",
        "informal_statement": "Smoke theorem used by the canonical E2E fixture.",
        "formal_statement": "theorem smoke_trivial : True := by trivial",
        "header": "",
    }


class SweBenchSmokeTask(Task[SWEBenchTaskPayload]):
    """Concrete Task subclass so ``Task.from_definition`` can resolve the
    ``_type`` discriminator via ``getattr(module, "SweBenchSmokeTask")``.

    Mirrors the named-subclass pattern from PR 6 minif2f.  Avoids the
    parameterized-generic ``Task[X]`` discriminator that
    ``import_component`` cannot resolve.
    """


class SweBenchSmokeBenchmark(_SingleTaskSmokeBenchmark):
    """SWE-Bench smoke benchmark (PR 10a: object-bound Task).

    Overrides ``build_instances`` to return a concrete ``SweBenchSmokeTask``
    with inline ``evaluators``, so the smoke fixture exercises the v2
    object-bound path that the production SWE-Bench benchmark now uses.
    Note: ``worker`` and ``sandbox`` stay ``None`` because the smoke
    harness owns sandbox lifecycle via ``SmokeSandboxManager`` and resolves
    workers by registry slug — the existing v1 dispatch is what we test.
    """

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

    def build_instances(self) -> Mapping[str, Sequence[Task[SWEBenchTaskPayload]]]:
        # Import smoke rubrics lazily so the production import graph of
        # `tests.fixtures.smoke_components.benchmarks` (used by anything that
        # references the smoke payload model) doesn't fan out into the full
        # rubric/criterion stack at module load.
        # reason: circular import — `criteria.smoke_rubrics` transitively
        # imports `tests.fixtures.smoke_components.smoke_base.criterion_base`,
        # which imports back into the smoke-components package while it is
        # still loading `benchmarks.py` during `register_smoke_fixtures`.
        from tests.fixtures.smoke_components.criteria.smoke_rubrics import (
            SweBenchSmokeRubric,
        )
        from tests.fixtures.smoke_components.criteria.timing import (
            SmokePostRootTimingRubric,
        )

        payload = SWEBenchTaskPayload.model_validate(self.task_payload)
        task = SweBenchSmokeTask(
            task_slug=self.task_slug,
            instance_key="default",
            description=self.task_description,
            evaluator_binding_keys=("default", "post-root"),
            task_payload=payload,
            evaluators=(
                SweBenchSmokeRubric(name="default"),
                SmokePostRootTimingRubric(name="post-root"),
            ),
        )
        return {"default": [task]}
