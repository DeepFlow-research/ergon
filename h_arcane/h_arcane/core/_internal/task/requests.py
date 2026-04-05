"""Request types for child Inngest functions.

These are the input types for step.invoke() child functions.
They act as "internal" events - only used for parent→child invocation.

Each request type has a `name` class variable that serves as the event name
for the Inngest function trigger.
"""

from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel


class SandboxSetupRequest(BaseModel):
    """Request to setup a sandbox for task execution."""

    name: ClassVar[str] = "task/sandbox-setup"

    run_id: UUID
    experiment_id: UUID
    task_id: UUID
    benchmark_name: str
    input_resource_ids: list[UUID] = []
    envs: dict[str, str] = {}


class WorkerExecuteRequest(BaseModel):
    """Request to execute a worker in an existing sandbox."""

    name: ClassVar[str] = "task/worker-execute"

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: str
    task_description: str
    input_resource_ids: list[UUID]
    benchmark_name: str
    max_questions: int


class PersistOutputsRequest(BaseModel):
    """Request to download and persist outputs from sandbox."""

    name: ClassVar[str] = "task/persist-outputs"

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: str
    output_dir: str
    input_resource_ids: list[UUID]
