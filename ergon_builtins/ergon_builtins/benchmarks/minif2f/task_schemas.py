"""MiniF2F task shapes -- v2c schema (Lean 4, HuggingFace jsonl)."""

from pydantic import BaseModel, Field


class MiniF2FProblem(BaseModel):
    """A MiniF2F-v2c problem parsed from the HuggingFace jsonl file."""

    name: str = Field(description="Problem name, e.g. 'mathd_algebra_478'")
    informal_statement: str = Field(description="Natural-language problem statement")
    formal_statement: str = Field(description="Lean 4 theorem statement ending with ':= by'")
    header: str = Field(description="Import block (e.g. 'import Mathlib\\n...')")


class MiniF2FTaskPayload(BaseModel):
    """Structured payload carried inside ``BenchmarkTask.task_payload``."""

    name: str
    informal_statement: str
    formal_statement: str
    header: str
