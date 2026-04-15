"""ResearchRubrics vanilla benchmark (ScaleAI's official dataset).

Used for the paper's headline number.  Inherits all logic from the base
``ResearchRubricsBenchmark`` and overrides only the dataset name.
"""

from collections.abc import Mapping
from typing import Any, ClassVar

from ergon_builtins.benchmarks.researchrubrics.benchmark import (
    ResearchRubricsBenchmark,
)


class ResearchRubricsVanillaBenchmark(ResearchRubricsBenchmark):
    """ScaleAI's official ResearchRubrics dataset (un-ablated).

    Used for the paper's headline number.
    """

    type_slug: ClassVar[str] = "researchrubrics-vanilla"

    def __init__(
        self,
        *,
        limit: int | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            dataset_name="ScaleAI/researchrubrics",
            limit=limit,
            name="researchrubrics-vanilla",
            description=(
                "ScaleAI's ResearchRubrics deep-research benchmark (paper headline config)."
            ),
            metadata=metadata,
        )
