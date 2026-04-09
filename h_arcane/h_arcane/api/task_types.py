"""Public benchmark-owned task type."""

from typing import Any

from pydantic import BaseModel, Field


class BenchmarkTask(BaseModel):
    """Unit of work passed to Worker.execute() and referenced in EvaluationContext.

    Benchmark subclasses may extend this with typed fields for benchmark-specific
    data rather than relying on task_payload alone.
    """

    model_config = {"frozen": True}

    task_key: str
    instance_key: str
    description: str
    parent_task_key: str | None = None
    dependency_task_keys: tuple[str, ...] = ()
    evaluator_binding_keys: tuple[str, ...] = ()
    task_payload: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
