"""Step output models for task inngest functions.

These are service contracts for step.run return types - they define
the shape of data passed between steps within a single Inngest function.

Distinct from:
- Domain models (db/models.py) - persistent entities
- Event contracts (events.py) - inter-function communication
"""

from uuid import UUID

from pydantic import BaseModel

from h_arcane.core._internal.db.models import Experiment, Resource, Run


class DependencyCreationResult(BaseModel):
    """Result of create-dependencies step."""

    dependency_count: int


class EvaluatorCreationResult(BaseModel):
    """Result of create-evaluators step."""

    evaluator_count: int


class ReadyTaskIdsResult(BaseModel):
    """Result of steps that identify ready tasks."""

    ready_task_ids: list[UUID]


class LoadContextResult(BaseModel):
    """Result of load-context step in task_execute."""

    run: Run
    experiment: Experiment


class PrepareExecutionResult(BaseModel):
    """Result of prepare-execution step."""

    agent_config_id: UUID | None
    worker_data: dict  # This is task_data["assigned_to"] - shape varies by worker type
    input_resources: list[Resource]


class PersistResult(BaseModel):
    """Result of persist-results step."""

    actions_count: int
    outputs_count: int


class WorkflowStatusResult(BaseModel):
    """Result of check-workflow-status step."""

    complete: bool
    failed: bool


class ScoreAggregationResult(BaseModel):
    """Result of aggregate-scores step."""

    final_score: float | None
    normalized_score: float | None
    evaluators_count: int = 0
