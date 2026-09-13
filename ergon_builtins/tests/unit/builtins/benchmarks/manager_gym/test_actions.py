"""The source action vocabulary executes through the actual Ergon task facade."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlmodel import Session

from ergon_core.api.worker import WorkerContext
from ergon_core.core.application.communication import service as communication_module
from ergon_core.core.application.runtime import task_inspection as inspection_module
from ergon_core.core.application.runtime.task_inspection import TaskInspectionService
from ergon_core.core.application.resources.service import SampleResourceReadService
from ergon_core.tests.unit.runtime.test_manager_gym_preport_proof import preport
from ergon_core.tests.unit.runtime.test_spawn_dynamic_task import _SessionContext
from ergon_builtins.benchmarks.manager_gym import manager
from ergon_builtins.benchmarks.manager_gym import baselines
from ergon_builtins.benchmarks.manager_gym.actions import (
    ManagerDecision,
    AssignTaskAction,
    RemoveTaskAction,
)
from ergon_builtins.benchmarks.manager_gym.inference import InferenceResult, INTERNAL_MODEL
from ergon_builtins.benchmarks.manager_gym.state import all_tasks, public_observation
from ergon_builtins.benchmarks.manager_gym.source_types import Resource
from tests.fixtures.mag_contract import contract_state

ACTIONS = [
    "assign_task",
    "create_task",
    "remove_task",
    "refine_task",
    "add_task_dependency",
    "remove_task_dependency",
    "inspect_task",
    "decompose_task",
    "send_message",
    "noop",
    "get_workflow_status",
    "get_available_agents",
    "get_pending_tasks",
]


def test_assignment_does_not_expose_unrelated_workflow_resources():
    state = contract_state()
    planned = next(iter(state.workflow.tasks.values()))
    allowed = Resource(name="Declared input", description="For this task", content="allowed")
    unrelated = Resource(name="Other task input", description="Not assigned", content="unrelated")
    state.workflow.resources = {r.id: r for r in (allowed, unrelated)}
    planned.input_resource_ids = [allowed.id]
    actor = next(k for k, a in state.actors.items() if a["agent_type"] == "ai")
    task = manager.work_task(state, planned, actor, INTERNAL_MODEL, [])
    assert [r.id for r in task.task_payload.resources] == [allowed.id]


@pytest.fixture
def runtime(preport, monkeypatch):
    session, sample_id, root, service = preport
    monkeypatch.setattr(inspection_module, "get_session", lambda: _SessionContext(session))
    monkeypatch.setattr(communication_module, "get_session", lambda: Session(session.get_bind()))
    monkeypatch.setattr(
        communication_module,
        "get_dashboard_event_publisher",
        lambda: SimpleNamespace(publish=AsyncMock()),
    )
    context = WorkerContext(
        sample_id=sample_id,
        task_id=root.task_id,
        execution_id=uuid4(),
        sandbox_id="offline-contract",
        task_mgmt=service,
        task_inspect=TaskInspectionService(),
        resource_service=SampleResourceReadService(),
        session_factory=lambda: _SessionContext(session),
    )
    return contract_state(), context


def action_data(name, state):
    plans = list(state.workflow.tasks.values())
    fields = {
        "assign_task": {
            "task_id": str(plans[0].id),
            "agent_id": next(
                k for k in state.active_actors if state.actors[k]["agent_type"] == "ai"
            ),
        },
        "create_task": {
            "name": "New plan",
            "description": "New work",
            "estimated_duration_hours": 1,
            "estimated_cost": 1,
        },
        "remove_task": {"task_id": str(plans[4].id)},
        "refine_task": {
            "task_id": str(plans[1].id),
            "new_description": "Revised scope",
            "new_name": None,
            "new_estimated_duration": None,
            "new_estimated_cost": None,
            "additional_instructions": None,
        },
        "add_task_dependency": {
            "dependent_task_id": str(plans[2].id),
            "prerequisite_task_id": str(plans[0].id),
        },
        "remove_task_dependency": {
            "dependent_task_id": str(plans[2].id),
            "prerequisite_task_id": str(plans[1].id),
        },
        "inspect_task": {"task_id": str(plans[0].id)},
        "decompose_task": {"task_id": str(plans[5].id)},
        "send_message": {"receiver_id": state.active_actors[0], "content": "Contract message"},
    }.get(name, {})
    return {"action_type": name, "reasoning": "Action contract", **fields}


@pytest.mark.parametrize("name", ACTIONS)
@pytest.mark.asyncio
async def test_all_source_actions_reach_native_result(runtime, monkeypatch, name):
    state, context = runtime
    parsed = ManagerDecision(reasoning="Contract decision", action=action_data(name, state))

    async def infer(**kwargs):
        output = (
            parsed.model_dump(mode="json")
            if kwargs["output_type"] is ManagerDecision
            else {
                "reasoning": "Split work",
                "subtasks": [
                    {
                        "name": f"Part {i}",
                        "executive_summary": "Scope",
                        "implementation_plan": "Write a note",
                        "acceptance_criteria": "One resource",
                    }
                    for i in range(3)
                ],
            }
        )
        return InferenceResult(output=output, elapsed_seconds=0, input_tokens=1, output_tokens=1)

    monkeypatch.setattr(manager, "infer", infer)
    chunks = [chunk async for chunk in manager.policy_turn(state, context, INTERNAL_MODEL)]
    assert state.actions[-1].success and not chunks[-1].part.is_error
    if name.startswith("get_"):
        assert "last_action" not in state.actions[-1].data
    if name == "assign_task":
        info = await context.get_task(next(iter(state.bindings.values())))
        assert info.status == "pending" and info.description
    if name == "decompose_task":
        assert len(list(state.workflow.tasks.values())[-1].subtasks) == 3


@pytest.mark.asyncio
async def test_plan_cycles_are_rejected_without_mutation(runtime):
    state, context = runtime
    a, b = list(state.workflow.tasks.values())[:2]
    action = ManagerDecision(
        reasoning="Cycle",
        action={
            "reasoning": "Cycle",
            "action_type": "add_task_dependency",
            "dependent_task_id": str(a.id),
            "prerequisite_task_id": str(b.id),
        },
    ).action
    before = state.model_dump(mode="json")
    with pytest.raises(ValueError, match="cycle"):
        await manager.apply_action(state, action, context, INTERNAL_MODEL)
    assert state.model_dump(mode="json") == before


def test_public_observation_hides_future_roster_and_private_weights():
    state = contract_state()
    observation = public_observation(state)
    assert "weights" not in observation and "preferences" not in str(observation["agents"])
    assert {a["id"] for a in observation["agents"]} == set(state.active_actors)
    assert all("subtasks" not in task for task in observation["tasks"])
    assert len(observation["tasks"]) == len(all_tasks(state.workflow))
    assert observation["stakeholder_profile"]["preference_summary"]
    assert "preference_history" not in observation


@pytest.mark.asyncio
async def test_reassignment_preserves_work_dependencies_without_serializing_an_actor(runtime):
    state, context = runtime
    a, b, c = list(state.workflow.tasks.values())[:3]
    for planned in (a, b, c):
        planned.dependency_task_ids = []
    b.dependency_task_ids = [a.id]
    ai = next(k for k in state.active_actors if state.actors[k]["agent_type"] == "ai")
    human = next(k for k in state.active_actors if state.actors[k]["agent_type"] == "human_mock")
    for planned, actor in ((a, ai), (b, ai), (b, human)):
        await manager.assign(
            state,
            AssignTaskAction(reasoning="Assign", task_id=str(planned.id), agent_id=actor),
            context,
            INTERNAL_MODEL,
        )
    b_native = state.bindings[str(b.id)]
    b_info = await context.get_task(b_native)
    assert b_info.depends_on == [state.bindings[str(a.id)]]
    await manager.remove_work(
        state, RemoveTaskAction(reasoning="Remove", task_id=b.id), context, INTERNAL_MODEL
    )
    await manager.assign(
        state,
        AssignTaskAction(reasoning="Continue", task_id=str(c.id), agent_id=ai),
        context,
        INTERNAL_MODEL,
    )
    c_info = await context.get_task(state.bindings[str(c.id)])
    assert b_native not in c_info.depends_on
    assert c_info.depends_on == []
    assert (await context.get_task(b_native)).status == "cancelled"


@pytest.mark.asyncio
async def test_removed_prerequisite_is_policy_blocked_not_infrastructure_failure(runtime):
    state, context = runtime
    a, b = list(state.workflow.tasks.values())[:2]
    ai = next(k for k in state.active_actors if state.actors[k]["agent_type"] == "ai")
    for planned in (a, b):
        await manager.assign(
            state,
            AssignTaskAction(reasoning="Assign", task_id=str(planned.id), agent_id=ai),
            context,
            INTERNAL_MODEL,
        )
    assert not await manager.has_cancelled_prerequisite(context, state.bindings[str(b.id)])
    await manager.remove_work(
        state, RemoveTaskAction(reasoning="Remove", task_id=a.id), context, INTERNAL_MODEL
    )
    assert await manager.has_cancelled_prerequisite(context, state.bindings[str(b.id)])
    state.config.drain_timeout_seconds = 0.001
    await manager.drain_admitted_work(state, context)
    assert not state.infrastructure_errors
    assert (await context.get_task(state.bindings[str(b.id)])).status == "cancelled"


@pytest.mark.asyncio
async def test_assign_all_model_fallback_uses_native_dependencies_once(runtime, monkeypatch):
    state, context = runtime
    state.config.manager_mode = "assign_all"
    state.config.noop_wait_seconds = 0
    failed_model = AsyncMock(side_effect=RuntimeError("Contract model failure"))
    monkeypatch.setattr(baselines, "infer", failed_model)
    first = [c async for c in manager.policy_turn(state, context, INTERNAL_MODEL)]
    assert len(state.bindings) == 6
    assert state.actions[-1].success
    assert "Contract model failure" in state.actions[-1].data["model_error"]
    assert first[-1].part.tool_name == "assign_tasks_to_agents"
    state.timestep += 1
    second = [c async for c in manager.policy_turn(state, context, INTERNAL_MODEL)]
    assert len(state.bindings) == 6 and failed_model.await_count == 1
    assert second[-1].part.tool_name == "noop"


@pytest.mark.asyncio
async def test_random_baseline_is_one_selected_model_action_with_recorded_fallback(
    runtime, monkeypatch
):
    state, context = runtime
    state.config.manager_mode = "random"
    selected = baselines.random_schema(state)
    assert (
        selected.model_fields["action"].annotation
        is baselines.random_schema(state).model_fields["action"].annotation
    )
    assert "anyOf" not in selected.model_json_schema()["properties"]["action"]
    failed_model = AsyncMock(side_effect=RuntimeError("Contract random failure"))
    monkeypatch.setattr(baselines, "infer", failed_model)
    chunks = [c async for c in manager.policy_turn(state, context, INTERNAL_MODEL)]
    assert not state.actions[-1].success and chunks[-1].part.is_error
    assert "Contract random failure" in state.actions[-1].data["error"]
    assert failed_model.call_args.kwargs["model"] == INTERNAL_MODEL
