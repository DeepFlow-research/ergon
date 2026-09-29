"""Episode configuration and state, and projections of native Ergon records into MAG's model.

``EpisodeState`` is the manager's view of an episode: the authored workflow plan,
the simulated team, stakeholder preferences and frozen observations of native
task, message and tool records. Native Ergon records stay authoritative; this
state never schedules work.
"""

import json
from datetime import UTC, datetime
from enum import Enum
from functools import cache
from hashlib import sha256
from typing import Annotated, Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from ergon_core.api import Sandbox
from ergon_core.api.worker import WorkerContext, WorkerOutput
from ergon_core.core.application.runtime import status as graph_status
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.telemetry.models import SampleTaskAttempt, ThreadMessage
from ergon_core.core.shared.context_parts import ToolResultPart
from pydantic import BaseModel, Discriminator, Field, Tag, field_validator
from sqlmodel import Session, col, select

from ergon_builtins.benchmarks.manager_gym.actions import ActionResult
from ergon_builtins.benchmarks.manager_gym.constants import SNAPSHOT_PATH
from ergon_builtins.benchmarks.manager_gym.inference import InferenceProfile
from ergon_builtins.benchmarks.manager_gym.upstream import (
    SCENARIOS,
    UPSTREAM_REVISION,
    AgentConfig,
    AgentToolUseEvent,
    AIAgentConfig,
    HumanAgentConfig,
    Message,
    MessageType,
    Preference,
    PreferenceWeights,
    PreferenceWeightUpdateRequest,
    Resource,
    StakeholderConfig,
    Task,
    TaskStatus,
    Workflow,
    create_stakeholder_agent,
)

BENCHMARK_VERSION = "mag-native-v1"
SOURCE_REVISION = UPSTREAM_REVISION

# Upstream parity: preview lengths MAG uses when rendering state for the manager.
RESOURCE_PREVIEW_CHARS = 300
MESSAGE_PREVIEW_CHARS = 140
ACTION_SUMMARY_CHARS = 120
RECENT_ITEMS = 10


def _agent_type(value: dict[str, Any] | AgentConfig) -> str:
    return value["agent_type"] if isinstance(value, dict) else value.agent_type


Actor = Annotated[
    Annotated[AIAgentConfig, Tag("ai")]
    | Annotated[HumanAgentConfig, Tag("human_mock")]
    | Annotated[StakeholderConfig, Tag("stakeholder")],
    Discriminator(_agent_type),
]
"""A member of the simulated team, discriminated by upstream's ``agent_type``."""


class EpisodeConfig(BaseModel):
    """Everything that defines one Manager Gym episode; the root task's payload."""

    scenario: str = Field(description="Scenario key in the upstream catalog, e.g. `icaap`.")
    manager_mode: Literal["cot", "random", "assign_all"] = Field(
        default="cot",
        description="Manager policy: the LLM manager, or upstream's random or one-shot "
        "assignment baseline.",
    )
    seed: int = Field(default=0, description="Seed for simulated humans and baselines.")
    max_decisions: int = Field(default=50, ge=1, le=500, description="Manager decision limit.")
    stakeholder_persona: Literal["balanced", "nitpicky", "hands_off"] = Field(
        default="balanced", description="Upstream stakeholder persona."
    )
    noop_wait_seconds: float = Field(
        default=5, ge=0, le=30, description="How long a no-op waits for running work."
    )
    drain_timeout_seconds: float = Field(
        default=600,
        gt=0,
        le=3600,
        description="Time allowed for admitted work to finish after the last decision.",
    )
    wall_time_seconds: float = Field(
        default=2400, gt=0, le=2700, description="Wall-clock budget for manager decisions."
    )
    input_token_price_per_million: float = Field(
        default=0, ge=0, description="Price used to compute AI workers' simulated cost."
    )
    output_token_price_per_million: float = Field(
        default=0, ge=0, description="Price used to compute AI workers' simulated cost."
    )
    inference: InferenceProfile = Field(
        default_factory=InferenceProfile, description="Model limits for every role."
    )

    @field_validator("scenario")
    @classmethod
    def _known_scenario(cls, value: str) -> str:
        if value not in SCENARIOS:
            raise ValueError(f"Unknown scenario {value!r}; choose from {', '.join(SCENARIOS)}")
        return value


class ScheduledMessage(BaseModel):
    """A stakeholder reply waiting for its delivery decision index."""

    due: int
    content: str
    key: str


class EpisodeState(BaseModel):
    """The manager's state for one episode, checkpointed after every observation."""

    config: EpisodeConfig
    workflow: Workflow
    actors: dict[str, Actor] = Field(default_factory=dict)
    active_actors: list[str] = Field(default_factory=list)
    bindings: dict[UUID, UUID] = Field(
        default_factory=dict, description="Planned task id to its native Ergon task id."
    )
    native_dependencies: dict[UUID, list[UUID]] = Field(
        default_factory=dict, description="Native prerequisites of each bound planned task."
    )
    weights: dict[str, float]
    preference_history: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[ActionResult] = Field(default_factory=list)
    scheduled_messages: list[ScheduledMessage] = Field(default_factory=list)
    message_ticks: dict[UUID, int] = Field(
        default_factory=dict, description="Decision index at which each message was first seen."
    )
    tool_usage: dict[UUID, list[AgentToolUseEvent]] = Field(default_factory=dict)
    timestep: int = 0
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stop_requested: bool = False
    infrastructure_errors: list[str] = Field(default_factory=list)

    def stakeholder(self) -> StakeholderConfig:
        """The episode's stakeholder; every scenario has exactly one."""
        return next(a for a in self.actors.values() if isinstance(a, StakeholderConfig))


def all_tasks(workflow: Workflow) -> dict[UUID, Task]:
    """Every task in the plan, composite and atomic, keyed by id."""
    tasks: dict[UUID, Task] = {}
    for root in workflow.tasks.values():
        for item in [root, *root.get_all_subtasks_flat()]:
            tasks[item.id] = item
    return tasks


def inherited_dependencies(tasks: dict[UUID, Task], task: Task) -> list[UUID]:
    """A task's own prerequisites followed by those of every enclosing composite."""
    dependencies = list(task.dependency_task_ids)
    parent = task.parent_task_id
    while parent:
        dependencies.extend(tasks[parent].dependency_task_ids)
        parent = tasks[parent].parent_task_id
    return dependencies


def dependency_graph(tasks: dict[UUID, Task]) -> dict[UUID, set[UUID]]:
    """Each task's prerequisites, including inherited ones, plus its own subtasks."""
    return {
        task.id: set(inherited_dependencies(tasks, task)) | {t.id for t in task.subtasks}
        for task in tasks.values()
    }


@cache
def scenario_goal(scenario: str) -> str:
    """The scenario's workflow goal, without building an episode."""
    return SCENARIOS[scenario].create_workflow().workflow_goal


@cache
def team_events(scenario: str) -> dict[int, tuple[tuple[str, str], ...]]:
    """Roster changes by decision index, as ``(action, actor id)`` pairs."""
    return {
        tick: tuple(
            (action, actor.agent_id if isinstance(actor, AgentConfig) else str(actor))
            for action, actor, _reason in events
        )
        for tick, events in SCENARIOS[scenario].create_team_timeline().items()
    }


@cache
def preference_requests(scenario: str) -> tuple[PreferenceWeightUpdateRequest, ...]:
    """The scenario's scheduled stakeholder preference changes."""
    factory = SCENARIOS[scenario].create_preference_update_requests
    return tuple(factory()) if factory else ()


def canonicalize(workflow: Workflow, namespace: UUID) -> None:
    """Give every task, resource and constraint an id derived from its position.

    Upstream factories draw random UUIDs; deterministic ids make checkpoints,
    retries and reruns of the same scenario and seed refer to the same plan.
    """
    id_map: dict[UUID, UUID] = {}

    def identify(task: Task, path: str) -> None:
        id_map[task.id] = uuid5(namespace, f"task/{path}/{task.name}")
        for index, child in enumerate(task.subtasks):
            child.parent_task_id = task.id
            identify(child, f"{path}/{index}")

    for index, root in enumerate(workflow.tasks.values()):
        identify(root, str(index))
    for index, resource in enumerate(workflow.resources.values()):
        id_map[resource.id] = uuid5(namespace, f"resource/{index}/{resource.name}")
    for item in all_tasks(workflow).values():
        item.id = id_map[item.id]
        item.parent_task_id = id_map.get(item.parent_task_id) if item.parent_task_id else None
        item.dependency_task_ids = [id_map[d] for d in item.dependency_task_ids]
        item.input_resource_ids = [id_map[r] for r in item.input_resource_ids]
        item.output_resource_ids = [id_map[r] for r in item.output_resource_ids]
    for resource in workflow.resources.values():
        resource.id = id_map[resource.id]
    workflow.tasks = {t.id: t for t in workflow.tasks.values()}
    workflow.resources = {r.id: r for r in workflow.resources.values()}
    workflow.id = namespace
    workflow.owner_id = uuid5(namespace, "owner")
    for index, constraint in enumerate(workflow.constraints):
        constraint.constraint_id = uuid5(namespace, f"constraint/{index}")


def new_episode(config: EpisodeConfig) -> EpisodeState:
    """Build the initial state for ``config`` from the upstream scenario factories."""
    spec = SCENARIOS[config.scenario]
    workflow = spec.create_workflow()
    namespace = uuid5(NAMESPACE_URL, f"{BENCHMARK_VERSION}/{config.scenario}/{config.seed}")
    canonicalize(workflow, namespace)
    workflow.started_at = datetime.now(UTC)
    workflow.seed = config.seed
    workflow.is_active = True
    preferences = spec.create_preferences()
    stakeholder = create_stakeholder_agent(config.stakeholder_persona, preferences)
    stakeholder.initial_preferences = PreferenceWeights(
        preferences=[Preference(name=p.name, weight=p.weight) for p in preferences.preferences]
    )
    actors: dict[str, Actor] = {stakeholder.agent_id: stakeholder}
    for events in spec.create_team_timeline().values():
        for action, actor, _reason in events:
            if action == "add":
                actors[actor.agent_id] = actor
    return EpisodeState(
        config=config,
        workflow=workflow,
        actors=actors,
        active_actors=[stakeholder.agent_id],
        weights=preferences.get_preference_dict(),
        preference_history=[{"timestep": 0, "weights": preferences.get_preference_dict()}],
    )


def update_weights(
    weights: dict[str, float], request: PreferenceWeightUpdateRequest
) -> dict[str, float]:
    """Apply one scheduled preference change, as upstream does, to a copy of ``weights``.

    Upstream mutates the stored preferences in place, so a change scheduled for a
    later decision also rewrites earlier weights; copying keeps history intact.
    """
    result = dict(weights)
    for key, value in request.changes.items():
        if key not in result:
            if request.missing == "error":
                raise ValueError(f"Unknown preference {key}")
            if request.missing == "ignore":
                continue
            result[key] = 0
        if request.mode == "delta":
            result[key] += value
        elif request.mode == "multiplier":
            result[key] *= value
        else:
            result[key] = value
    if (
        request.mode == "absolute"
        and request.redistribution == "uniform"
        and sum(max(0, v) for k, v in request.changes.items() if k in result) <= 0
    ):
        result = {k: 1 / len(result) for k in result}
    if request.clamp_zero:
        result = {k: max(0, v) for k, v in result.items()}
    # Upstream parity: PreferenceWeights normalises even when request.normalize is False.
    return PreferenceWeights(
        preferences=[Preference(name=k, weight=v) for k, v in result.items()]
    ).get_preference_dict()


def apply_timeline(state: EpisodeState) -> None:
    """Apply the roster and preference changes scheduled for the current decision."""
    for action, key in team_events(state.config.scenario).get(state.timestep, ()):
        if action == "add" and key not in state.active_actors:
            state.active_actors.append(key)
        elif action == "remove" and key in state.active_actors:
            state.active_actors.remove(key)
    for request in preference_requests(state.config.scenario):
        if request.timestep == state.timestep:
            state.weights = update_weights(state.weights, request)
            state.preference_history.append(
                {"timestep": state.timestep, "weights": dict(state.weights)}
            )


def _parse_enum[E: Enum](cls: type[E], value: object, default: E) -> E:
    try:
        return cls(value)
    except ValueError:
        return default


def project_tool_usage(
    session: Session, sample_id: UUID, bindings: dict[UUID, UUID]
) -> dict[UUID, list[AgentToolUseEvent]]:
    """Tool calls recorded for each bound task, keyed by planned task id."""
    logical_ids = {native: logical for logical, native in bindings.items()}
    result: dict[UUID, list[AgentToolUseEvent]] = {}
    rows = session.exec(
        select(SampleContextEvent, SampleTaskAttempt.task_id)
        .join(SampleTaskAttempt, col(SampleContextEvent.task_attempt_id) == SampleTaskAttempt.id)
        .where(SampleContextEvent.sample_id == sample_id)
        .order_by(col(SampleContextEvent.created_at), col(SampleContextEvent.sequence))
    ).all()
    for event, task_id in rows:
        logical = logical_ids.get(task_id)
        part = event.parsed_payload().part
        if (
            logical is not None
            and isinstance(part, ToolResultPart)
            and part.tool_name != "final_result"
        ):
            result.setdefault(logical, []).append(
                AgentToolUseEvent(
                    timestamp=event.created_at,
                    agent_id=event.worker_binding_key,
                    task_id=logical,
                    tool_name=part.tool_name,
                    succeeded=not part.is_error,
                    result_size=len(part.content),
                )
            )
    return result


def _project_tasks(
    state: EpisodeState, tasks: dict[UUID, Task], context: WorkerContext, session: Session
) -> None:
    """Copy status, timing, cost and outputs of every bound native task into the plan."""
    for logical, native in state.bindings.items():
        if logical not in tasks:
            continue
        task = tasks[logical]
        result = context.task_inspect.completion(
            session, sample_id=context.sample_id, task_id=native
        )
        task.status = _parse_enum(TaskStatus, result.status, TaskStatus.FAILED)
        task.effective_status = result.status
        task.started_at = result.started_at
        task.completed_at = result.completed_at
        prerequisite_results = [
            context.task_inspect.completion(session, sample_id=context.sample_id, task_id=d)
            for d in state.native_dependencies.get(logical, [])
        ]
        task.deps_ready_at = max(
            (r.completed_at for r in prerequisite_results if r.completed_at),
            default=state.workflow.started_at,
        )
        if result.output:
            metadata = result.output.metadata
            task.actual_duration_hours = metadata.get("simulated_hours", 0)
            task.actual_cost = metadata.get("simulated_cost", 0)
            task.execution_notes = metadata.get("execution_notes", [])
            for raw in metadata.get("resources", []):
                resource = Resource.model_validate(raw)
                state.workflow.resources[resource.id] = resource
                if resource.id not in task.output_resource_ids:
                    task.output_resource_ids.append(resource.id)
        if (
            result.status == graph_status.FAILED
            and not (result.output and result.output.metadata.get("model_failure"))
            and str(native) not in state.infrastructure_errors
        ):
            state.infrastructure_errors.append(str(native))


def _project_messages(state: EpisodeState, context: WorkerContext, session: Session) -> None:
    """Replace the workflow's messages with the sample's persisted messages."""
    rows = session.exec(
        select(ThreadMessage)
        .where(ThreadMessage.sample_id == context.sample_id)
        .order_by(col(ThreadMessage.created_at), col(ThreadMessage.id))
    ).all()
    state.workflow.messages = [
        Message(
            message_id=row.id,
            thread_id=row.thread_id,
            sender_id=row.from_agent_id,
            receiver_id=row.to_agent_id,
            content=row.content,
            message_type=_parse_enum(
                MessageType, row.metadata_json.get("message_type", "general"), MessageType.GENERAL
            ),
            related_task_id=row.metadata_json.get("logical_task_id"),
            timestamp=row.created_at,
            metadata={
                **row.metadata_json,
                "timestep": row.metadata_json.get(
                    "timestep", state.message_ticks.get(row.id, state.timestep)
                ),
            },
        )
        for row in rows
    ]
    for msg in state.workflow.messages:
        state.message_ticks.setdefault(msg.message_id, state.timestep)


def _roll_up(state: EpisodeState, tasks: dict[UUID, Task]) -> None:
    """Derive composite status and workflow totals from the atomic tasks."""
    for task in reversed(list(tasks.values())):
        if task.subtasks:
            leaves = task.get_atomic_subtasks()
            task.status = (
                TaskStatus.COMPLETED
                if all(t.status == TaskStatus.COMPLETED for t in leaves)
                else TaskStatus.PENDING
            )
            task.effective_status = task.status.value
    leaves = [t for t in tasks.values() if not t.subtasks]
    state.workflow.total_cost = sum(t.actual_cost or 0 for t in leaves)
    state.workflow.total_simulated_hours = sum(t.actual_duration_hours or 0 for t in leaves)


async def project_native_state(state: EpisodeState, context: WorkerContext) -> EpisodeState:
    """Return a copy of ``state`` updated from committed native records.

    Called once per durable observation step, so replays see the same projection.
    """
    state = state.model_copy(deep=True)
    state.observed_at = datetime.now(UTC)
    tasks = all_tasks(state.workflow)
    with context.session_factory() as session:
        _project_tasks(state, tasks, context, session)
        _project_messages(state, context, session)
        state.tool_usage = project_tool_usage(session, context.sample_id, state.bindings)
    _roll_up(state, tasks)
    return state


def _agent_view(key: str, actor: AgentConfig, tasks: dict[UUID, Task]) -> dict[str, Any]:
    named = actor if isinstance(actor, HumanAgentConfig | StakeholderConfig) else None
    return {
        "id": key,
        "type": actor.agent_type,
        "description": actor.agent_description,
        "capabilities": actor.agent_capabilities,
        "name": named.name if named else key,
        "role": named.role if named else None,
        "hourly_rate": actor.hourly_rate if isinstance(actor, HumanAgentConfig) else None,
        # Upstream parity: the view lists capacity, which no agent config defines.
        "max_concurrent_tasks": None,
        "current_task_ids": [
            str(t.id)
            for t in tasks.values()
            if t.assigned_agent_id == key and t.status == TaskStatus.RUNNING
        ],
    }


def public_observation(state: EpisodeState) -> dict[str, Any]:
    """What the manager sees: the plan, team, public stakeholder profile and recent activity.

    Private preference weights, future events and rubric definitions are excluded.
    """
    stakeholder = state.stakeholder()
    tasks = all_tasks(state.workflow)
    return {
        "timestep": state.timestep,
        "max_timesteps": state.config.max_decisions,
        "timesteps_remaining": max(0, state.config.max_decisions - state.timestep - 1),
        "goal": state.workflow.workflow_goal,
        "stakeholder_profile": {
            "display_name": stakeholder.name,
            "role": stakeholder.role,
            "preference_summary": stakeholder.initial_preferences.get_preference_summary(),
        },
        "total_cost": state.workflow.total_cost,
        "total_simulated_hours": state.workflow.total_simulated_hours,
        "tasks": [
            {
                **task.model_dump(mode="json", exclude={"subtasks", "execution_notes"}),
                "is_composite": bool(task.subtasks),
                "child_task_ids": [str(t.id) for t in task.subtasks],
            }
            for task in tasks.values()
        ],
        "agents": [_agent_view(k, state.actors[k], tasks) for k in state.active_actors],
        "constraints": [c.model_dump(mode="json") for c in state.workflow.constraints],
        # Full contents stay in native artifacts and the frozen evaluation state.
        "resources": [
            {
                **r.model_dump(mode="json", exclude={"content"}),
                "content": (r.content or "")[:RESOURCE_PREVIEW_CHARS],
                "content_characters": len(r.content or ""),
            }
            for r in state.workflow.resources.values()
        ],
        "messages": [
            {
                **m.model_dump(mode="json", exclude={"content", "metadata"}),
                "content": m.content[:MESSAGE_PREVIEW_CHARS],
            }
            for m in sorted(state.workflow.messages, key=lambda m: m.timestamp, reverse=True)[
                :RECENT_ITEMS
            ]
        ],
        "recent_actions": [
            {
                **a.model_dump(mode="json", exclude={"data", "summary"}),
                "summary": a.summary[:ACTION_SUMMARY_CHARS],
            }
            for a in state.actions[-RECENT_ITEMS:]
        ],
    }


def snapshot_hash(state: EpisodeState) -> str:
    """SHA-256 of the state's canonical JSON; ties a grade to the exact snapshot."""
    return sha256(
        json.dumps(state.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def snapshot_output(
    state: EpisodeState, sandbox: Sandbox, **metadata: object
) -> WorkerOutput:
    """Write the frozen state into ``sandbox`` and return it as the task's output.

    ``MAGRubric`` grades exactly this output; ``snapshot_hash`` ties each grade to it.
    """
    encoded = state.model_dump_json()
    await sandbox.write_file(SNAPSHOT_PATH, encoded.encode())
    return WorkerOutput(
        output=encoded,
        metadata={
            "benchmark_version": BENCHMARK_VERSION,
            "source_revision": SOURCE_REVISION,
            "snapshot_hash": snapshot_hash(state),
            "incomplete": bool(state.infrastructure_errors),
            **metadata,
        },
    )
