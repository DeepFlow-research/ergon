"""Typed request payloads for Inngest child function invocations.

These are passed via ctx.step.invoke(data=...) from task_execute
to its child functions. They must allow extra fields because Inngest
injects `_inngest` metadata into event data.
"""

from typing import ClassVar
from uuid import UUID

from ergon_core.core.runtime.events.base import InngestEventContract


class SandboxSetupRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/sandbox-setup"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    benchmark_type: str
    input_resource_ids: list[UUID] = []
    envs: dict[str, str] = {}


class WorkerExecuteRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/worker-execute"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: str
    task_key: str
    task_description: str = ""  # slopcop: ignore[no-str-empty-default]
    worker_binding_key: str = ""  # slopcop: ignore[no-str-empty-default]
    worker_type: str
    model_target: str | None = None
    benchmark_type: str


class PersistOutputsRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/persist-outputs"

    run_id: UUID
    definition_id: UUID
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
    task_id: UUID
    execution_id: UUID
    evaluator_id: UUID
    evaluator_binding_key: str = ""  # slopcop: ignore[no-str-empty-default]
    evaluator_type: str
    agent_reasoning: str = ""  # slopcop: ignore[no-str-empty-default]
    sandbox_id: str = ""  # slopcop: ignore[no-str-empty-default]
