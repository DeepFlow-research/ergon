"""ResearchRubrics-specific schemas."""

from pydantic import BaseModel, Field


class RubricCriterion(BaseModel):
    """A single criterion from ResearchRubrics dataset.

    Each task has ~25 criteria organized by axis type (Implicit Criteria,
    Explicit Criteria, Synthesis of Information, etc.). Criteria weights
    can be positive or negative.
    """

    criterion: str = Field(description="The criterion text to evaluate")
    axis: str = Field(
        description="Axis type: Implicit Criteria, Explicit Criteria, "
        "Synthesis of Information, Communication Quality, "
        "Instruction Following, References & Citation Quality"
    )
    weight: float = Field(description="Criterion weight (can be negative)")


class ResearchRubricsTask(BaseModel):
    """A ResearchRubrics task parsed from HuggingFace dataset.

    The ablated dataset contains both the original prompts and ablated
    versions designed to require mid-task stakeholder queries.
    """

    sample_id: str = Field(description="Unique identifier from HuggingFace dataset")
    domain: str = Field(
        description="Domain category: AI & ML, Historical Analysis, "
        "Business Planning & Research, Technical Documentation, etc."
    )
    ablated_prompt: str = Field(description="Ablated prompt (what worker sees)")
    rubrics: list[RubricCriterion] = Field(description="List of evaluation criteria")
    # Metadata for analysis
    removed_elements: list[str] | None = Field(
        default=None, description="Elements removed during ablation"
    )
    ablation_type: str | None = Field(default=None, description="Type of ablation applied")
