"""ResearchRubrics-specific task data shapes."""

from pydantic import BaseModel, Field


class RubricCriterion(BaseModel):
    """A single criterion from the ResearchRubrics dataset.

    Each task has ~25 criteria organised by axis type (Implicit Criteria,
    Explicit Criteria, Synthesis of Information, etc.).
    Weights can be positive or negative.
    """

    criterion: str = Field(description="The criterion text to evaluate")
    axis: str = Field(
        description=(
            "Axis type: Implicit Criteria, Explicit Criteria, "
            "Synthesis of Information, Communication Quality, "
            "Instruction Following, References & Citation Quality"
        ),
    )
    weight: float = Field(description="Criterion weight (can be negative)")


class ResearchRubricsTaskPayload(BaseModel):
    """Structured payload carried inside ``BenchmarkTask.task_payload``."""

    sample_id: str = Field(description="Unique identifier from HuggingFace dataset")
    domain: str = Field(
        description=(
            "Domain category: AI & ML, Historical Analysis, "
            "Business Planning & Research, Technical Documentation, etc."
        ),
    )
    prompt: str = Field(description="Official ResearchRubrics task prompt")
    rubrics: list[RubricCriterion] = Field(description="List of evaluation criteria")
