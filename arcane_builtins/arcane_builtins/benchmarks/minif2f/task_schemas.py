"""MiniF2F task shapes — problem_id, statement, proof_type."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class MiniF2FProblem(BaseModel):
    """A MiniF2F problem with its ground-truth proof."""

    problem_id: str = Field(description="Theorem name, e.g. 'amc12a_2008_p25'")
    problem_statement: str = Field(description="Lean theorem statement (up to :=)")
    ground_truth_proof: str = Field(description="Full ground-truth theorem block")
    split: str = Field(description="Dataset split: 'valid' or 'test'")
    proof_type: str = Field(default="lean", description="Formal system (currently only 'lean')")
    lean_file_path: Path | None = Field(
        default=None, description="Source .lean file path (if loaded from disk)"
    )


class MiniF2FTaskPayload(BaseModel):
    """Structured payload carried inside ``BenchmarkTask.task_payload``."""

    problem_id: str
    problem_statement: str
    ground_truth_proof: str
    split: str
    proof_type: str = "lean"
