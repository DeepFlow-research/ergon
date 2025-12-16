"""GDPEval-specific schemas."""

from pathlib import Path
from pydantic import BaseModel
from h_arcane.evaluation.rubric import StagedRubric


class GDPEvalTask(BaseModel):
    """A GDPEval task with its rubric."""

    task_id: str
    task_description: str
    reference_files: list[Path]
    rubric: StagedRubric
    category: str
