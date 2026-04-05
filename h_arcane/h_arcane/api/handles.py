"""Public lifecycle handle types returned by persist() and run()."""

from datetime import datetime
from typing import Any
from uuid import UUID

from h_arcane.core.utils import utcnow
from pydantic import BaseModel, Field


class PersistedExperimentDefinition(BaseModel):
    """Rich handle returned by Experiment.persist().

    Carries enough information for inspection, logging, and downstream use
    without requiring a database round-trip.
    """

    model_config = {"frozen": True}

    definition_id: UUID
    benchmark_type: str
    worker_bindings: dict[str, str] = Field(default_factory=dict)
    evaluator_bindings: dict[str, str] = Field(default_factory=dict)
    instance_count: int = 0
    task_count: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentRunHandle(BaseModel):
    """Rich handle returned by Experiment.run().

    Carries enough information for inspection, logging, and downstream use
    without requiring a database round-trip.
    """

    model_config = {"frozen": True}

    run_id: UUID
    definition_id: UUID
    benchmark_type: str
    status: str
    worker_bindings: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
