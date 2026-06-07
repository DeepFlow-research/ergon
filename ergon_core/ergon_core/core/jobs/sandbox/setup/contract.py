from typing import ClassVar
from uuid import UUID

from ergon_core.core.application.events.base import InngestEventContract
from pydantic import BaseModel, Field


class SandboxSetupRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/sandbox-setup"

    sample_id: UUID
    definition_id: UUID
    task_id: UUID
    benchmark_type: str
    sandbox_slug: str | None = None
    input_resource_ids: list[UUID] = Field(default_factory=list)
    envs: dict[str, str] = Field(default_factory=dict)


class SandboxReadyResult(BaseModel):
    model_config = {"frozen": True}

    sandbox_id: str
    output_dir: str | None = None
