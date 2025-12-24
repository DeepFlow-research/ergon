"""Task evaluation context - bundles data needed to evaluate task outputs."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from h_arcane.core.db.models import Resource
from h_arcane.benchmarks.types import AnyRubric


class TaskEvaluationContext(BaseModel):
    """Context for evaluating an entire task (all criteria).

    Bundles all data needed to evaluate task outputs against a rubric.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID
    task_input: str
    agent_reasoning: str
    agent_outputs: list[Resource]
    rubric: AnyRubric  # Discriminated union - auto-selects StagedRubric or MiniF2FRubric
