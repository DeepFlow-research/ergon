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
    task_id: UUID | None
    benchmark_type: str
    input_resource_ids: list[UUID] = []
    envs: dict[str, str] = {}


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
    model_target: str | None = None
    benchmark_type: str
    node_id: UUID | None = None


class PersistOutputsRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/persist-outputs"

    run_id: UUID
    definition_id: UUID
    task_id: UUID | None
    execution_id: UUID
    sandbox_id: str | None = None
    output_dir: str | None = None
    benchmark_type: str
    # Worker's final assistant message (from ``WorkerOutput.output``).  Also
    # written into ``RunTaskExecution.final_assistant_message`` via
    # ``finalize_success`` for quick single-column reads; we additionally
    # publish it as a ``RunResource(kind=OUTPUT, name="worker_output")`` so
    # evaluators and downstream tooling can treat it like any other resource
    # (content hashed, blob-backed, append-only).  ``None`` when the worker
    # produced no text output.
    worker_final_assistant_message: str | None = None


class EvaluateTaskRunRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/evaluate"

    run_id: UUID
    definition_id: UUID
    task_id: UUID | None
    execution_id: UUID
    evaluator_id: UUID
    evaluator_binding_key: str | None = None
    evaluator_type: str
    agent_reasoning: str | None = None
    sandbox_id: str | None = None
