"""Dynamic task behaviour a long-running manager worker relies on.

Real Ergon services on in-memory SQLite, plus the installed Inngest SDK's replay:
dependency release, cancellation, refinement, actor bindings, checkpointed
decisions, persisted outputs, idempotent messages and incomplete evaluations.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import inngest
import pytest
from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.application.communication import service as comm_module
from ergon_core.core.application.communication.models import CreateMessageRequest
from ergon_core.core.application.context.service import ContextEventService
from ergon_core.core.application.evaluation import service as eval_module
from ergon_core.core.application.runtime import task_execution as execution_module
from ergon_core.core.application.runtime.orchestration import PrepareTaskExecutionCommand
from ergon_core.core.application.runtime.task_execution import TaskExecutionService
from ergon_core.core.application.runtime.task_execution_repository import WorkerOutputRepository
from ergon_core.core.application.runtime.task_inspection import TaskInspectionService
from ergon_core.core.application.runtime.task_models import CancelTaskCommand, RefineTaskCommand
from ergon_core.core.jobs.task.worker_execute.job import _StepAwareTaskManagementService
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.telemetry.models import SampleTaskAttempt, SampleTaskEvaluation
from ergon_core.core.shared.context_parts import AssistantTextPart, ContextPartChunk
from ergon_core.test_support.runtime_harness import SessionContext, make_task
from inngest.experimental import mocked
from sqlmodel import Session, select


@pytest.mark.parametrize("status", ["completed", "failed", "running", "cancelled"])
def test_completion_exposes_retained_output_for_completed_or_failed_attempts(graph_runtime, status):
    session, sample_id, parent, _ = graph_runtime
    parent.status = status
    output = {"output": "Recorded task outcome", "success": status != "failed", "metadata": {}}
    attempt = SampleTaskAttempt(
        sample_id=sample_id,
        task_id=parent.task_id,
        status=status,
        worker_output_json=output,
    )
    session.add(attempt)
    session.add(parent)
    session.commit()
    result = TaskInspectionService().completion(
        session, sample_id=sample_id, task_id=parent.task_id
    )
    assert result.status == status
    if status in {"completed", "failed"}:
        assert result.output.model_dump() == output
    else:
        assert result.output is None


@pytest.mark.asyncio
async def test_dependency_created_before_completion_releases(graph_runtime):
    a = await graph_runtime.spawn("a")
    b = await graph_runtime.spawn("b", deps=(a.task_id,))
    ready = await graph_runtime.complete(a.task_id)
    assert b.task_id in ready


@pytest.mark.asyncio
async def test_dependency_created_after_completion_releases(graph_runtime):
    a = await graph_runtime.spawn("a")
    await graph_runtime.complete(a.task_id)
    dispatched = []

    async def record(sample_id, task_id):
        dispatched.append(task_id)

    graph_runtime.service._runtime_events.dispatch_task_ready = record
    b = await graph_runtime.spawn("b", deps=(a.task_id,))
    assert b.task_id in dispatched


@pytest.mark.asyncio
async def test_explicit_cancellation_survives_prerequisite_completion(graph_runtime):
    session, sample_id, _, svc = graph_runtime
    a = await graph_runtime.spawn("a")
    b = await graph_runtime.spawn("b", deps=(a.task_id,))
    await svc.cancel_task(session, CancelTaskCommand(sample_id=sample_id, task_id=b.task_id))
    ready = await graph_runtime.complete(a.task_id)
    assert b.task_id not in ready and graph_runtime.node(b.task_id).status == "cancelled"


@pytest.mark.asyncio
async def test_refinement_reaches_executable_task(graph_runtime):
    session, sample_id, _, svc = graph_runtime
    b = await graph_runtime.spawn("b")
    await svc.refine_task(
        session,
        RefineTaskCommand(
            sample_id=sample_id, task_id=b.task_id, new_description="revised instructions"
        ),
    )
    loaded = await svc._graph_repo.node(session, sample_id=sample_id, task_id=b.task_id)
    assert loaded.task.description == "revised instructions"


@pytest.mark.asyncio
async def test_prepare_rechecks_dependencies(graph_runtime, monkeypatch):
    session, sample_id, _, _ = graph_runtime
    a = await graph_runtime.spawn("a")
    b = await graph_runtime.spawn("b", deps=(a.task_id,))
    monkeypatch.setattr(execution_module, "get_session", lambda: SessionContext(session))
    monkeypatch.setattr(execution_module, "_emit_task_status", AsyncMock())
    await TaskExecutionService().prepare(
        PrepareTaskExecutionCommand(sample_id=sample_id, task_id=b.task_id)
    )
    assert not session.exec(
        select(SampleTaskAttempt).where(SampleTaskAttempt.task_id == b.task_id)
    ).all()


@pytest.mark.asyncio
async def test_workers_of_one_class_keep_distinct_actor_bindings(graph_runtime):
    a = await graph_runtime.spawn("a", actor="alice")
    b = await graph_runtime.spawn("b", actor="bob")
    assert (
        graph_runtime.node(a.task_id).assigned_worker_slug
        != graph_runtime.node(b.task_id).assigned_worker_slug
    )


def run_sdk_manager(state, monkeypatch):
    session, sample_id, parent, _ = state
    calls = []
    sdk = inngest.Inngest(app_id="mag-graph_runtime-proof")

    async def decision():
        calls.append("model-response")
        return {"action": "spawn"}

    @sdk.create_function(fn_id="manager", trigger=inngest.TriggerEvent(event="proof"))
    async def manager(ctx: inngest.Context):
        await ctx.step.run("decision-0", decision)
        handle = await _StepAwareTaskManagementService(ctx).spawn_dynamic_task(
            sample_id=sample_id,
            parent_task_id=parent.task_id,
            task=make_task(),
        )
        return str(handle.task_id)

    result = mocked.trigger(
        manager, inngest.Event(name="proof"), mocked.Inngest(app_id="mag-graph_runtime-proof")
    )
    if result.status is not mocked.Status.COMPLETED:
        raise RuntimeError(f"SDK proof did not complete: {result}")
    children = session.exec(
        select(SampleGraphNode).where(SampleGraphNode.parent_task_id == parent.task_id)
    ).all()
    if len(children) != 1:
        raise RuntimeError(f"SDK proof created {len(children)} children")
    return len(calls)


def test_checkpointed_decision_runs_once_across_sdk_replay(graph_runtime, monkeypatch):
    assert run_sdk_manager(graph_runtime, monkeypatch) == 1


@pytest.mark.asyncio
async def test_full_worker_output_and_actor_binding_persist(graph_runtime):
    session, sample_id, _, _ = graph_runtime
    handle = await graph_runtime.spawn("work")
    attempt = SampleTaskAttempt(sample_id=sample_id, task_id=handle.task_id, status="running")
    session.add(attempt)
    session.commit()
    output = WorkerOutput(output="x" * 3000, metadata={"actor_key": "alice", "hours": 2.5})
    repo = WorkerOutputRepository()
    await repo.persist(session, execution_id=attempt.id, output=output)
    session.commit()
    assert await repo.load(session, execution_id=attempt.id) == output
    await ContextEventService().persist_chunk(
        session,
        sample_id=sample_id,
        execution_id=attempt.id,
        worker_binding_key="alice",
        chunk=ContextPartChunk(part=AssistantTextPart(content="work")),
    )
    assert session.exec(select(SampleContextEvent)).one().worker_binding_key == "alice"


@pytest.mark.asyncio
async def test_retried_message_with_idempotency_key_is_stored_once(graph_runtime, monkeypatch):
    session, sample_id, _, _ = graph_runtime
    engine = session.get_bind()
    monkeypatch.setattr(comm_module, "get_session", lambda: Session(engine))
    monkeypatch.setattr(
        comm_module, "get_dashboard_event_publisher", lambda: SimpleNamespace(publish=AsyncMock())
    )
    request = CreateMessageRequest(
        sample_id=sample_id,
        from_agent_id="alice",
        to_agent_id="bob",
        thread_topic="work",
        content="decision-0",
        idempotency_key="decision-0",
    )
    svc = comm_module.CommunicationService()
    first, second = await svc.save_message(request), await svc.save_message(request)
    assert first.message_id == second.message_id
    assert len(svc.get_thread_messages(first.thread_id)) == 1


@pytest.mark.asyncio
async def test_incomplete_evaluator_failure_persists_no_score(graph_runtime, monkeypatch):
    session, sample_id, _, _ = graph_runtime
    engine = session.get_bind()
    monkeypatch.setattr(eval_module, "get_session", lambda: Session(engine))
    await eval_module.EvaluationService().persist_failure(
        sample_id=sample_id,
        task_attempt_id=uuid4(),
        task_id=uuid4(),
        binding_key="proof-judge",
        exc=RuntimeError("synthetic judge outage"),
        incomplete=True,
    )
    with Session(engine) as read:
        row = read.exec(
            select(SampleTaskEvaluation).where(SampleTaskEvaluation.sample_id == sample_id)
        ).one()
        assert row.score is None, f"persisted failure score={row.score}"
