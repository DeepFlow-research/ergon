"""Base protocols and abstractions for evaluation."""

from typing import TYPE_CHECKING, Protocol

import inngest

if TYPE_CHECKING:
    from h_arcane.core.db.models import TaskEvaluationResult
    from h_arcane.core.evaluation.schemas import TaskEvaluationContext


class BaseRubric(Protocol):
    """Protocol for benchmark rubrics.

    Each benchmark implements its own rubric as a Pydantic model
    with a discriminator field and scoring logic.
    """

    benchmark: str  # Discriminator field

    async def compute_scores(
        self,
        context: "TaskEvaluationContext",
        inngest_ctx: inngest.Context,
    ) -> "TaskEvaluationResult":
        """Compute scores for agent outputs against this rubric.

        Each benchmark implements its own scoring logic:
        - GDPEval: staged evaluation with gates
        - MiniF2F: binary proof verification
        """
        ...
