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
)
from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel
from tests.fixtures.smoke_components.sandbox import SmokePublicSandbox


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


class GDPEvalTaskPayload(BaseModel):
    task_id: str
    workflow_type: str
    reference_files: list[str]


class _SingleTaskSmokeBenchmark(Benchmark):
    """Base class for smoke benchmarks that expose one deterministic task.

    PR 10c: every subclass now overrides ``build_instances`` to return
    a concrete ``Task[...]`` with inline ``evaluators``.  The base
    method previously returned a ``object-bound Task``-shaped payload; with all
    four benchmark subclasses (MiniF2F, SWE-Bench, ResearchRubrics,
    GDPEval) owning their builds, the default is gone and the import
    of ``object-bound Task`` no longer fans out from this module.
    """

    onboarding_deps: ClassVar[BenchmarkRequirements] = BenchmarkRequirements(e2b=True)
    task_slug: ClassVar[str]
    task_description: ClassVar[str]
    task_payload: ClassVar[JsonObject] = {}
    task_payload_model = EmptyTaskPayload

    def evaluator_requirements(self) -> Sequence[str]:
        return ("default", "post-root")


class ResearchRubricsSmokeTask(Task[ResearchRubricsTaskPayload]):
    """Concrete Task subclass so ``Task.from_definition`` can resolve the
    ``_type`` discriminator as a plain module attribute.

    Mirrors the named-subclass pattern from PR 6 minif2f / PR 10a swebench.
    Avoids the parameterized-generic ``Task[X]`` discriminator that
    ``import_component`` cannot resolve.
    """


class ResearchRubricsSmokeBenchmark(_SingleTaskSmokeBenchmark):
    """ResearchRubrics smoke benchmark (PR 10b: object-bound Task).

    Overrides ``build_instances`` to return a concrete
    ``ResearchRubricsSmokeTask`` with inline ``evaluators``, so the smoke
    fixture exercises the v2 object-bound path that the production
    ResearchRubrics benchmark now uses. ``sandbox`` uses the test-owned
    public wrapper over ``SmokeSandboxManager`` so eval-side
    ``Task.from_definition(..., sandbox_id=...)`` can attach a live
    runtime without reaching E2B.
    """

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

    def build_instances(self) -> Mapping[str, Sequence[Task[ResearchRubricsTaskPayload]]]:
        # Import smoke rubrics lazily so the production import graph of
        # `tests.fixtures.smoke_components.benchmarks` (used by anything that
        # references the smoke payload model) doesn't fan out into the full
        # rubric/criterion stack at module load.
        # reason: circular import — `criteria.smoke_rubrics` transitively
        # imports `tests.fixtures.smoke_components.smoke_base.criterion_base`,
        # which imports back into the smoke-components package while it is
        # still loading `benchmarks.py` during `register_smoke_fixtures`.
        from tests.fixtures.smoke_components.criteria.smoke_rubrics import (
            ResearchRubricsSmokeRubric,
        )
        from tests.fixtures.smoke_components.criteria.timing import (
            SmokePostRootTimingRubric,
        )

        payload = ResearchRubricsTaskPayload.model_validate(self.task_payload)
        task = ResearchRubricsSmokeTask(
            task_slug=self.task_slug,
            instance_key="default",
            description=self.task_description,
            evaluator_binding_keys=("default", "post-root"),
            task_payload=payload,
            sandbox=SmokePublicSandbox(),
            evaluators=(
                ResearchRubricsSmokeRubric(name="default"),
                SmokePostRootTimingRubric(name="post-root"),
            ),
        )
        return {"default": [task]}


class MiniF2FSmokeTask(Task[MiniF2FTaskPayload]):
    """Concrete Task subclass so ``Task.from_definition`` can resolve the
    ``_type`` discriminator via a plain module attribute.

    Mirrors the named-subclass pattern from PR 6 minif2f / PR 10a swebench /
    PR 10b researchrubrics.  Avoids the parameterized-generic ``Task[X]``
    discriminator that ``import_component`` cannot resolve.
    """


class MiniF2FSmokeBenchmark(_SingleTaskSmokeBenchmark):
    """MiniF2F smoke benchmark (PR 10c: object-bound Task).

    Overrides ``build_instances`` to return a concrete ``MiniF2FSmokeTask``
    with inline ``evaluators``, so the smoke fixture exercises the v2
    object-bound path that the production MiniF2F benchmark now uses.
    ``sandbox`` uses the test-owned public wrapper over
    ``SmokeSandboxManager`` so eval-side
    ``Task.from_definition(..., sandbox_id=...)`` can attach a live
    runtime without reaching E2B.
    """

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

    def build_instances(self) -> Mapping[str, Sequence[Task[MiniF2FTaskPayload]]]:
        # See ResearchRubricsSmokeBenchmark for the lazy-import rationale.
        # reason: circular import — `criteria.smoke_rubrics` transitively
        # imports `tests.fixtures.smoke_components.smoke_base.criterion_base`,
        # which imports back into the smoke-components package while it is
        # still loading `benchmarks.py` during `register_smoke_fixtures`.
        from tests.fixtures.smoke_components.criteria.smoke_rubrics import (
            MiniF2FSmokeRubric,
        )
        from tests.fixtures.smoke_components.criteria.timing import (
            SmokePostRootTimingRubric,
        )

        payload = MiniF2FTaskPayload.model_validate(self.task_payload)
        task = MiniF2FSmokeTask(
            task_slug=self.task_slug,
            instance_key="default",
            description=self.task_description,
            evaluator_binding_keys=("default", "post-root"),
            task_payload=payload,
            sandbox=SmokePublicSandbox(),
            evaluators=(
                MiniF2FSmokeRubric(name="default"),
                SmokePostRootTimingRubric(name="post-root"),
            ),
        )
        return {"default": [task]}


class SweBenchSmokeTask(Task[SWEBenchTaskPayload]):
    """Concrete Task subclass so ``Task.from_definition`` can resolve the
    ``_type`` discriminator as a plain module attribute.

    Mirrors the named-subclass pattern from PR 6 minif2f.  Avoids the
    parameterized-generic ``Task[X]`` discriminator that
    ``import_component`` cannot resolve.
    """


class SweBenchSmokeBenchmark(_SingleTaskSmokeBenchmark):
    """SWE-Bench smoke benchmark (PR 10a: object-bound Task).

    Overrides ``build_instances`` to return a concrete ``SweBenchSmokeTask``
    with inline ``evaluators``, so the smoke fixture exercises the v2
    object-bound path that the production SWE-Bench benchmark now uses.
    ``sandbox`` uses the test-owned public wrapper over
    ``SmokeSandboxManager`` so eval-side
    ``Task.from_definition(..., sandbox_id=...)`` can attach a live
    runtime without reaching E2B.
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
        # See ResearchRubricsSmokeBenchmark for the lazy-import rationale.
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
            sandbox=SmokePublicSandbox(),
            evaluators=(
                SweBenchSmokeRubric(name="default"),
                SmokePostRootTimingRubric(name="post-root"),
            ),
        )
        return {"default": [task]}


class GDPEvalSmokeTask(Task[GDPEvalTaskPayload]):
    """Concrete Task subclass so ``Task.from_definition`` can resolve the
    ``_type`` discriminator via a plain module attribute.

    Mirrors the named-subclass pattern from PR 10a swebench / PR 10b
    researchrubrics.  Avoids the parameterized-generic ``Task[X]``
    discriminator that ``import_component`` cannot resolve.
    """


class GDPEvalSmokeBenchmark(_SingleTaskSmokeBenchmark):
    """GDPEval smoke benchmark (PR 10c: object-bound Task).

    Overrides ``build_instances`` to return a concrete ``GDPEvalSmokeTask``
    with inline ``evaluators``, so the smoke fixture exercises the v2
    object-bound path that the production GDPEval benchmark now uses.
    The GDPEval slot did not exist before PR 10c — this is the first
    smoke fixture row for the benchmark.  The post-root timing rubric is
    the only evaluator wired here; per-criterion smoke checks for
    GDPEval can land in a follow-up.
    """

    type_slug: ClassVar[str] = "gdpeval"
    task_payload_model = GDPEvalTaskPayload
    task_slug: ClassVar[str] = "gdpeval-smoke-001"
    task_description: ClassVar[str] = "Process the reference documents and write outputs."
    task_payload: ClassVar[JsonObject] = {
        "task_id": "gdpeval-smoke-001",
        "workflow_type": "document_processing",
        "reference_files": [],
    }

    def build_instances(self) -> Mapping[str, Sequence[Task[GDPEvalTaskPayload]]]:
        # See ResearchRubricsSmokeBenchmark for the lazy-import rationale.
        # reason: circular import — `criteria.timing` transitively
        # imports `tests.fixtures.smoke_components.smoke_base.criterion_base`,
        # which imports back into the smoke-components package while it is
        # still loading `benchmarks.py` during `register_smoke_fixtures`.
        from tests.fixtures.smoke_components.criteria.timing import (
            SmokePostRootTimingRubric,
        )

        payload = GDPEvalTaskPayload.model_validate(self.task_payload)
        task = GDPEvalSmokeTask(
            task_slug=self.task_slug,
            instance_key="default",
            description=self.task_description,
            evaluator_binding_keys=("post-root",),
            task_payload=payload,
            sandbox=SmokePublicSandbox(),
            evaluators=(SmokePostRootTimingRubric(name="post-root"),),
        )
        return {"default": [task]}
