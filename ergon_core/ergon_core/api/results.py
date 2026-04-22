"""Public result types returned by workers, criteria, and evaluators."""

from typing import Any

from pydantic import BaseModel, Field


class WorkerOutput(BaseModel):
    """Final output of a worker execution.

    The worker's ``execute()`` async generator yields ``GenerationTurn``
    objects (persisted individually to PG). After the generator exhausts,
    ``Worker.get_output()`` returns this model with the execution summary.
    """

    model_config = {"frozen": True}

    output: str
    success: bool = True
    artifacts: dict[str, Any] = Field(  # slopcop: ignore[no-typing-any]
        default_factory=dict,
        description=(
            "DEPRECATED. This field is NOT carried across the durable "
            "worker→evaluator boundary (dropped at "
            "inngest/worker_execute.py). Do not use for files or data "
            "the criterion needs to read. Files → write to "
            "/workspace/final_output/ (auto-published as RunResources by "
            "SandboxResourcePublisher.sync). Computed artifacts → have "
            "the criterion run commands in the sandbox via "
            "CriterionRuntime.run_command. "
            "Slated for removal once no in-tree worker writes to it."
        ),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]


class CriterionResult(BaseModel):
    """Result of a single Criterion.evaluate() invocation."""

    model_config = {"frozen": True}

    name: str
    score: float
    passed: bool
    weight: float = 1.0
    feedback: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]


class TaskEvaluationResult(BaseModel):
    """Aggregated evaluation result for one task across all criteria."""

    model_config = {"frozen": True}

    task_slug: str
    score: float
    passed: bool
    evaluator_name: str
    criterion_results: list[CriterionResult] = Field(default_factory=list)
    feedback: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
