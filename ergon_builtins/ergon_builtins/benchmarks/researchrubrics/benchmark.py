"""ResearchRubrics benchmark for studying adaptive stakeholder querying.

Uses deep research tasks with weighted evaluation criteria to study
whether agents know when and what to ask stakeholders.
"""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from datasets import load_dataset
from ergon_core.api import Evaluator, Sandbox, Task, Worker
from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements

from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.sandbox_manager import ResearchRubricsSandbox
from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)
from ergon_builtins.workers.research_rubrics.workflow_cli_react_worker import (
    make_researchrubrics_workflow_react_worker,
)


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

    limit: int | None = None
    worker: Worker
    sandbox: Sandbox
    evaluators: tuple[Evaluator, ...]

    def __init__(
        self,
        *,
        limit: int | None = None,
        worker: Worker | None = None,
        sandbox: Sandbox | None = None,
        evaluators: tuple[Evaluator, ...] | None = None,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            name=name or "researchrubrics",
            description=description or "ResearchRubrics deep-research benchmark",
            metadata=dict(metadata or {}),
            limit=limit,
            worker=worker or make_researchrubrics_workflow_react_worker(name="default", model=None),
            sandbox=sandbox or ResearchRubricsSandbox(),
            evaluators=evaluators or (ResearchRubricsRubric(name="default"),),
        )

    # ------------------------------------------------------------------

    def build_instances(self) -> Mapping[str, Sequence[Task[ResearchRubricsTaskPayload]]]:
        payloads = self._load_rows()
        tasks: list[Task[ResearchRubricsTaskPayload]] = []
        for payload in payloads:
            tasks.append(
                Task[ResearchRubricsTaskPayload](
                    task_slug=payload.sample_id,
                    instance_key="default",
                    description=payload.prompt,
                    worker=self.worker.model_copy(deep=True),
                    sandbox=self.sandbox.model_copy(deep=True),
                    evaluators=tuple(e.model_copy(deep=True) for e in self.evaluators),
                    task_payload=payload,
                )
            )
        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ("default",)

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
