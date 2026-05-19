"""GDP-specific task and rubric data shapes."""

from pathlib import Path
from typing import Any

from ergon_core.api.criterion import ScoreScale
from pydantic import BaseModel, Field, model_validator


class GDPDatasetRef(BaseModel):
    """Pointer to the on-disk GDP evaluation dataset."""

    parquet_path: str = Field(description="Path to gdpeval.parquet")
    reference_dir: str = Field(description="Directory containing per-task reference files")
    rubric_file: str = Field(description="Path to staged rubrics JSONL file")


class GDPTaskConfig(BaseModel):
    """Configuration for a single GDP evaluation task."""

    task_id: str = Field(description="GDPEval task identifier (e.g. 'task_001')")
    workflow_type: str = Field(
        default="document_processing",
        description="Workflow category for the task",
    )
    category: str = Field(default="", description="High-level task category")
    reference_files: list[str] = Field(
        default_factory=list,
        description="Paths to reference / input files",
    )
    dataset_ref: GDPDatasetRef | None = Field(
        default=None,
        description="Optional pointer to the full dataset",
    )


class GDPTaskInstance(BaseModel):
    """A fully loaded GDP task ready for execution."""

    task_id: str
    task_description: str
    reference_files: list[Path] = Field(default_factory=list)
    category: str = ""  # slopcop: ignore[no-str-empty-default]
    rubric_data: dict[str, Any] = Field(  # slopcop: ignore[no-typing-any]
        default_factory=dict,
        description="Raw rubric JSON blob for this task",
    )


class GDPRubricCriterionData(BaseModel):
    """Raw GDPEval criterion entry from the HuggingFace rubric JSONL."""

    name: str | None = None
    description: str | None = None
    type: str | None = None
    code_template: str | None = None
    prompt_template: str | None = None
    weight: float = 1.0
    score_spec: ScoreScale = Field(default_factory=ScoreScale)

    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def _normalize_hf_max_score(cls, data: Any) -> Any:  # slopcop: ignore[no-typing-any]
        if isinstance(data, dict) and "max_score" in data and "score_spec" not in data:
            data = dict(data)
            data["score_spec"] = {"max_score": data.pop("max_score")}
        return data


class GDPRubricStageData(BaseModel):
    """Raw GDPEval staged-rubric entry from the HuggingFace rubric JSONL."""

    name: str
    description: str | None = None
    is_required: bool = True
    max_points: float = 1.0
    min_score_to_pass: float = 0.0
    on_failure_action: str = "skip_remaining"
    on_failure_score: float = 0.0
    criteria: list[GDPRubricCriterionData] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class GDPRubricData(BaseModel):
    """Raw GDPEval rubric record keyed by task_id."""

    task_id: str
    category_name: str | None = None
    max_total_score: float | None = None
    stages: list[GDPRubricStageData] = Field(default_factory=list)
    rationale: str | None = None

    model_config = {"extra": "allow"}
