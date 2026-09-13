"""Source RandomV2 and one-shot bulk policies; Ergon still owns execution."""

import json
import random
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, create_model, field_validator

from ergon_builtins.benchmarks.manager_gym.actions import (
    ManagerDecision,
    AssignTaskAction,
    CreateTaskAction,
    RemoveTaskAction,
    RefineTaskAction,
    AddTaskDependencyAction,
    RemoveTaskDependencyAction,
    DecomposeTaskAction,
    InspectTaskAction,
    GetWorkflowStatusAction,
    GetAvailableAgentsAction,
    GetPendingTasksAction,
    SendMessageAction,
    NoOpAction,
)
from ergon_builtins.benchmarks.manager_gym.inference import InferenceResult, infer
from ergon_builtins.benchmarks.manager_gym.state import EpisodeState, all_tasks, public_observation


class BaselineInference(BaseModel):
    result: InferenceResult | None = None
    error: str | None = None


class AssignmentPair(BaseModel):
    task_id: UUID
    agent_id: str


class BulkAction(BaseModel):
    reasoning: str
    action_type: Literal["assign_tasks_to_agents"] = "assign_tasks_to_agents"
    assignments: list[AssignmentPair] = Field(default_factory=list)

    @field_validator("assignments", mode="before")
    @classmethod
    def decode_assignments(cls, value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value


class BulkDecision(BaseModel):
    reasoning: str
    action: BulkAction

    @field_validator("action", mode="before")
    @classmethod
    def decode_action(cls, value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value


def random_schema(state: EpisodeState) -> type[BaseModel]:
    # Source order and minimal feasibility filter; purpose-scoped RNG is a
    # recorded v1 change, independent of incidental replay or worker timing.
    candidates = [
        AssignTaskAction,
        CreateTaskAction,
        RemoveTaskAction,
        RefineTaskAction,
        AddTaskDependencyAction,
        RemoveTaskDependencyAction,
        DecomposeTaskAction,
        InspectTaskAction,
        GetWorkflowStatusAction,
        GetAvailableAgentsAction,
        GetPendingTasksAction,
        SendMessageAction,
        NoOpAction,
    ]
    plans = all_tasks(state.workflow)
    assignable = any(
        not t.subtasks
        and str(t.id) not in state.bindings
        and all(d in plans and plans[d].status.value == "completed" for d in t.dependency_task_ids)
        for t in plans.values()
    )
    if not assignable or not state.active_actors:
        candidates.remove(AssignTaskAction)
    selected = random.Random(f"{state.config.seed}:manager:{state.timestep}").choice(candidates)
    return create_model("RandomManagerDecision", __base__=ManagerDecision, action=(selected, ...))


async def baseline_infer(**kwargs) -> BaselineInference:
    """The source baselines deliberately fall back on model errors, recording why."""
    try:
        return BaselineInference(result=await infer(**kwargs))
    except Exception as exc:
        return BaselineInference(error=f"{type(exc).__name__}: {exc}")


async def bulk_infer(state: EpisodeState, model: str) -> BaselineInference:
    return await baseline_infer(
        model=model,
        system=(
            "You are a workflow orchestration manager operating on a task DAG.\n"
            "Goal: assign each task to the best-fit agent so work can proceed without further input.\n"
            "Respect constraints and practical roles: prefer AI agents for analysis/automation;\n"
            "route approvals, governance, and sign-offs to human/stakeholder roles when required.\n"
            "Maximize overall workflow throughput and quality; avoid leaving tasks unassigned.\n"
            "Output exactly one AssignTasksToAgentsAction with a complete 'assignments' list.\n"
        ),
        prompt=json.dumps(public_observation(state)),
        output_type=BulkDecision,
    )


def bulk_assignments(state: EpisodeState, decision: BaselineInference) -> dict[UUID, str]:
    fallback = next(
        (k for k in state.active_actors if state.actors[k]["agent_type"] != "stakeholder"),
        state.active_actors[0] if state.active_actors else None,
    )
    mapping = (
        {
            a.task_id: a.agent_id
            for a in BulkDecision.model_validate(decision.result.output).action.assignments
        }
        if decision.result
        else {}
    )
    # Expand composite mappings to their leaves. An explicit leaf mapping wins.
    plans = all_tasks(state.workflow)
    result = {}
    for task in plans.values():
        if task.subtasks or str(task.id) in state.bindings:
            continue
        actor = mapping.get(task.id)
        parent = task.parent_task_id
        while actor is None and parent:
            actor = mapping.get(parent)
            parent = plans[parent].parent_task_id
        actor = actor or fallback
        if actor:
            result[task.id] = actor
    return result
