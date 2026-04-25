"""ResearchRubrics benchmark for studying adaptive stakeholder querying.

Uses deep research tasks with weighted evaluation criteria to study
whether agents know when and what to ask stakeholders.
"""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from datasets import load_dataset
from huggingface_hub import HfApi

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.benchmark_deps import BenchmarkDeps
from ergon_core.api.task_types import BenchmarkTask

from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)


class ResearchRubricsBenchmark(Benchmark):
    """Benchmark backed by the ResearchRubrics HuggingFace dataset.

    ``build_instances`` loads samples from the (ablated) HuggingFace dataset
    and returns one task per sample.  Each task's ``task_payload`` carries the
    full ``ResearchRubricsTaskPayload`` so the rubric and worker can
    reconstruct criteria and prompts.
    """

    type_slug: ClassVar[str] = "researchrubrics"
    task_payload_model: ClassVar[type[ResearchRubricsTaskPayload]] = ResearchRubricsTaskPayload
    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(
        extras=("ergon-builtins[data]",),
        optional_keys=("EXA_API_KEY",),
    )
    required_packages: ClassVar[list[str]] = ["datasets", "huggingface_hub"]
    install_hint: ClassVar[str] = "pip install 'ergon-builtins[data]'"

    def __init__(
        self,
        *,
        dataset_name: str | None = None,
        limit: int | None = None,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            name=name or "researchrubrics",
            description=description or "ResearchRubrics deep-research benchmark",
            metadata=metadata,
        )
        self.dataset_name = dataset_name
        self.limit = limit

    # ------------------------------------------------------------------

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask[ResearchRubricsTaskPayload]]]:
        payloads = self._load_rows()
        tasks: list[BenchmarkTask[ResearchRubricsTaskPayload]] = []
        for payload in payloads:
            tasks.append(
                BenchmarkTask[ResearchRubricsTaskPayload](
                    task_slug=payload.sample_id,
                    instance_key="default",
                    description=payload.ablated_prompt,
                    evaluator_binding_keys=("default",),
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
        dataset_name = self.dataset_name
        # reason: avoids circular import at module level
        from ergon_core.core.settings import settings

        token = settings.hf_api_key
        if dataset_name is None:
            if token is None:
                raise RuntimeError("HF_API_KEY must be set when dataset_name is not provided")
            api = HfApi(token=token)
            user_info = api.whoami()
            dataset_name = f"{user_info['name']}/researchrubrics-ablated"

        ds = load_dataset(dataset_name, token=token)
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
        ablated_prompt=row["ablated_prompt"],
        rubrics=[
            RubricCriterion(
                criterion=r["criterion"],
                axis=r["axis"],
                weight=r["weight"],
            )
            for r in row["rubrics"]
        ],
        removed_elements=row.get("removed_elements"),
        ablation_type=row.get("ablation_type"),
    )
