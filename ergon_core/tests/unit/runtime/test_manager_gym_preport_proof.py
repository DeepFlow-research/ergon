"""Bounded pre-port probes: real Ergon services, SQLite, and installed SDK replay.

Strict xfails assert desired port behavior that current Ergon does not provide.
These are evidence of gaps, not live PostgreSQL/E2B or full-manager acceptance.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import inngest
import pytest
from inngest.experimental import mocked
from sqlmodel import Session, select

from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.application.communication import service as comm_module
from ergon_core.core.application.communication.models import CreateMessageRequest
from ergon_core.core.application.context.service import ContextEventService
from ergon_core.core.application.evaluation import service as eval_module
from ergon_core.core.application.runtime import task_execution as execution_module
from ergon_core.core.application.runtime import task_management as management_module
from ergon_core.core.application.runtime.lifecycle import on_task_completed_or_failed
from ergon_core.core.application.runtime.orchestration import PrepareTaskExecutionCommand
from ergon_core.core.application.runtime.task_execution import TaskExecutionService
from ergon_core.core.application.runtime.task_execution_repository import WorkerOutputRepository
from ergon_core.core.application.runtime.task_models import CancelTaskCommand, RefineTaskCommand
from ergon_core.core.jobs.task.worker_execute.job import _StepAwareTaskManagementService
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.telemetry.models import SampleTaskAttempt, SampleTaskEvaluation
from ergon_core.core.shared.context_parts import AssistantTextPart, ContextPartChunk
from ergon_core.tests.unit.runtime.test_spawn_dynamic_task import (
    _make_session,
    _make_task,
    _seed_parent,
    _service,
    _SessionContext,
)


@pytest.fixture
def preport(monkeypatch):
    session = _make_session()
    sample_id = uuid4()
    parent = _seed_parent(session, sample_id=sample_id)
    svc = _service(session, monkeypatch)
    monkeypatch.setattr(
        management_module,
        "get_dashboard_event_publisher",
        lambda: SimpleNamespace(publish=AsyncMock()),
    )
    monkeypatch.setattr(management_module.inngest_client, "send", AsyncMock())
    yield session, sample_id, parent, svc
    session.close()


async def child(state, slug, *, deps=(), actor=None):
    _, sample_id, parent, svc = state
    task = _make_task().model_copy(update={"task_slug": slug})
    if actor:
        task.worker.name = actor
        task.worker.actor_key = actor
        task.worker.metadata = {"actor_key": actor, "actor_role": "environment"}
    return await svc.spawn_dynamic_task(
        sample_id=sample_id, parent_task_id=parent.task_id, task=task, depends_on=deps
    )


def node(state, task_id):
    session, sample_id, _, _ = state
    return session.get(SampleGraphNode, (sample_id, task_id))


async def complete(state, task_id):
    session, sample_id, _, svc = state
    node(state, task_id).status = "completed"
    session.commit()
    return await on_task_completed_or_failed(
        session,
        sample_id=sample_id,
        task_id=task_id,
        terminal_status="completed",
        graph_repo=svc._graph_repo,
    )


@pytest.mark.asyncio
async def test_preport_dependency_created_before_completion_releases(preport):
    a = await child(preport, "a")
    b = await child(preport, "b", deps=(a.task_id,))
    ready = await complete(preport, a.task_id)
    assert b.task_id in ready


@pytest.mark.asyncio
async def test_preport_dependency_created_after_completion_releases(preport):
    a = await child(preport, "a")
    await complete(preport, a.task_id)
    dispatched = []

    async def record(sample_id, task_id):
        dispatched.append(task_id)

    preport[3]._runtime_events.dispatch_task_ready = record
    b = await child(preport, "b", deps=(a.task_id,))
    assert b.task_id in dispatched


@pytest.mark.asyncio
async def test_preport_explicit_cancellation_stays_cancelled(preport):
    session, sample_id, _, svc = preport
    a = await child(preport, "a")
    b = await child(preport, "b", deps=(a.task_id,))
    await svc.cancel_task(session, CancelTaskCommand(sample_id=sample_id, task_id=b.task_id))
    ready = await complete(preport, a.task_id)
    assert b.task_id not in ready and node(preport, b.task_id).status == "cancelled"


@pytest.mark.asyncio
async def test_preport_refinement_reaches_executable_task(preport):
    session, sample_id, _, svc = preport
    b = await child(preport, "b")
    await svc.refine_task(
        session,
        RefineTaskCommand(
            sample_id=sample_id, task_id=b.task_id, new_description="revised instructions"
        ),
    )
    loaded = await svc._graph_repo.node(session, sample_id=sample_id, task_id=b.task_id)
    assert loaded.task.description == "revised instructions"


@pytest.mark.asyncio
async def test_preport_prepare_rechecks_dependencies(preport, monkeypatch):
    session, sample_id, _, _ = preport
    a = await child(preport, "a")
    b = await child(preport, "b", deps=(a.task_id,))
    monkeypatch.setattr(execution_module, "get_session", lambda: _SessionContext(session))
    monkeypatch.setattr(execution_module, "_emit_task_status", AsyncMock())
    await TaskExecutionService().prepare(
        PrepareTaskExecutionCommand(sample_id=sample_id, task_id=b.task_id)
    )
    assert not session.exec(
        select(SampleTaskAttempt).where(SampleTaskAttempt.task_id == b.task_id)
    ).all()


@pytest.mark.asyncio
async def test_preport_same_class_people_have_distinct_bindings(preport):
    a = await child(preport, "a", actor="alice")
    b = await child(preport, "b", actor="bob")
    assert (
        node(preport, a.task_id).assigned_worker_slug
        != node(preport, b.task_id).assigned_worker_slug
    )


def run_sdk_manager(state, monkeypatch, *, memoize_decision):
    session, sample_id, parent, _ = state
    calls = []
    sdk = inngest.Inngest(app_id="mag-preport-proof")

    async def decision():
        calls.append("model-response")
        return {"action": "spawn"}

    @sdk.create_function(fn_id="manager", trigger=inngest.TriggerEvent(event="proof"))
    async def manager(ctx: inngest.Context):
        if memoize_decision:
            await ctx.step.run("decision-0", decision)
        else:
            await decision()
        handle = await _StepAwareTaskManagementService(ctx).spawn_dynamic_task(
            sample_id=sample_id,
            parent_task_id=parent.task_id,
            task=_make_task(),
        )
        return str(handle.task_id)

    result = mocked.trigger(
        manager, inngest.Event(name="proof"), mocked.Inngest(app_id="mag-preport-proof")
    )
    if result.status is not mocked.Status.COMPLETED:
        raise RuntimeError(f"SDK proof did not complete: {result}")
    children = session.exec(
        select(SampleGraphNode).where(SampleGraphNode.parent_task_id == parent.task_id)
    ).all()
    if len(children) != 1:
        raise RuntimeError(f"SDK proof created {len(children)} children")
    return len(calls)


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="SDK replay repeats uncheckpointed policy work even though spawning itself is memoized",
)
def test_preport_inline_manager_does_not_repeat_policy(preport, monkeypatch, record_property):
    count = run_sdk_manager(preport, monkeypatch, memoize_decision=False)
    record_property("policy_calls", count)
    assert count == 1, f"policy calls={count} for one decision and one spawned node"


def test_preport_existing_sdk_step_can_checkpoint_policy(preport, monkeypatch):
    assert run_sdk_manager(preport, monkeypatch, memoize_decision=True) == 1


@pytest.mark.asyncio
async def test_preport_full_output_and_actor_context_already_persist(preport):
    session, sample_id, _, _ = preport
    handle = await child(preport, "work")
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
async def test_preport_message_retries_currently_make_two_rows(preport, monkeypatch):
    session, sample_id, _, _ = preport
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
    )
    svc = comm_module.CommunicationService()
    first, second = await svc.save_message(request), await svc.save_message(request)
    assert first.message_id != second.message_id
    assert len(svc.get_thread_messages(first.thread_id)) == 2


@pytest.mark.asyncio
async def test_preport_evaluator_failure_has_no_valid_score(preport, monkeypatch):
    session, sample_id, _, _ = preport
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
