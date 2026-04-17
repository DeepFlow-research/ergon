"""ResearchRubrics vanilla benchmark (``ScaleAI/researchrubrics``).

Standalone sibling of :class:`ResearchRubricsBenchmark`.  The **vanilla**
and **ablated** variants are two different HuggingFace datasets with
different column schemas:

* ``ScaleAI/researchrubrics`` (vanilla): ``prompt``, ``sample_id``,
  ``domain``, ``conceptual_breadth``, ``logical_nesting``,
  ``exploration``, ``rubrics``.
* ``<user>/researchrubrics-ablated``: ``ablated_prompt``, ``sample_id``,
  ``domain``, ``rubrics``, ``removed_elements``, ``ablation_type``.

Sharing a single ``build_instances`` between the two produced a
``KeyError: 'ablated_prompt'`` on the vanilla dataset, so this class
implements its own loader and its own payload shape
(:class:`VanillaResearchRubricsTaskPayload`).

NOTE on toolkits: today both variants use the same
``researchrubrics-manager`` / ``researchrubrics-researcher`` workers.
The two benchmarks may grow distinct toolkits later (e.g. the ablated
variant may expose a stakeholder-query tool the vanilla one does not),
at which point this class is the place to override worker composition.
"""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.task_types import BenchmarkTask

from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    RubricCriterion,
    VanillaResearchRubricsTaskPayload,
)


class ResearchRubricsVanillaBenchmark(Benchmark):
    """Benchmark backed by the vanilla ``ScaleAI/researchrubrics`` dataset.

    Used for the paper's headline number: every task carries the full
    un-ablated prompt and the difficulty-classification metadata so
    downstream analysis can slice by breadth / nesting / exploration.
    """

    type_slug: ClassVar[str] = "researchrubrics-vanilla"
    required_packages: ClassVar[list[str]] = ["datasets"]
    install_hint: ClassVar[str] = "pip install 'ergon-builtins[data]'"

    # Hard-coded because this class is specifically the vanilla loader.
    # If you want a different HF source, subclass ``ResearchRubricsBenchmark``
    # (ablated shape) or add a new sibling like this one.
    DATASET_NAME: ClassVar[str] = "ScaleAI/researchrubrics"

    def __init__(
        self,
        *,
        limit: int | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            name="researchrubrics-vanilla",
            description=(
                "ScaleAI's ResearchRubrics deep-research benchmark (paper headline config)."
            ),
            metadata=metadata,
        )
        self.limit = limit

    # ------------------------------------------------------------------

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask]]:
        rows = self._load_rows()
        tasks: list[BenchmarkTask] = []
        for row in rows:
            payload = VanillaResearchRubricsTaskPayload(
                sample_id=row["sample_id"],
                domain=row.get("domain", ""),
                prompt=row["prompt"],
                rubrics=[
                    RubricCriterion(
                        criterion=r["criterion"],
                        axis=r["axis"],
                        weight=r["weight"],
                    )
                    for r in row["rubrics"]
                ],
                conceptual_breadth=row.get("conceptual_breadth"),
                logical_nesting=row.get("logical_nesting"),
                exploration=row.get("exploration"),
            )
            tasks.append(
                BenchmarkTask(
                    task_key=row["sample_id"],
                    instance_key="default",
                    description=row["prompt"],
                    evaluator_binding_keys=("default",),
                    task_payload=payload.model_dump(),
                )
            )
        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ("default",)

    # ------------------------------------------------------------------

    def _load_rows(self) -> list[dict[str, Any]]:  # slopcop: ignore[no-typing-any]
        """Load vanilla dataset rows from HuggingFace.

        Requires ``datasets`` to be installed. Unlike the ablated loader
        this does **not** call ``HfApi().whoami()`` — the vanilla dataset
        is public and owned by ``ScaleAI``, so no auth is strictly
        required.
        """
        # Deferred: optional dependency
        from datasets import load_dataset

        ds = load_dataset(self.DATASET_NAME)
        train_ds = ds["train"]

        if self.limit:
            train_ds = train_ds.select(range(min(self.limit, len(train_ds))))

        return [train_ds[idx] for idx in range(len(train_ds))]
