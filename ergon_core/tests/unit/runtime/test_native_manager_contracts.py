"""Public manager operations retain their native persistence and replay contracts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import inngest
import pytest
from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.application.context.service import ContextEventService, ContextReplayMismatch
from ergon_core.core.application.runtime import sample_lifecycle as lifecycle_module
from ergon_core.core.application.runtime import task_execution as execution_module
from ergon_core.core.application.runtime.orchestration import (
    FailTaskExecutionCommand,
    FinalizeTaskExecutionCommand,
    PrepareTaskExecutionCommand,
)
from ergon_core.core.application.runtime.task_errors import (
    TaskAlreadyTerminalError,
    TaskRunningError,
)
from ergon_core.core.application.runtime.task_execution import TaskExecutionService
from ergon_core.core.application.runtime.task_inspection import TaskInspectionService
from ergon_core.core.application.runtime.task_management import TaskManagementService
from ergon_core.core.application.runtime.task_models import RefineTaskCommand
from ergon_core.core.jobs.sample.cleanup import job as cleanup_module
from ergon_core.core.jobs.task.cancel_orphans import job as orphan_module
from ergon_core.core.jobs.task.propagate import job as propagation_module
from ergon_core.core.jobs.task.propagate.contract import TaskFailedEvent
from ergon_core.core.jobs.task.worker_execute.job import _StepAwareTaskManagementService
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.telemetry.models import (
    SampleRecord,
    SampleTaskAttempt,
    SandboxEvent,
)
from ergon_core.core.shared.context_parts import AssistantTextPart, ContextPartChunk
from ergon_core.test_support.runtime_harness import SessionContext, make_task
from inngest.experimental import mocked
from sqlmodel import select


@pytest.mark.asyncio
@pytest.mark.parametrize("running_child", [False, True])
async def test_failure_before_descendant_blocking_rechecks_workflow(
    graph_runtime, monkeypatch, running_child
):
    session, sample_id, parent, _ = graph_runtime
    pending = await graph_runtime.spawn("pending")
    if running_child:
        running = await graph_runtime.spawn("running")
        graph_runtime.node(running.task_id).status = "running"
    parent.status = "failed"
    session.commit()
    for module in (lifecycle_module, orphan_module):
        monkeypatch.setattr(module, "get_session", lambda: SessionContext(session))
    send = AsyncMock()
    monkeypatch.setattr(propagation_module, "send_job_events", send)
    payload = TaskFailedEvent(
        sample_id=sample_id, task_id=parent.task_id, execution_id=uuid4(), error="parent failed"
    )

    # Reproduce the event ordering from the live proof: failure sees pending
    # containment work; the independent descendant handler settles it later.
    initial = await propagation_module.run_propagate_task_failure_job(payload)
    assert not initial.workflow_failed
    send.assert_awaited_once_with([])
    send.reset_mock()

    async def run_step(name, action):
        return await action()

    ctx = SimpleNamespace(step=SimpleNamespace(run=run_step))
    assert await orphan_module.run_block_descendants_on_failed_job(ctx, payload) == 1
    assert graph_runtime.node(pending.task_id).status == "blocked"
    if running_child:
        assert graph_runtime.node(running.task_id).status == "running"
        send.assert_awaited_once_with([])
    else:
        events = send.await_args.args[0]
        assert len(events) == 1
        assert events[0][0] == "workflow/failed"
        assert events[0][1]["sample_id"] == str(sample_id)


@pytest.mark.asyncio
async def test_duplicate_ready_claim_creates_one_attempt(graph_runtime, monkeypatch):
    session, sample_id, _, _ = graph_runtime
    handle = await graph_runtime.spawn("claimed-once")
    monkeypatch.setattr(execution_module, "get_session", lambda: SessionContext(session))
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
async def test_cancelled_parent_cannot_spawn_after_its_cascade(graph_runtime):
    session, _, parent, _ = graph_runtime
    parent.status = "cancelled"
    session.commit()
    with pytest.raises(TaskAlreadyTerminalError):
        await graph_runtime.spawn("late-spawn")
    assert len(session.exec(select(SampleGraphNode)).all()) == 1


@pytest.mark.asyncio
async def test_cancelled_sample_rejects_late_spawns_and_ready_events(graph_runtime, monkeypatch):
    session, sample_id, _, _ = graph_runtime
    pending = await graph_runtime.spawn("queued-before-cancel")
    sample = session.get(SampleRecord, sample_id)
    sample.status = "cancelled"
    session.commit()
    with pytest.raises(ValueError, match="terminal sample"):
        await graph_runtime.spawn("late-spawn")
    monkeypatch.setattr(execution_module, "get_session", lambda: SessionContext(session))
    claim = await TaskExecutionService().prepare(
        PrepareTaskExecutionCommand(sample_id=sample_id, task_id=pending.task_id)
    )
    assert claim.skipped and claim.execution_id is None
    assert not session.exec(select(SampleTaskAttempt)).all()


@pytest.mark.asyncio
async def test_late_success_or_failure_cannot_overwrite_cancelled_attempt(
    graph_runtime, monkeypatch
):
    session, sample_id, _, _ = graph_runtime
    pending = await graph_runtime.spawn("cancel-wins")
    attempt = SampleTaskAttempt(sample_id=sample_id, task_id=pending.task_id, status="cancelled")
    session.add(attempt)
    graph_runtime.node(pending.task_id).status = "cancelled"
    session.commit()
    monkeypatch.setattr(execution_module, "get_session", lambda: SessionContext(session))
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
    assert (
        attempt.status == "cancelled" and graph_runtime.node(pending.task_id).status == "cancelled"
    )
    emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_sample_cancel_closes_every_attempt_and_unattached_sandbox(
    graph_runtime, monkeypatch
):
    session, sample_id, parent, _ = graph_runtime
    running = await graph_runtime.spawn("running")
    graph_runtime.node(running.task_id).status = "running"
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
async def test_pending_replacement_is_atomic_on_invalid_dependency(graph_runtime):
    session, sample_id, _, service = graph_runtime
    a = await graph_runtime.spawn("a")
    b = await graph_runtime.spawn("b", deps=(a.task_id,))
    replacement = make_task().model_copy(update={"task_slug": "b", "description": "new"})
    before = graph_runtime.node(b.task_id).task_json
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
    assert graph_runtime.node(b.task_id).task_json == before
    assert [
        e.source_task_id
        for e in service._graph_repo.get_incoming_edges(
            session, sample_id=sample_id, task_id=b.task_id
        )
    ] == [a.task_id]


def test_sdk_replays_a_rejected_mutation_without_changing_the_error(graph_runtime, monkeypatch):
    session, sample_id, parent, _ = graph_runtime
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
async def test_full_completion_and_context_replay(graph_runtime):
    session, sample_id, _, _ = graph_runtime
    handle = await graph_runtime.spawn("full-result")
    output = WorkerOutput(output="durable " * 1000, metadata={"actor_key": "alice", "hours": 2})
    attempt = SampleTaskAttempt(
        sample_id=sample_id,
        task_id=handle.task_id,
        status="completed",
        worker_output_json=output.model_dump(mode="json"),
    )
    session.add(attempt)
    graph_runtime.node(handle.task_id).status = "completed"
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
