"""Upstream MAG's baseline managers: RandomV2 and one-shot bulk assignment.

Both still call the model, and both keep upstream's behaviour of recording a
model error as a failed decision rather than failing the episode.
"""

import json
import random
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, create_model
from pydantic_ai.exceptions import AgentRunError

from ergon_builtins.benchmarks.manager_gym.actions import (
    AddTaskDependencyAction,
    AssignTaskAction,
    CreateTaskAction,
    DecomposeTaskAction,
    GetAvailableAgentsAction,
    GetPendingTasksAction,
    GetWorkflowStatusAction,
    InspectTaskAction,
    ManagerDecision,
    NoOpAction,
    RefineTaskAction,
    RemoveTaskAction,
    RemoveTaskDependencyAction,
    SendMessageAction,
)
from ergon_builtins.benchmarks.manager_gym.inference import (
    InferenceProfile,
    InferenceResult,
    Role,
    infer,
)
from ergon_builtins.benchmarks.manager_gym.parsing import JsonDecoded
from ergon_builtins.benchmarks.manager_gym.prompts import BULK_ASSIGNMENT_SYSTEM_PROMPT
from ergon_builtins.benchmarks.manager_gym.state import EpisodeState, all_tasks, public_observation
from ergon_builtins.benchmarks.manager_gym.upstream import StakeholderConfig, TaskStatus

# Model failures a baseline records instead of raising. PydanticAI reports
# provider HTTP and connection errors as AgentRunError subclasses.
MODEL_ERRORS = (AgentRunError, TimeoutError)


class BaselineInference(BaseModel):
    """A baseline's model call: its result, or the error it fell back from."""

    result: InferenceResult | None = None
    error: str | None = None


# Part of the bulk manager's output schema; no docstring, see BulkAction.
class AssignmentPair(BaseModel):
    task_id: UUID
    agent_id: str


# BulkAction and BulkDecision form the bulk manager's output schema, so they have
# no docstrings: the model sees exactly upstream's schema.
class BulkAction(BaseModel):
    reasoning: str
    action_type: Literal["assign_tasks_to_agents"] = "assign_tasks_to_agents"
    assignments: Annotated[list[AssignmentPair], JsonDecoded] = Field(default_factory=list)


class BulkDecision(BaseModel):
    reasoning: str
    action: Annotated[BulkAction, JsonDecoded]


def random_schema(state: EpisodeState) -> type[BaseModel]:
    """RandomV2's decision schema: one randomly chosen action type for the model to fill.

    Upstream parity: the candidate order and the feasibility filter for assignment.
    The RNG is seeded per decision, where upstream used the global generator, so a
    rerun or replay chooses the same action type.
    """
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
        and t.id not in state.bindings
        and all(
            d in plans and plans[d].status == TaskStatus.COMPLETED for d in t.dependency_task_ids
        )
        for t in plans.values()
    )
    if not assignable or not state.active_actors:
        candidates.remove(AssignTaskAction)
    selected = random.Random(f"{state.config.seed}:manager:{state.timestep}").choice(candidates)
    return create_model("RandomManagerDecision", __base__=ManagerDecision, action=(selected, ...))


async def baseline_infer(
    *,
    model: str,
    role: Role,
    profile: InferenceProfile,
    system: str,
    prompt: str,
    output_type: type[BaseModel],
) -> BaselineInference:
    """Call ``infer``, recording a model or transport failure instead of raising it."""
    try:
        return BaselineInference(
            result=await infer(
                model=model,
                role=role,
                profile=profile,
                system=system,
                prompt=prompt,
                output_type=output_type,
            )
        )
    except MODEL_ERRORS as exc:
        return BaselineInference(error=f"{type(exc).__name__}: {exc}")


async def bulk_infer(state: EpisodeState, model: str) -> BaselineInference:
    """Ask the model for one assignment of every task."""
    return await baseline_infer(
        model=model,
        role="manager",
        profile=state.config.inference,
        system=BULK_ASSIGNMENT_SYSTEM_PROMPT,
        prompt=json.dumps(public_observation(state)),
        output_type=BulkDecision,
    )


def bulk_assignments(state: EpisodeState, decision: BaselineInference) -> dict[UUID, str]:
    """Map every unassigned atomic task to an agent.

    A mapping for a composite applies to its leaves unless a leaf has its own.
    Upstream parity: unmapped tasks go to the first active non-stakeholder.
    """
    fallback = next(
        (k for k in state.active_actors if not isinstance(state.actors[k], StakeholderConfig)),
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
    plans = all_tasks(state.workflow)
    result = {}
    for task in plans.values():
        if task.subtasks or task.id in state.bindings:
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
