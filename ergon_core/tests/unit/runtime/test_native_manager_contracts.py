"""Public manager operations retain their native persistence and replay contracts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import inngest
from inngest.experimental import mocked
import pytest
from sqlmodel import select

from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.application.context.service import ContextEventService, ContextReplayMismatch
from ergon_core.core.application.runtime import task_execution as execution_module
from ergon_core.core.application.runtime.orchestration import (
    PrepareTaskExecutionCommand,
    FinalizeTaskExecutionCommand,
    FailTaskExecutionCommand,
)
from ergon_core.core.application.runtime.task_execution import TaskExecutionService
from ergon_core.core.application.runtime.task_errors import (
    TaskRunningError,
    TaskAlreadyTerminalError,
)
from ergon_core.core.application.runtime.task_inspection import TaskInspectionService
from ergon_core.core.application.runtime.task_management import TaskManagementService
from ergon_core.core.application.runtime.task_models import RefineTaskCommand
from ergon_core.core.jobs.task.worker_execute.job import _StepAwareTaskManagementService
from ergon_core.core.persistence.telemetry.models import (
    SampleTaskAttempt,
    SampleRecord,
    SandboxEvent,
)
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.jobs.sample.cleanup import job as cleanup_module
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.shared.context_parts import AssistantTextPart, ContextPartChunk
from ergon_core.tests.unit.runtime.test_manager_gym_preport_proof import preport, child, node
from ergon_core.tests.unit.runtime.test_spawn_dynamic_task import _SessionContext, _make_task


@pytest.mark.asyncio
async def test_duplicate_ready_claim_creates_one_attempt(preport, monkeypatch):
    session, sample_id, _, _ = preport
    handle = await child(preport, "claimed-once")
    monkeypatch.setattr(execution_module, "get_session", lambda: _SessionContext(session))
    monkeypatch.setattr(execution_module, "_emit_task_status", AsyncMock())
    command = PrepareTaskExecutionCommand(sample_id=sample_id, task_id=handle.task_id)
    first, second = (
        await TaskExecutionService().prepare(command),
        await TaskExecutionService().prepare(command),
    )
    assert first.execution_id is not None and not first.skipped
    assert second.skipped and second.execution_id is None
    assert len(session.exec(select(SampleTaskAttempt)).all()) == 1


@pytest.mark.asyncio
async def test_cancelled_parent_cannot_spawn_after_its_cascade(preport):
    session, _, parent, _ = preport
    parent.status = "cancelled"
    session.commit()
    with pytest.raises(TaskAlreadyTerminalError):
        await child(preport, "late-spawn")
    assert len(session.exec(select(SampleGraphNode)).all()) == 1


@pytest.mark.asyncio
async def test_cancelled_sample_rejects_late_spawns_and_ready_events(preport, monkeypatch):
    session, sample_id, _, _ = preport
    pending = await child(preport, "queued-before-cancel")
    sample = session.get(SampleRecord, sample_id)
    sample.status = "cancelled"
    session.commit()
    with pytest.raises(ValueError, match="terminal sample"):
        await child(preport, "late-spawn")
    monkeypatch.setattr(execution_module, "get_session", lambda: _SessionContext(session))
    claim = await TaskExecutionService().prepare(
        PrepareTaskExecutionCommand(sample_id=sample_id, task_id=pending.task_id)
    )
    assert claim.skipped and claim.execution_id is None
    assert not session.exec(select(SampleTaskAttempt)).all()


@pytest.mark.asyncio
async def test_late_success_or_failure_cannot_overwrite_cancelled_attempt(preport, monkeypatch):
    session, sample_id, _, _ = preport
    pending = await child(preport, "cancel-wins")
    attempt = SampleTaskAttempt(sample_id=sample_id, task_id=pending.task_id, status="cancelled")
    session.add(attempt)
    node(preport, pending.task_id).status = "cancelled"
    session.commit()
    monkeypatch.setattr(execution_module, "get_session", lambda: _SessionContext(session))
    emit = AsyncMock()
    monkeypatch.setattr(execution_module, "_emit_task_status", emit)
    service = TaskExecutionService()
    await service.finalize_success(FinalizeTaskExecutionCommand(execution_id=attempt.id))
    await service.finalize_failure(
        FailTaskExecutionCommand(
            execution_id=attempt.id,
            sample_id=sample_id,
            task_id=pending.task_id,
            error_message="Late provider result after cancellation",
        )
    )
    assert attempt.status == "cancelled" and node(preport, pending.task_id).status == "cancelled"
    emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_sample_cancel_closes_every_attempt_and_unattached_sandbox(preport, monkeypatch):
    session, sample_id, parent, _ = preport
    running = await child(preport, "running")
    node(preport, running.task_id).status = "running"
    for task_id, sandbox_id in ((parent.task_id, "root-box"), (running.task_id, "child-box")):
        session.add(
            SampleTaskAttempt(
                sample_id=sample_id, task_id=task_id, status="running", sandbox_id=sandbox_id
            )
        )
    session.add(
        SandboxEvent(
            sample_id=sample_id,
            task_id=running.task_id,
            sandbox_id="setup-box",
            kind="sandbox_created",
        )
    )
    session.get(SampleRecord, sample_id).status = "cancelled"
    session.commit()
    boxes = await cleanup_module._cancel_sample_work(session, sample_id)
    assert boxes == {"root-box", "child-box", "setup-box"}
    assert {n.status for n in session.exec(select(SampleGraphNode)).all()} == {"cancelled"}
    assert {a.status for a in session.exec(select(SampleTaskAttempt)).all()} == {"cancelled"}
    # Cleanup retries retain the same ownership set after every row is terminal.
    assert await cleanup_module._cancel_sample_work(session, sample_id) == boxes


@pytest.mark.asyncio
async def test_pending_replacement_is_atomic_on_invalid_dependency(preport):
    session, sample_id, _, service = preport
    a = await child(preport, "a")
    b = await child(preport, "b", deps=(a.task_id,))
    replacement = _make_task().model_copy(update={"task_slug": "b", "description": "new"})
    before = node(preport, b.task_id).task_json
    with pytest.raises(Exception, match="missing node"):
        await service.refine_task(
            session,
            RefineTaskCommand(
                sample_id=sample_id,
                task_id=b.task_id,
                new_description="new",
                replacement=replacement,
                depends_on=(uuid4(),),
            ),
        )
    # Even a caller retaining/committing its session cannot publish a partial replacement.
    session.commit()
    assert node(preport, b.task_id).task_json == before
    assert [
        e.source_task_id
        for e in service._graph_repo.get_incoming_edges(
            session, sample_id=sample_id, task_id=b.task_id
        )
    ] == [a.task_id]


def test_sdk_replays_a_rejected_mutation_without_changing_the_error(preport, monkeypatch):
    session, sample_id, parent, _ = preport
    calls = []

    async def reject(self, session, command):
        calls.append(command.task_id)
        raise TaskRunningError(command.task_id, "running")

    monkeypatch.setattr(TaskManagementService, "refine_task", reject)
    sdk = inngest.Inngest(app_id="mag-mutation-contract")

    @sdk.create_function(fn_id="manager", trigger=inngest.TriggerEvent(event="contract"))
    async def manager(ctx):
        service = _StepAwareTaskManagementService(ctx)
        try:
            await service.refine_task(
                session,
                RefineTaskCommand(
                    sample_id=sample_id, task_id=parent.task_id, new_description="edit"
                ),
            )
        except TaskRunningError as error:
            assert error.task_id == parent.task_id and error.current_status == "running"
        await ctx.step.run("subsequent-step", lambda: "continued")
        return "continued"

    result = mocked.trigger(
        manager, inngest.Event(name="contract"), mocked.Inngest(app_id="mag-mutation-contract")
    )
    assert result.status is mocked.Status.COMPLETED and calls == [parent.task_id]


@pytest.mark.asyncio
async def test_full_completion_and_context_replay(preport):
    session, sample_id, _, _ = preport
    handle = await child(preport, "full-result")
    output = WorkerOutput(output="durable " * 1000, metadata={"actor_key": "alice", "hours": 2})
    attempt = SampleTaskAttempt(
        sample_id=sample_id,
        task_id=handle.task_id,
        status="completed",
        worker_output_json=output.model_dump(mode="json"),
    )
    session.add(attempt)
    node(preport, handle.task_id).status = "completed"
    session.commit()
    assert (
        TaskInspectionService()
        .completion(session, sample_id=sample_id, task_id=handle.task_id)
        .output
        == output
    )
    chunk = ContextPartChunk(part=AssistantTextPart(content="one generation"))
    for _ in range(2):
        await ContextEventService().persist_chunk(
            session,
            sample_id=sample_id,
            execution_id=attempt.id,
            worker_binding_key="alice",
            chunk=chunk,
            replay=True,
        )
    assert len(session.exec(select(SampleContextEvent)).all()) == 1
    with pytest.raises(ContextReplayMismatch):
        await ContextEventService().persist_chunk(
            session,
            sample_id=sample_id,
            execution_id=attempt.id,
            worker_binding_key="alice",
            chunk=ContextPartChunk(part=AssistantTextPart(content="different generation")),
            replay=True,
        )
