"""Test-owned environments for canonical E2E smoke runs.

The smoke matrix validates Ergon runtime topology, sandbox resource
publication, evaluation, and dashboard rendering. It should not depend on
network access or private Hugging Face credentials to materialize the root
task, so these fixtures replace the production environment loaders only when
``tests.fixtures.smoke_components`` is imported by the test harness.
"""

from collections.abc import Iterator, Sequence
from typing import ClassVar, Literal

from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandbox
from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
from ergon_builtins.benchmarks.researchrubrics.sandbox import ResearchE2BSandbox
from ergon_builtins.benchmarks.swebench_verified.sandbox import SWEBenchSandbox
from ergon_core.api import Environment, Sample
from ergon_core.api.task import Task
from ergon_core.api.worker import Worker
from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel
from tests.fixtures.smoke_components.workers.minif2f_smoke import (
    MiniF2FFailingLeafWorker,
    MiniF2FRecursiveSmokeWorker,
    MiniF2FSadPathSmokeWorker,
    MiniF2FSmokeLeafWorker,
    MiniF2FSmokeWorker,
)
from tests.fixtures.smoke_components.workers.researchrubrics_smoke import (
    ResearchRubricsFailingLeafWorker,
    ResearchRubricsRecursiveSmokeWorker,
    ResearchRubricsSadPathSmokeWorker,
    ResearchRubricsSmokeLeafWorker,
    ResearchRubricsSmokeWorker,
)
from tests.fixtures.smoke_components.workers.swebench_smoke import (
    SweBenchFailingLeafWorker,
    SweBenchRecursiveSmokeWorker,
    SweBenchSadPathSmokeWorker,
    SweBenchSmokeLeafWorker,
    SweBenchSmokeWorker,
)


class GDPEvalSmokeWorker(SweBenchSmokeWorker):
    """GDPEval smoke root using the generic smoke worker topology."""

    type_slug: ClassVar[str] = "gdpeval-smoke-worker"


_SMOKE_WORKERS: dict[str, type[Worker]] = {
    cls.type_slug: cls
    for cls in (
        ResearchRubricsSmokeWorker,
        ResearchRubricsSmokeLeafWorker,
        ResearchRubricsRecursiveSmokeWorker,
        ResearchRubricsSadPathSmokeWorker,
        ResearchRubricsFailingLeafWorker,
        MiniF2FSmokeWorker,
        MiniF2FSmokeLeafWorker,
        MiniF2FRecursiveSmokeWorker,
        MiniF2FSadPathSmokeWorker,
        MiniF2FFailingLeafWorker,
        SweBenchSmokeWorker,
        SweBenchSmokeLeafWorker,
        SweBenchRecursiveSmokeWorker,
        SweBenchSadPathSmokeWorker,
        SweBenchFailingLeafWorker,
        GDPEvalSmokeWorker,
    )
}


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


class _SingleTaskSmokeEnvironment(Environment):
    """Base class for smoke environments that expose one deterministic sample."""

    name: str
    source_mode: Literal["materialized"] = "materialized"
    worker_slug: str | None = None
    model: str = "openai:gpt-4o"

    environment_slug: ClassVar[str]
    task_slug: ClassVar[str]
    task_description: ClassVar[str]
    task_payload: ClassVar[JsonObject] = {}
    default_worker_slug: ClassVar[str]

    def __init__(
        self,
        *,
        worker_slug: str | None = None,
        model: str = "openai:gpt-4o",
        **kwargs,
    ) -> None:
        kwargs.setdefault("name", self.environment_slug)
        super().__init__(**kwargs)
        self.worker_slug = worker_slug or self.default_worker_slug
        self.model = model

    def _make_worker(self) -> Worker:
        slug = self.worker_slug or self.default_worker_slug
        try:
            worker_cls = _SMOKE_WORKERS[slug]
        except KeyError:
            known = ", ".join(sorted(_SMOKE_WORKERS))
            raise ValueError(f"Unknown smoke worker slug {self.worker_slug!r}; known: {known}")
        return worker_cls(name=slug, model=self.model)

    def iter_samples(self) -> Iterator[Sample]:
        yield from self.all_samples()

    def all_samples(self) -> Sequence[Sample]:
        return [
            Sample.from_tasks(
                name=f"{self.name}:default",
                sample_key="default",
                environment_name=self.name,
                tasks=self._tasks(),
                sample_ref={"instance_key": "default"},
                metadata=dict(self.metadata),
            )
        ]

    def _tasks(self) -> Sequence[Task]:
        raise NotImplementedError


class ResearchRubricsSmokeTask(Task[ResearchRubricsTaskPayload]):
    """Concrete Task subclass so ``Task.from_definition`` can resolve the
    ``_type`` discriminator as a plain module attribute.

    Mirrors the named-subclass pattern from PR 6 minif2f / PR 10a swebench.
    Avoids the parameterized-generic ``Task[X]`` discriminator that
    ``import_component`` cannot resolve.
    """


class ResearchRubricsSmokeEnvironment(_SingleTaskSmokeEnvironment):
    """ResearchRubrics smoke environment.

    Returns a concrete ``ResearchRubricsSmokeTask`` with inline ``evaluators``, so the smoke
    fixture exercises the v2 object-bound path that the production
    ResearchRubrics environment now uses. ``sandbox`` uses the real
    benchmark sandbox class so the smoke fixture mirrors production
    posture while the test harness controls the runtime manager.
    """

    environment_slug: ClassVar[str] = "researchrubrics"
    default_worker_slug: ClassVar[str] = "researchrubrics-smoke-worker"
    task_slug: ClassVar[str] = "smoke-001"
    task_description: ClassVar[str] = (
        "Review the supplied research notes and produce a concise evidence-backed report."
    )
    task_payload: ClassVar[JsonObject] = {
        "sample_id": "smoke-001",
        "domain": "smoke",
        "prompt": "Review the supplied research notes and produce a concise evidence-backed report.",
        "rubrics": [
            {
                "criterion": "Report contains the expected smoke-test marker.",
                "axis": "correctness",
                "weight": 1.0,
            },
        ],
    }

    def _tasks(self) -> Sequence[Task[ResearchRubricsTaskPayload]]:
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
            task_payload=payload,
            worker=self._make_worker(),
            sandbox=ResearchE2BSandbox(),
            evaluators=(
                ResearchRubricsSmokeRubric(name="default"),
                SmokePostRootTimingRubric(name="post-root"),
            ),
        )
        return [task]


class MiniF2FSmokeTask(Task[MiniF2FTaskPayload]):
    """Concrete Task subclass so ``Task.from_definition`` can resolve the
    ``_type`` discriminator via a plain module attribute.

    Mirrors the named-subclass pattern from PR 6 minif2f / PR 10a swebench /
    PR 10b researchrubrics.  Avoids the parameterized-generic ``Task[X]``
    discriminator that ``import_component`` cannot resolve.
    """


class MiniF2FSmokeEnvironment(_SingleTaskSmokeEnvironment):
    """MiniF2F smoke environment.

    Returns a concrete ``MiniF2FSmokeTask`` with inline ``evaluators``, so the smoke fixture exercises the v2
    object-bound path that the production MiniF2F environment now uses.
    ``sandbox`` uses the real benchmark sandbox class so the smoke fixture
    mirrors production posture while the test harness controls the runtime
    manager.
    """

    environment_slug: ClassVar[str] = "minif2f"
    default_worker_slug: ClassVar[str] = "minif2f-smoke-worker"
    task_slug: ClassVar[str] = "mathd_algebra_478"
    task_description: ClassVar[str] = "Verify the supplied Lean theorem and record proof evidence."
    task_payload: ClassVar[JsonObject] = {
        "name": "mathd_algebra_478",
        "informal_statement": "Smoke theorem used by the canonical E2E fixture.",
        "formal_statement": "theorem smoke_trivial : True := by trivial",
        "header": "",
    }

    def _tasks(self) -> Sequence[Task[MiniF2FTaskPayload]]:
        # See ResearchRubricsSmokeEnvironment for the lazy-import rationale.
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
            task_payload=payload,
            worker=self._make_worker(),
            sandbox=LeanSandbox(),
            evaluators=(
                MiniF2FSmokeRubric(name="default"),
                SmokePostRootTimingRubric(name="post-root"),
            ),
        )
        return [task]


class SweBenchSmokeTask(Task[SWEBenchTaskPayload]):
    """Concrete Task subclass so ``Task.from_definition`` can resolve the
    ``_type`` discriminator as a plain module attribute.

    Mirrors the named-subclass pattern from PR 6 minif2f.  Avoids the
    parameterized-generic ``Task[X]`` discriminator that
    ``import_component`` cannot resolve.
    """


class SweBenchSmokeEnvironment(_SingleTaskSmokeEnvironment):
    """SWE-Bench smoke environment.

    Returns a concrete ``SweBenchSmokeTask`` with inline ``evaluators``, so the smoke fixture exercises the v2
    object-bound path that the production SWE-Bench environment now uses.
    ``sandbox`` uses the real benchmark sandbox class so the smoke fixture
    mirrors production posture while the test harness controls the runtime
    manager.
    """

    environment_slug: ClassVar[str] = "swebench-verified"
    default_worker_slug: ClassVar[str] = "swebench-smoke-worker"
    task_slug: ClassVar[str] = "astropy__astropy-12907"
    task_description: ClassVar[str] = (
        "Inspect the Python issue and produce a minimal source patch with evidence."
    )
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

    def _tasks(self) -> Sequence[Task[SWEBenchTaskPayload]]:
        # See ResearchRubricsSmokeEnvironment for the lazy-import rationale.
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
            task_payload=payload,
            worker=self._make_worker(),
            sandbox=SWEBenchSandbox(),
            evaluators=(
                SweBenchSmokeRubric(name="default"),
                SmokePostRootTimingRubric(name="post-root"),
            ),
        )
        return [task]


class GDPEvalSmokeTask(Task[GDPEvalTaskPayload]):
    """Concrete Task subclass so ``Task.from_definition`` can resolve the
    ``_type`` discriminator via a plain module attribute.

    Mirrors the named-subclass pattern from PR 10a swebench / PR 10b
    researchrubrics.  Avoids the parameterized-generic ``Task[X]``
    discriminator that ``import_component`` cannot resolve.
    """


class GDPEvalSmokeEnvironment(_SingleTaskSmokeEnvironment):
    """GDPEval smoke environment.

    Returns a concrete ``GDPEvalSmokeTask`` with inline ``evaluators``, so the smoke fixture exercises the v2
    object-bound path that the production GDPEval environment now uses.
    The GDPEval slot did not exist before PR 10c — this is the first
    smoke fixture row for the environment.  The post-root timing rubric is
    the only evaluator wired here; per-criterion smoke checks for
    GDPEval can land in a follow-up.
    """

    environment_slug: ClassVar[str] = "gdpeval"
    default_worker_slug: ClassVar[str] = "gdpeval-smoke-worker"
    task_slug: ClassVar[str] = "gdpeval-smoke-001"
    task_description: ClassVar[str] = (
        "Process the reference documents and write a structured output bundle."
    )
    task_payload: ClassVar[JsonObject] = {
        "task_id": "gdpeval-smoke-001",
        "workflow_type": "document_processing",
        "reference_files": [],
    }

    def _tasks(self) -> Sequence[Task[GDPEvalTaskPayload]]:
        # See ResearchRubricsSmokeEnvironment for the lazy-import rationale.
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
            task_payload=payload,
            worker=self._make_worker(),
            sandbox=GDPEvalSandbox(),
            evaluators=(SmokePostRootTimingRubric(name="post-root"),),
        )
        return [task]
