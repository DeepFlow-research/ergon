"""MiniF2F-specific schemas."""

from pathlib import Path
from pydantic import BaseModel


class MiniF2FProblem(BaseModel):
    """A MiniF2F problem with its ground truth proof."""

    problem_id: str
    problem_statement: str
    ground_truth_proof: str
    split: str  # "valid" or "test"
    lean_file_path: Path | None = None
