"""ResearchRubrics concrete task type and row helpers.

Uses deep research tasks with weighted evaluation criteria to study
whether agents know when and what to ask stakeholders.
"""

from collections.abc import Mapping
from typing import Any

from ergon_core.api import Task

from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)

RESEARCH_RUBRICS_DATASET = "ScaleAI/researchrubrics"


class ResearchRubricsTask(Task[ResearchRubricsTaskPayload]):
    """Concrete Task subclass for ResearchRubrics instances.

    Named so ``Task.from_definition`` can resolve the ``_type``
    discriminator as a plain module attribute.  The parameterized
    generic ``Task[ResearchRubricsTaskPayload]`` cannot be looked up that
    way — its ``__qualname__`` includes ``[...]``.
    """


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


__all__ = [
    "RESEARCH_RUBRICS_DATASET",
    "ResearchRubricsTask",
    "_payload_from_row",
]
