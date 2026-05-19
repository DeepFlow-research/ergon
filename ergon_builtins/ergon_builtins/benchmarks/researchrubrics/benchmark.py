"""ResearchRubrics benchmark for studying adaptive stakeholder querying.

Uses deep research tasks with weighted evaluation criteria to study
whether agents know when and what to ask stakeholders.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar

from datasets import load_dataset
from ergon_core.api import Benchmark, BenchmarkRequirements, Task
from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker

from ergon_builtins.benchmarks.researchrubrics.sandbox import ResearchE2BSandbox
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)
from ergon_builtins.benchmarks.researchrubrics.worker_factory import (
    make_research_rubric,
    make_research_worker,
)


def _default_research_sandbox() -> Sandbox:
    return ResearchE2BSandbox()


class ResearchRubricsTask(Task[ResearchRubricsTaskPayload]):
    """Concrete Task subclass for ResearchRubrics instances.

    Named so ``Task.from_definition`` can resolve the ``_type``
    discriminator as a plain module attribute.  The parameterized
    generic ``Task[ResearchRubricsTaskPayload]`` cannot be looked up that
    way — its ``__qualname__`` includes ``[...]``.
    """


class ResearchRubricsBenchmark(Benchmark):
    """Benchmark backed by the ResearchRubrics HuggingFace dataset.

    ``build_instances`` loads official ScaleAI ResearchRubrics samples and
    returns one task per sample. Each task's ``task_payload`` carries the full
    ``ResearchRubricsTaskPayload`` so the rubric and worker can reconstruct
    criteria and prompts.
    """

    type_slug: ClassVar[str] = "researchrubrics"
    dataset_name: ClassVar[str] = "ScaleAI/researchrubrics"
    task_payload_model: ClassVar[type[ResearchRubricsTaskPayload]] = ResearchRubricsTaskPayload
    onboarding_deps: ClassVar[BenchmarkRequirements] = BenchmarkRequirements(
        extras=("ergon-builtins[data]",),
        optional_keys=("EXA_API_KEY",),
    )
    required_packages: ClassVar[list[str]] = ["datasets", "huggingface_hub"]
    install_hint: ClassVar[str] = "pip install 'ergon-builtins[data]'"

    def __init__(
        self,
        *,
        limit: int | None = None,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
        worker_factory: Callable[[], Worker] = make_research_worker,
        sandbox_factory: Callable[[], Sandbox] = _default_research_sandbox,
        evaluator_factory: Callable[[], Evaluator] = make_research_rubric,
    ) -> None:
        super().__init__(
            name=name or "researchrubrics",
            description=description or "ResearchRubrics deep-research benchmark",
            metadata=metadata,
        )
        self.limit = limit
        self._worker_factory = worker_factory
        self._sandbox_factory = sandbox_factory
        self._evaluator_factory = evaluator_factory

    # ------------------------------------------------------------------

    def build_instances(self) -> Mapping[str, Sequence[Task[ResearchRubricsTaskPayload]]]:
        payloads = self._load_rows()
        tasks: list[Task[ResearchRubricsTaskPayload]] = []
        for payload in payloads:
            evaluator = self._evaluator_factory()
            if isinstance(evaluator, ResearchRubricsRubric) and not evaluator.rubric_criteria:
                evaluator = ResearchRubricsRubric(
                    name=evaluator.name,
                    metadata=evaluator.metadata,
                    rubric_criteria=tuple(payload.rubrics),
                )
            tasks.append(
                ResearchRubricsTask(
                    task_slug=payload.sample_id,
                    instance_key="default",
                    description=payload.prompt,
                    task_payload=payload,
                    worker=self._worker_factory(),
                    sandbox=self._sandbox_factory(),
                    evaluators=(evaluator,),
                )
            )
        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ()

    # ------------------------------------------------------------------

    def _load_rows(self) -> list[ResearchRubricsTaskPayload]:
        """Load and validate dataset rows from HuggingFace.

        Requires ``datasets`` and ``huggingface_hub`` to be installed.
        """
        # reason: avoids circular import at module level
        from ergon_core.core.shared.settings import settings

        token = settings.hf_api_key
        ds = load_dataset(self.dataset_name, token=token)
        train_ds = ds["train"]

        if self.limit:
            train_ds = train_ds.select(range(min(self.limit, len(train_ds))))

        return [_payload_from_row(train_ds[idx]) for idx in range(len(train_ds))]


def _payload_from_row(
    row: Mapping[str, Any],  # slopcop: ignore[no-typing-any]
) -> ResearchRubricsTaskPayload:
    """Convert one raw HuggingFace row into the benchmark payload schema."""
    return ResearchRubricsTaskPayload(
        sample_id=row["sample_id"],
        domain=str(row.get("domain", "")),
        prompt=row["prompt"],
        rubrics=[
            RubricCriterion(
                criterion=r["criterion"],
                axis=r["axis"],
                weight=r["weight"],
            )
            for r in row["rubrics"]
        ],
    )
