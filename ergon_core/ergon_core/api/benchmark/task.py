"""Public benchmark-owned task type."""

from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field


class EmptyTaskPayload(BaseModel):
    """Default payload for benchmarks that do not need task-specific data."""

    model_config = {"extra": "forbid", "frozen": True}


PayloadT = TypeVar(
    "PayloadT",
    bound=BaseModel,
    default=EmptyTaskPayload,
    covariant=True,
)


class TaskSpec(BaseModel, Generic[PayloadT]):
    """Definition-time task template produced by benchmark authoring code."""

    model_config = {"frozen": True}

    task_slug: str
    instance_key: str
    description: str
    parent_task_slug: str | None = None
    dependency_task_slugs: tuple[str, ...] = ()
    evaluator_binding_keys: tuple[str, ...] = ()
    task_payload: PayloadT = Field(default_factory=EmptyTaskPayload)  # ty: ignore[invalid-assignment]


class Task(BaseModel, Generic[PayloadT]):
    """Runtime task passed to Worker.execute()."""

    model_config = {"frozen": True}

    task_id: UUID
    task_slug: str
    instance_key: str
    description: str
    parent_task_slug: str | None = None
    dependency_task_slugs: tuple[str, ...] = ()
    evaluator_binding_keys: tuple[str, ...] = ()
    task_payload: PayloadT = Field(default_factory=EmptyTaskPayload)  # ty: ignore[invalid-assignment]
