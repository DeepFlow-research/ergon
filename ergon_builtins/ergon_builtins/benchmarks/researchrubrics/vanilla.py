"""ResearchRubrics vanilla benchmark alias.

Kept as a registry-compatible alias for the official ScaleAI dataset.
"""

from collections.abc import Mapping
from typing import Any, ClassVar

from ergon_builtins.benchmarks.researchrubrics.benchmark import (
    ResearchRubricsBenchmark,
)


class ResearchRubricsVanillaBenchmark(ResearchRubricsBenchmark):
    """Compatibility alias for ScaleAI's official ResearchRubrics dataset.

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
            limit=limit,
            name="researchrubrics-vanilla",
            description=(
                "ScaleAI's ResearchRubrics deep-research benchmark (paper headline config)."
            ),
            metadata=metadata,
        )
