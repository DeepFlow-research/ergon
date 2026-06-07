from typing import ClassVar
from uuid import UUID

from ergon_core.core.application.events.base import InngestEventContract
from pydantic import BaseModel, Field


class PersistOutputsRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/persist-outputs"

    sample_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: str | None = None
    output_dir: str | None = None
    benchmark_type: str
    sandbox_slug: str | None = None


class PersistOutputsResult(BaseModel):
    model_config = {"frozen": True}

    output_resource_ids: list[UUID] = Field(default_factory=list)
    outputs_count: int = 0
