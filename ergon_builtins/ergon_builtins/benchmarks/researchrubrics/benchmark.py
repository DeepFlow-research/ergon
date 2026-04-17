"""ResearchRubrics **ablated** benchmark for studying adaptive stakeholder querying.

Uses deep research tasks with weighted evaluation criteria to study
whether agents know when and what to ask stakeholders.

This module is the loader for the *ablated* dataset variant only -- the
vanilla ``ScaleAI/researchrubrics`` dataset has a different column
schema and lives in :mod:`ergon_builtins.benchmarks.researchrubrics.vanilla`.
"""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.task_types import BenchmarkTask

from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)


class ResearchRubricsBenchmark(Benchmark):
    """Benchmark backed by the **ablated** ResearchRubrics HuggingFace dataset.

    ``build_instances`` loads samples from the ablated HuggingFace
    dataset (expected columns: ``sample_id``, ``domain``,
    ``ablated_prompt``, ``rubrics``, ``removed_elements``,
    ``ablation_type``) and returns one task per sample. Each task's
    ``task_payload`` carries the full
    :class:`ResearchRubricsTaskPayload` so the rubric and worker can
    reconstruct criteria and prompts.

    For the un-ablated vanilla dataset see
    :class:`ResearchRubricsVanillaBenchmark`.
    """

    type_slug: ClassVar[str] = "researchrubrics"
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

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask]]:
        rows = self._load_rows()
        tasks: list[BenchmarkTask] = []
        for row in rows:
            payload = ResearchRubricsTaskPayload(
                sample_id=row["sample_id"],
                domain=row.get("domain", ""),
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
            tasks.append(
                BenchmarkTask(
                    task_key=row["sample_id"],
                    instance_key="default",
                    description=row["ablated_prompt"],
                    evaluator_binding_keys=("default",),
                    task_payload=payload.model_dump(),
                )
            )
        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ("default",)

    # ------------------------------------------------------------------

    def _load_rows(self) -> list[dict[str, Any]]:  # slopcop: ignore[no-typing-any]
        """Load dataset rows from HuggingFace.

        Requires ``datasets`` and ``huggingface_hub`` to be installed.
        """
        # Deferred: optional dependency
        from datasets import load_dataset

        # Deferred: optional dependency
        from huggingface_hub import HfApi

        dataset_name = self.dataset_name
        if dataset_name is None:
            api = HfApi()
            user_info = api.whoami()
            dataset_name = f"{user_info['name']}/researchrubrics-ablated"

        ds = load_dataset(dataset_name)
        train_ds = ds["train"]

        if self.limit:
            train_ds = train_ds.select(range(min(self.limit, len(train_ds))))

        return [train_ds[idx] for idx in range(len(train_ds))]
