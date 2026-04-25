"""Typed request payloads for Inngest child function invocations.

These are passed via ctx.step.invoke(data=...) from task_execute
to its child functions. They must allow extra fields because Inngest
injects `_inngest` metadata into event data.
"""

from typing import ClassVar
from uuid import UUID

from ergon_core.core.runtime.events.base import InngestEventContract
from pydantic import Field, model_validator


class SandboxSetupRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/sandbox-setup"

    run_id: UUID
    definition_id: UUID
    # For static tasks this is the definition task id; for dynamic subtasks it
    # is the graph node id used as the sandbox registry key.
    task_id: UUID
    benchmark_type: str
    input_resource_ids: list[UUID] = Field(default_factory=list)
    envs: dict[str, str] = Field(default_factory=dict)


class WorkerExecuteRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/worker-execute"

    run_id: UUID
    definition_id: UUID
    task_id: UUID | None
    execution_id: UUID
    sandbox_id: str
    task_slug: str
    task_description: str
    assigned_worker_slug: str
    worker_type: str
    model_target: str
    benchmark_type: str
    node_id: UUID | None = None

    @model_validator(mode="after")
    def _has_static_or_dynamic_identity(self) -> "WorkerExecuteRequest":
        if self.task_id is None and self.node_id is None:
            raise ValueError("WorkerExecuteRequest requires task_id or node_id")
        return self


class PersistOutputsRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/persist-outputs"

    run_id: UUID
    definition_id: UUID
    # Matches SandboxSetupRequest.task_id: definition task id for static tasks,
    # graph node id for dynamic subtasks.
    task_id: UUID
    execution_id: UUID
    sandbox_id: str | None = None
    output_dir: str | None = None
    benchmark_type: str


class EvaluateTaskRunRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/evaluate"

    run_id: UUID
    definition_id: UUID
    task_id: UUID | None = None
    node_id: UUID
    execution_id: UUID
    evaluator_id: UUID
    evaluator_binding_key: str
    evaluator_type: str
    agent_reasoning: str | None = None
    sandbox_id: str | None = None
