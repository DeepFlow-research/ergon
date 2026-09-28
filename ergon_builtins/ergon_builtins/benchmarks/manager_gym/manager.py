"""The Manager Gym manager: the policy loop that runs one episode as a native Ergon task.

Each decision observes committed native state, asks the policy for one action,
and carries it out through ``WorkerContext`` task tools. Observations, model
calls and message sends are durable steps, so a retried manager replays
earlier decisions instead of repeating them.
"""

import json
import random
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime
from graphlib import TopologicalSorter
from typing import Annotated, ClassVar, cast
from uuid import UUID, uuid5

from ergon_core.api import Task, Worker, WorkerContext, WorkerStreamItem
from ergon_core.core.application.communication.models import MessageResponse
from ergon_core.core.application.runtime import status as graph_status
from ergon_core.core.application.runtime.errors import GraphError
from ergon_core.core.shared.context_parts import ContextPartChunk, ToolResultPart
from pydantic import BaseModel, Field

from ergon_builtins.benchmarks.manager_gym.actions import (
    ActionResult,
    ActionType,
    AddTaskDependencyAction,
    AssignTaskAction,
    CreateTaskAction,
    DecomposeTaskAction,
    GetAvailableAgentsAction,
    GetPendingTasksAction,
    GetWorkflowStatusAction,
    InspectTaskAction,
    ManagerAction,
    ManagerDecision,
    NoOpAction,
    RefineTaskAction,
    RemoveTaskAction,
    RemoveTaskDependencyAction,
    SendMessageAction,
)
from ergon_builtins.benchmarks.manager_gym.baselines import (
    BaselineInference,
    baseline_infer,
    bulk_assignments,
    bulk_infer,
    random_schema,
)
from ergon_builtins.benchmarks.manager_gym.communication import persist_message
from ergon_builtins.benchmarks.manager_gym.constants import (
    MANAGER_ACTOR_ID,
    SANDBOX_TIMEOUT_SECONDS,
)
from ergon_builtins.benchmarks.manager_gym.inference import InferenceResult, infer
from ergon_builtins.benchmarks.manager_gym.parsing import JsonDecoded
from ergon_builtins.benchmarks.manager_gym.prompts import (
    DECOMPOSED_SUBTASK_DESCRIPTION,
    DECOMPOSITION_GOAL_SUFFIX,
    DECOMPOSITION_SYSTEM_PROMPT,
    MANAGER_SCHEDULING_RULES,
    STAKEHOLDER_REPLY,
    STAKEHOLDER_REPLY_QUOTE,
    STAKEHOLDER_SUGGESTION,
)
from ergon_builtins.benchmarks.manager_gym.state import (
    EpisodeConfig,
    EpisodeState,
    ScheduledMessage,
    all_tasks,
    apply_timeline,
    dependency_graph,
    inherited_dependencies,
    new_episode,
    project_native_state,
    public_observation,
    snapshot_output,
)
from ergon_builtins.benchmarks.manager_gym.upstream import (
    STRUCTURED_MANAGER_SYSTEM_PROMPT_TEMPLATE,
    TASK_DECOMPOSITION_PROMPT,
    HumanAgentConfig,
    StakeholderConfig,
    TaskStatus,
)
from ergon_builtins.benchmarks.manager_gym.upstream import Task as PlannedTask
from ergon_builtins.benchmarks.manager_gym.workers import (
    MAGHumanWorker,
    MAGStakeholderWorker,
    MAGWorkWorker,
    WorkPayload,
    WorkTask,
)
from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox

# Native statuses of planned work the manager may still remove.
REMOVABLE = frozenset({graph_status.PENDING, graph_status.READY, graph_status.CANCELLED})
# Native statuses a no-op waits on.
IN_FLIGHT = frozenset({graph_status.RUNNING, graph_status.PENDING, graph_status.READY})

# Upstream parity: StakeholderAgent reconsiders its 20 most recent inbound
# messages on every decision rather than reading each once.
STAKEHOLDER_INBOX_WINDOW = 20
STAKEHOLDER_QUOTE_CHARS = 200

ACTION_ERRORS = (ValueError, KeyError, GraphError)
"""Errors that make a manager action fail without failing the episode."""


class EpisodeTask(Task[EpisodeConfig]):
    """The root task of an episode; its worker is the manager."""


# Part of the decomposer's output schema; no docstring, as with Decomposition.
class DecomposedSubtask(BaseModel):
    name: str
    executive_summary: str
    implementation_plan: str
    acceptance_criteria: str


# The decomposer's structured output. No docstring: the model sees this schema.
class Decomposition(BaseModel):
    reasoning: str
    subtasks: Annotated[list[DecomposedSubtask], JsonDecoded] = Field(min_length=3, max_length=6)


class DrainClassification(BaseModel):
    """Checkpointed answer to whether a task waits on a policy-blocked prerequisite."""

    policy_blocked: bool


def dependency_leaves(state: EpisodeState, planned: PlannedTask) -> list[UUID]:
    """Native ids of the atomic prerequisites of ``planned``, including inherited ones.

    Raises:
        ValueError: A prerequisite is missing, is the task itself or its own
            composite, or has not been assigned yet.
    """
    tasks = all_tasks(state.workflow)
    dependencies = []
    for dep in inherited_dependencies(tasks, planned):
        if dep == planned.id or dep not in tasks:
            raise ValueError("Dependency must identify another existing task")
        source = tasks[dep]
        for leaf in source.get_atomic_subtasks() if source.subtasks else [source]:
            if leaf.id == planned.id:
                raise ValueError("A task cannot depend on its own composite")
            native = state.bindings.get(leaf.id)
            if native is None:
                raise ValueError(f"Assign prerequisite {leaf.id} before admitting its dependent")
            dependencies.append(native)
    return list(dict.fromkeys(dependencies))


def work_task(
    state: EpisodeState, planned: PlannedTask, actor: str, model: str, dependencies: list[UUID]
) -> WorkTask:
    """The native task that runs ``planned`` as ``actor``."""
    config = state.actors[actor]
    if isinstance(config, HumanAgentConfig):
        worker_class: type[MAGWorkWorker] = MAGHumanWorker
    elif isinstance(config, StakeholderConfig):
        worker_class = MAGStakeholderWorker
    else:
        worker_class = MAGWorkWorker
    return WorkTask(
        task_slug=f"mag-work-{planned.id}",
        instance_key="default",
        description=planned.description,
        task_payload=WorkPayload(
            episode=state.config,
            planned_task=planned.model_copy(deep=True),
            actor=config,
            current_weights=dict(state.weights) if isinstance(config, StakeholderConfig) else {},
            resources=[
                state.workflow.resources[key]
                for key in planned.input_resource_ids
                if key in state.workflow.resources
            ],
            dependencies=dependencies,
            permitted_recipients=[MANAGER_ACTOR_ID, *state.active_actors],
            timestep=state.timestep,
        ),
        worker=worker_class(name=actor, actor_key=actor, model=model),
        sandbox=E2BSandbox(timeout_seconds=SANDBOX_TIMEOUT_SECONDS),
    )


async def assign(
    state: EpisodeState, action: AssignTaskAction, context: WorkerContext, model: str
) -> None:
    """Admit an atomic task as native work, or reassign its unclaimed native task."""
    planned = all_tasks(state.workflow)[UUID(action.task_id)]
    if planned.subtasks:
        raise ValueError("Assign atomic leaves; a composite is an unbound plan")
    if action.agent_id not in state.active_actors:
        raise ValueError("Agent is not currently available")
    native = state.bindings.get(planned.id)
    # Reassignment keeps the task's existing native prerequisites, including any
    # added outside the plan; one actor's tasks are never queued behind each other.
    dependencies = list(
        dict.fromkeys(
            [*dependency_leaves(state, planned), *state.native_dependencies.get(planned.id, [])]
        )
    )
    assigned = planned.model_copy(update={"assigned_agent_id": action.agent_id}, deep=True)
    executable = cast(Task, work_task(state, assigned, action.agent_id, model, dependencies))
    if native is None:
        child = await context.spawn_task(executable, depends_on=tuple(dependencies))
        native = child.task_id
    else:
        await context.refine_task(
            native,
            description=planned.description,
            replacement=executable,
            depends_on=tuple(dependencies),
        )
    state.bindings[planned.id] = native
    state.native_dependencies[planned.id] = dependencies
    planned.assigned_agent_id = action.agent_id


async def save_message(
    state: EpisodeState,
    context: WorkerContext,
    sender: str,
    recipient: str,
    content: str,
    key: str,
    message_type: str = "general",
) -> None:
    """Send a message from the manager task as a durable step."""

    async def send() -> MessageResponse:
        return await persist_message(
            context,
            sender=sender,
            recipient=recipient,
            content=content,
            metadata={"timestep": state.timestep, "message_type": message_type},
            idempotency_key=f"{context.execution_id}:{key}:{recipient}",
        )

    receipt = await context.run_step(
        f"message-{key}-{recipient}", send, output_type=MessageResponse
    )
    state.message_ticks[receipt.message_id] = state.timestep


async def stakeholder_tick(state: EpisodeState, context: WorkerContext) -> None:
    """Upstream's scripted stakeholder behaviour for one decision.

    Delivers replies that are due, schedules new replies to recent messages, and
    may push a suggestion. Every message is attributed to the stakeholder.
    """
    actor = state.stakeholder()
    key = actor.agent_id
    due = [m for m in state.scheduled_messages if m.due <= state.timestep]
    state.scheduled_messages = [m for m in state.scheduled_messages if m.due > state.timestep]
    for item in due:
        await save_message(state, context, key, MANAGER_ACTOR_ID, item.content, item.key)
    rng = random.Random(f"{state.config.seed}:{key}:tick:{state.timestep}")
    inbox = [m for m in reversed(state.workflow.messages) if m.receiver_id == key]
    for index, msg in enumerate(inbox[:STAKEHOLDER_INBOX_WINDOW]):
        if rng.random() <= actor.clarification_reply_rate:
            delay = rng.randint(
                actor.response_latency_steps_min,
                max(actor.response_latency_steps_min, actor.response_latency_steps_max),
            )
            content = STAKEHOLDER_REPLY
            if actor.verbosity > 1:
                content += STAKEHOLDER_REPLY_QUOTE.format(
                    content=msg.content[:STAKEHOLDER_QUOTE_CHARS]
                )
            state.scheduled_messages.append(
                ScheduledMessage(
                    due=state.timestep + delay,
                    content=content,
                    key=f"reply-{state.timestep}-{index}",
                )
            )
    if (
        rng.random() <= actor.push_probability_per_timestep
        and rng.random() <= actor.suggestion_rate
    ):
        await save_message(
            state,
            context,
            key,
            MANAGER_ACTOR_ID,
            STAKEHOLDER_SUGGESTION.format(name=actor.name, role=actor.role),
            f"push-{state.timestep}",
        )


def create_task(state: EpisodeState, action: CreateTaskAction) -> None:
    """Add a new root task to the plan."""
    task = PlannedTask(
        id=uuid5(state.workflow.id, f"created/{state.timestep}"),
        name=action.name,
        description=action.description,
        estimated_duration_hours=action.estimated_duration_hours,
        estimated_cost=action.estimated_cost,
    )
    state.workflow.tasks[task.id] = task


async def remove_work(
    state: EpisodeState, action: RemoveTaskAction, context: WorkerContext
) -> None:
    """Remove a task and its subtasks from the plan, cancelling their native tasks."""
    tasks = all_tasks(state.workflow)
    planned = tasks[action.task_id]
    affected = [planned, *planned.get_all_subtasks_flat()]
    for item in affected:
        if item.id in state.bindings:
            if (item.effective_status or item.status.value) not in REMOVABLE:
                raise ValueError("Remove only unstarted work")
    for item in affected:
        native = state.bindings.get(item.id)
        if native:
            await context.cancel_task(native)
    if planned.parent_task_id:
        tasks[planned.parent_task_id].remove_subtask(planned.id)
    else:
        del state.workflow.tasks[planned.id]


def patch_description(planned: PlannedTask, action: RefineTaskAction) -> None:
    """Apply a refinement's optional fields to ``planned``."""
    if action.new_name is not None:
        planned.name = action.new_name
    if action.new_description is not None:
        planned.description = action.new_description
    if action.new_estimated_duration is not None:
        planned.estimated_duration_hours = action.new_estimated_duration
    if action.new_estimated_cost is not None:
        planned.estimated_cost = action.new_estimated_cost
    if action.additional_instructions:
        planned.execution_notes.append(action.additional_instructions)


def validate_dependencies(state: EpisodeState, replacement: PlannedTask) -> None:
    """Check that replacing a task keeps every reference valid and the plan acyclic.

    Raises:
        ValueError: A dependency names a missing task.
        graphlib.CycleError: The edit would create a cycle.
    """
    tasks = all_tasks(state.workflow)
    tasks[replacement.id] = replacement
    graph = dependency_graph(tasks)
    if not all(dependencies.issubset(tasks) for dependencies in graph.values()):
        raise ValueError("Dependency does not identify an existing plan")
    TopologicalSorter(graph).prepare()


def _refined_plan(
    tasks: dict[UUID, PlannedTask],
    action: RefineTaskAction | AddTaskDependencyAction | RemoveTaskDependencyAction,
) -> PlannedTask:
    task_id = action.task_id if isinstance(action, RefineTaskAction) else action.dependent_task_id
    planned = tasks[task_id].model_copy(deep=True)
    if isinstance(action, RefineTaskAction):
        patch_description(planned, action)
    elif isinstance(action, AddTaskDependencyAction):
        if action.prerequisite_task_id not in tasks or action.prerequisite_task_id == task_id:
            raise ValueError("Invalid prerequisite")
        if action.prerequisite_task_id not in planned.dependency_task_ids:
            planned.dependency_task_ids.append(action.prerequisite_task_id)
    else:
        if action.prerequisite_task_id not in planned.dependency_task_ids:
            raise ValueError("Dependency does not exist")
        planned.dependency_task_ids.remove(action.prerequisite_task_id)
    return planned


async def refine_work(
    state: EpisodeState,
    action: RefineTaskAction | AddTaskDependencyAction | RemoveTaskDependencyAction,
    context: WorkerContext,
    model: str,
) -> None:
    """Edit an unstarted task's instructions or prerequisites, in the plan and natively."""
    tasks = all_tasks(state.workflow)
    planned = _refined_plan(tasks, action)
    task_id = planned.id
    validate_dependencies(state, planned)
    if planned.subtasks and any(t.id in state.bindings for t in planned.get_atomic_subtasks()):
        raise ValueError("Refine a composite before assigning its descendants")
    native = state.bindings.get(task_id)
    if native:
        dependencies = dependency_leaves(state, planned)
        old_work_deps = dependency_leaves(state, tasks[task_id])
        dependencies.extend(
            d
            for d in state.native_dependencies[task_id]
            if d not in old_work_deps and d not in dependencies
        )
        if planned.assigned_agent_id is None:
            raise ValueError("Bound task is missing its actor")
        replacement = work_task(state, planned, planned.assigned_agent_id, model, dependencies)
        await context.refine_task(
            native,
            description=planned.description,
            replacement=cast(Task, replacement),
            depends_on=tuple(dependencies),
        )
        state.native_dependencies[task_id] = dependencies
    if planned.parent_task_id:
        parent = tasks[planned.parent_task_id]
        parent.subtasks = [planned if t.id == task_id else t for t in parent.subtasks]
    else:
        state.workflow.tasks[task_id] = planned


async def decompose_work(
    state: EpisodeState, action: DecomposeTaskAction, context: WorkerContext, model: str
) -> list[ContextPartChunk]:
    """Split an unassigned atomic task into model-planned subtasks.

    Returns:
        The decomposer's transcript chunks.
    """
    planned = all_tasks(state.workflow)[action.task_id]
    if planned.subtasks or planned.id in state.bindings:
        raise ValueError("Decompose only an unassigned atomic plan")

    async def decompose() -> InferenceResult:
        return await infer(
            model=model,
            role="decomposer",
            profile=state.config.inference,
            system=DECOMPOSITION_SYSTEM_PROMPT,
            prompt=TASK_DECOMPOSITION_PROMPT.format(
                task_name=planned.name, task_description=planned.description
            )
            + DECOMPOSITION_GOAL_SUFFIX.format(goal=state.workflow.workflow_goal),
            output_type=Decomposition,
        )

    result = await context.run_step(
        f"decompose-{state.timestep}", decompose, output_type=InferenceResult
    )
    parsed = Decomposition.model_validate(result.output)
    for index, item in enumerate(parsed.subtasks):
        planned.add_subtask(
            PlannedTask(
                id=uuid5(planned.id, f"decomposition/{index}"),
                name=item.name,
                input_resource_ids=list(planned.input_resource_ids),
                output_resource_ids=list(planned.output_resource_ids),
                description=DECOMPOSED_SUBTASK_DESCRIPTION.format(
                    executive_summary=item.executive_summary,
                    implementation_plan=item.implementation_plan,
                    acceptance_criteria=item.acceptance_criteria,
                ),
            )
        )
    return list(result.chunks)


async def send_manager_message(
    state: EpisodeState, action: SendMessageAction, context: WorkerContext
) -> None:
    """Send the manager's message to one actor, or to every active actor."""
    recipients = [action.receiver_id] if action.receiver_id else state.active_actors
    if any(r not in state.active_actors for r in recipients):
        raise ValueError("Recipient is not an available actor")
    for recipient in recipients:
        await save_message(
            state,
            context,
            MANAGER_ACTOR_ID,
            recipient,
            action.content,
            f"action-{state.timestep}",
            message_type="alert",
        )


async def wait_briefly(state: EpisodeState, context: WorkerContext) -> None:
    """On a no-op, give the earliest in-flight task a short time to finish."""
    tasks = all_tasks(state.workflow)
    pending = [
        native
        for logical, native in sorted(state.bindings.items())
        if logical in tasks and tasks[logical].effective_status in IN_FLIGHT
    ]
    if pending and state.config.noop_wait_seconds:
        await context.wait_for_task(pending[0], timeout_seconds=state.config.noop_wait_seconds)


async def apply_action(
    state: EpisodeState, action: ManagerAction, context: WorkerContext, model: str
) -> list[ContextPartChunk]:
    """Carry out one manager action against the plan and native Ergon state.

    Returns:
        Transcript chunks from any model call the action made.

    Raises:
        ValueError, KeyError, GraphError: The action is invalid in the current state.
    """
    match action:
        case AssignTaskAction():
            await assign(state, action, context, model)
        case CreateTaskAction():
            create_task(state, action)
        case RemoveTaskAction():
            await remove_work(state, action, context)
        case RefineTaskAction() | AddTaskDependencyAction() | RemoveTaskDependencyAction():
            await refine_work(state, action, context, model)
        case DecomposeTaskAction():
            return await decompose_work(state, action, context, model)
        case SendMessageAction():
            await send_manager_message(state, action, context)
        case NoOpAction():
            await wait_briefly(state, context)
        case (
            GetWorkflowStatusAction()
            | GetAvailableAgentsAction()
            | GetPendingTasksAction()
            | InspectTaskAction()
        ):
            # Read-only: successful_action_result returns what was asked for.
            pass
    return []


# Observation fields each "get_*" action returns.
INFO_FIELDS = {
    "get_workflow_status": ("goal", "tasks", "constraints", "total_cost", "total_simulated_hours"),
    "get_available_agents": ("agents",),
    "get_pending_tasks": ("tasks",),
}


def successful_action_result(state: EpisodeState, action: ManagerAction) -> ActionResult:
    """The record of an action that applied, including what a query returned."""
    result = ActionResult(
        action_type=action.action_type,
        summary="Applied",
        kind="mutation",
        data={},
        timestep=state.timestep,
    )
    if isinstance(action, InspectTaskAction):
        result.data = all_tasks(state.workflow)[action.task_id].model_dump(mode="json")
        result.kind = "inspection"
    elif action.action_type in INFO_FIELDS:
        observation = public_observation(state)
        result.data = {key: observation[key] for key in INFO_FIELDS[action.action_type]}
        if action.action_type == "get_pending_tasks":
            result.data["tasks"] = [
                t for t in observation["tasks"] if t["status"] == TaskStatus.PENDING.value
            ]
        result.kind = "info"
    elif isinstance(action, NoOpAction):
        result.kind = "noop"
    elif isinstance(action, SendMessageAction):
        result.kind = "message"
    return result


def record_action(state: EpisodeState, result: ActionResult) -> ContextPartChunk:
    """Append ``result`` to the episode and return it as a transcript tool result."""
    state.actions.append(result)
    return ContextPartChunk(
        part=ToolResultPart(
            tool_call_id=f"mag-action-{state.timestep}",
            tool_name=result.action_type,
            content=result.model_dump_json(),
            is_error=not result.success,
        )
    )


def _failed_action(
    state: EpisodeState, action_type: ActionType, summary: str, **data: object
) -> ActionResult:
    return ActionResult(
        action_type=action_type,
        summary=summary,
        kind="failed_action",
        data=dict(data),
        timestep=state.timestep,
        success=False,
    )


async def _assign_in_order(
    state: EpisodeState, mapping: dict[UUID, str], context: WorkerContext, model: str
) -> tuple[list[str], list[dict[str, str]]]:
    """Assign mapped tasks prerequisites first; collect successes and failures."""
    graph = {
        task_id: sorted(deps)
        for task_id, deps in dependency_graph(all_tasks(state.workflow)).items()
    }
    assigned: list[str] = []
    failures: list[dict[str, str]] = []
    for task_id in TopologicalSorter(graph).static_order():
        if task_id not in mapping:
            continue
        action = AssignTaskAction(
            reasoning="One-shot bulk mapping", task_id=str(task_id), agent_id=mapping[task_id]
        )
        try:
            await assign(state, action, context, model)
            assigned.append(str(task_id))
        except ACTION_ERRORS as exc:
            failures.append({"task_id": str(task_id), "error": str(exc)})
    return assigned, failures


async def bulk_turn(
    state: EpisodeState, context: WorkerContext, model: str
) -> AsyncGenerator[ContextPartChunk]:
    """One decision of upstream's ``assign_all`` baseline.

    The first decision maps every task to an agent in one model call and assigns
    them; later decisions wait.
    """
    if state.actions:
        await wait_briefly(state, context)
        yield record_action(
            state,
            ActionResult(
                action_type="noop",
                summary="One-shot mapping already applied",
                kind="noop",
                data={},
                timestep=state.timestep,
            ),
        )
        return

    async def decide() -> BaselineInference:
        return await bulk_infer(state, model)

    decision = await context.run_step("bulk-mapping", decide, output_type=BaselineInference)
    if decision.result:
        for chunk in decision.result.chunks:
            yield chunk
    assigned, failures = await _assign_in_order(
        state, bulk_assignments(state, decision), context, model
    )
    yield record_action(
        state,
        ActionResult(
            action_type="assign_tasks_to_agents",
            summary="Applied one-shot mapping with fallback",
            kind="mutation",
            data={"assigned": assigned, "failures": failures, "model_error": decision.error},
            timestep=state.timestep,
            success=not failures,
        ),
    )


def _started_at(state: EpisodeState) -> datetime:
    if state.workflow.started_at is None:
        raise ValueError("Episode is missing its start time")
    return state.workflow.started_at


async def policy_turn(
    state: EpisodeState, context: WorkerContext, model: str
) -> AsyncGenerator[ContextPartChunk]:
    """One manager decision: ask the policy for an action and apply it."""
    if state.config.manager_mode == "assign_all":
        async for chunk in bulk_turn(state, context, model):
            yield chunk
        return
    observation = public_observation(state)
    schema = random_schema(state) if state.config.manager_mode == "random" else ManagerDecision
    system = STRUCTURED_MANAGER_SYSTEM_PROMPT_TEMPLATE.format(
        today_date=_started_at(state).strftime("%d.%m.%Y"),
        available_agents=json.dumps(observation["agents"]),
        available_actions=json.dumps(schema.model_json_schema()),
    )
    system += MANAGER_SCHEDULING_RULES
    prompt = json.dumps(observation)
    profile = state.config.inference

    async def decide() -> BaselineInference:
        if state.config.manager_mode == "random":
            return await baseline_infer(
                model=model,
                role="manager",
                profile=profile,
                system=system,
                prompt=prompt,
                output_type=schema,
            )
        result = await infer(
            model=model,
            role="manager",
            profile=profile,
            system=system,
            prompt=prompt,
            output_type=schema,
        )
        return BaselineInference(result=result)

    recorded = await context.run_step(
        f"manager-decision-{state.timestep}", decide, output_type=BaselineInference
    )
    decision = recorded.result
    if decision is None:
        yield record_action(
            state,
            _failed_action(
                state, "failed_action", "Random baseline model fallback", error=recorded.error
            ),
        )
        return
    for chunk in decision.chunks:
        yield chunk
    parsed = ManagerDecision.model_validate(decision.output)
    try:
        for chunk in await apply_action(state, parsed.action, context, model):
            yield chunk
        result = successful_action_result(state, parsed.action)
    except ACTION_ERRORS as exc:
        result = _failed_action(state, parsed.action.action_type, str(exc))
    yield record_action(state, result)


async def has_policy_blocked_prerequisite(context: WorkerContext, native: UUID) -> bool:
    """Whether unfinished work waits on a prerequisite the policy cancelled or a model failed.

    Reads the authoritative graph without releasing anything.
    """
    pending = [native]
    visited: set[UUID] = set()
    while pending:
        task_id = pending.pop()
        if task_id in visited:
            continue
        visited.add(task_id)
        task = await context.get_task(task_id)
        if task_id != native and task.status in {graph_status.CANCELLED, graph_status.BLOCKED}:
            return True
        if task_id != native and task.status == graph_status.FAILED:
            with context.session_factory() as session:
                result = context.task_inspect.completion(
                    session, sample_id=context.sample_id, task_id=task_id
                )
            if result.output and result.output.metadata.get("model_failure"):
                return True
        pending.extend(task.depends_on)
    return False


def _classifier(
    context: WorkerContext, native: UUID
) -> Callable[[], Awaitable[DrainClassification]]:
    async def classify() -> DrainClassification:
        return DrainClassification(
            policy_blocked=await has_policy_blocked_prerequisite(context, native)
        )

    return classify


async def drain_admitted_work(state: EpisodeState, context: WorkerContext) -> None:
    """Let admitted work finish within the drain budget, then cancel what remains.

    Work blocked by a policy outcome is cancelled at once. Work still running at
    the deadline is cancelled and, unless blocked by the policy, recorded as an
    infrastructure error.
    """
    remaining = state.config.drain_timeout_seconds
    checked_at = state.observed_at.timestamp()
    for _, native in sorted(state.bindings.items()):
        classify = _classifier(context, native)
        before = await context.run_step(
            f"drain-blocked-before-{native}", classify, output_type=DrainClassification
        )
        if before.policy_blocked and (await context.get_task(native)).status in {
            graph_status.PENDING,
            graph_status.BLOCKED,
        }:
            await context.cancel_task(
                native, reason="MAG prerequisite has a terminal policy outcome"
            )
            continue
        result = await context.wait_for_task(native, timeout_seconds=max(0, remaining))
        remaining -= max(0, result.checked_at - checked_at)
        checked_at = result.checked_at
        if result.timed_out:
            classification = await context.run_step(
                f"drain-blocked-{native}", classify, output_type=DrainClassification
            )
            await context.cancel_task(native, reason="MAG drain deadline")
            if not classification.policy_blocked:
                state.infrastructure_errors.append(f"drain timeout:{native}")


def _observer(state: EpisodeState, context: WorkerContext) -> Callable[[], Awaitable[EpisodeState]]:
    async def observe() -> EpisodeState:
        return await project_native_state(state, context)

    return observe


def _should_stop(state: EpisodeState) -> bool:
    return state.stop_requested or all(
        t.status == TaskStatus.COMPLETED
        for t in all_tasks(state.workflow).values()
        if not t.subtasks
    )


class MAGManagerWorker(Worker):
    """Runs one Manager Gym episode as the manager.

    The task payload is an ``EpisodeConfig``. The worker's output is the frozen
    final ``EpisodeState``, which ``MAGRubric`` grades.
    """

    type_slug: ClassVar[str] = "manager-gym-manager"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem]:
        config = EpisodeConfig.model_validate(task.task_payload.model_dump())

        async def initialize() -> EpisodeState:
            return new_episode(config)

        state = await context.run_step("episode-initialize", initialize, output_type=EpisodeState)
        started_at = _started_at(state)
        for tick in range(config.max_decisions):
            state.timestep = tick
            apply_timeline(state)
            state = await context.run_step(
                f"observe-{tick}", _observer(state, context), output_type=EpisodeState
            )
            if (state.observed_at - started_at).total_seconds() >= config.wall_time_seconds:
                state.infrastructure_errors.append("episode wall deadline")
                break
            if any(
                m.metadata.get("message_type") == "request_end_workflow"
                for m in state.workflow.messages
            ):
                state.stop_requested = True
                break
            await stakeholder_tick(state, context)
            async for chunk in policy_turn(state, context, self.model):
                yield chunk
            if _should_stop(state):
                break
        await drain_admitted_work(state, context)

        async def freeze() -> EpisodeState:
            final = await project_native_state(state, context)
            final.workflow.completed_at = datetime.now(UTC)
            final.workflow.is_active = False
            return final

        state = await context.run_step("episode-final-snapshot", freeze, output_type=EpisodeState)
        yield await snapshot_output(
            state,
            task.sandbox,
            decision_count=len(state.actions),
            native_task_count=len(state.bindings),
        )
