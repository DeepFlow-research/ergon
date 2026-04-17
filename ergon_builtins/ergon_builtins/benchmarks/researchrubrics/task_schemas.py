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
    """Payload for the **ablated** ResearchRubrics dataset.

    The ablated variant is a derivative of the vanilla ScaleAI dataset in
    which the original ``prompt`` has been edited (``ablated_prompt``)
    and the removed content is recorded under ``removed_elements`` /
    ``ablation_type``.  This shape is produced by
    :class:`ResearchRubricsBenchmark`.
    """

    sample_id: str = Field(description="Unique identifier from HuggingFace dataset")
    domain: str = Field(
        description=(
            "Domain category: AI & ML, Historical Analysis, "
            "Business Planning & Research, Technical Documentation, etc."
        ),
    )
    ablated_prompt: str = Field(description="Ablated prompt (what worker sees)")
    rubrics: list[RubricCriterion] = Field(description="List of evaluation criteria")
    removed_elements: list[str] | None = Field(
        default=None, description="Elements removed during ablation"
    )
    ablation_type: str | None = Field(default=None, description="Type of ablation applied")


class VanillaResearchRubricsTaskPayload(BaseModel):
    """Payload for the **vanilla** ``ScaleAI/researchrubrics`` dataset.

    The vanilla variant has a different HF schema than the ablated one:
    it carries the unedited ``prompt`` plus difficulty-classification
    metadata (``conceptual_breadth``, ``logical_nesting``, ``exploration``)
    and does **not** have ``ablated_prompt`` / ``removed_elements`` /
    ``ablation_type``.  Produced by
    :class:`ResearchRubricsVanillaBenchmark`.
    """

    sample_id: str = Field(description="Unique identifier from HuggingFace dataset")
    domain: str = Field(
        description=(
            "Domain category: AI & ML, Historical Analysis, "
            "Business Planning & Research, Technical Documentation, etc."
        ),
    )
    prompt: str = Field(description="Full (un-ablated) prompt from the vanilla dataset")
    rubrics: list[RubricCriterion] = Field(description="List of evaluation criteria")
    conceptual_breadth: str | None = Field(
        default=None, description="Difficulty axis: Simple / Intermediate / Complex"
    )
    logical_nesting: str | None = Field(
        default=None, description="Difficulty axis: Simple / Intermediate / Complex"
    )
    exploration: str | None = Field(
        default=None, description="Difficulty axis: Low / Medium / High"
    )
