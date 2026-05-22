"""Public criterion score models."""

from pydantic import BaseModel


class ScoreScale(BaseModel):
    """Criterion-local score range."""

    model_config = {"frozen": True}

    min_score: float = 0.0
    max_score: float = 1.0
