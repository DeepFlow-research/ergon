from ergon_core.api.criterion import Criterion
from pydantic import BaseModel, ConfigDict


class CriterionSpec(BaseModel):
    """Declarative description of one criterion to execute."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    criterion: Criterion
    criterion_idx: int = 0
    max_score: float = 1.0
    stage_idx: int = 0
    stage_name: str = "default"
    aggregation_weight: float = 1.0
