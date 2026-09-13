"""Authored work and frozen benchmark projections, never an execution queue."""

from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, Field
from sqlmodel import Session, select, col

from ergon_core.api.worker import WorkerContext
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.shared.context_parts import ToolResultPart
from ergon_core.core.persistence.telemetry.models import ThreadMessage, SampleTaskAttempt
from ergon_builtins.benchmarks.manager_gym.actions import ActionResult
from ergon_builtins.benchmarks.manager_gym.scenario_catalog import SCENARIOS
from ergon_builtins.benchmarks.manager_gym.scenarios.stakeholders import create_stakeholder_agent
from ergon_builtins.benchmarks.manager_gym.source_types import (
    AgentConfig,
    AIAgentConfig,
    HumanAgentConfig,
    StakeholderConfig,
    Message,
    MessageType,
    AgentToolUseEvent,
    PreferenceWeights,
    Preference,
    PreferenceWeightUpdateRequest,
    Resource,
    Task,
    TaskStatus,
    Workflow,
)

SOURCE_REVISION = "3f7a5d4af1d31abaedbedd525a0090452926fef4"
BENCHMARK_VERSION = "mag-native-v1"


class EpisodeConfig(BaseModel):
    scenario: str
    manager_mode: Literal["cot", "random", "assign_all"] = "cot"
    seed: int = 0
    max_decisions: int = Field(default=50, ge=1, le=500)
    stakeholder_persona: str = "balanced"
    noop_wait_seconds: float = Field(default=5, ge=0, le=30)
    drain_timeout_seconds: float = Field(default=600, gt=0, le=3600)
    wall_time_seconds: float = Field(default=2400, gt=0, le=2700)
    input_token_price_per_million: float = Field(default=0, ge=0)
    output_token_price_per_million: float = Field(default=0, ge=0)


class ScheduledMessage(BaseModel):
    due: int
    content: str
    key: str


class EpisodeState(BaseModel):
    config: EpisodeConfig
    workflow: Workflow
    actors: dict[str, dict[str, Any]] = Field(default_factory=dict)
    active_actors: list[str] = Field(default_factory=list)
    bindings: dict[str, UUID] = Field(default_factory=dict)
    native_dependencies: dict[str, list[UUID]] = Field(default_factory=dict)
    weights: dict[str, float]
    preference_history: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[ActionResult] = Field(default_factory=list)
    scheduled_messages: list[ScheduledMessage] = Field(default_factory=list)
    message_ticks: dict[str, int] = Field(default_factory=dict)
    tool_usage: dict[UUID, list[AgentToolUseEvent]] = Field(default_factory=dict)
    timestep: int = 0
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stop_requested: bool = False
    infrastructure_errors: list[str] = Field(default_factory=list)


def actor_config(value: dict[str, Any]) -> AgentConfig:
    cls = {"ai": AIAgentConfig, "human_mock": HumanAgentConfig, "stakeholder": StakeholderConfig}[
        value["agent_type"]
    ]
    return cls.model_validate(value)


def all_tasks(workflow: Workflow) -> dict[UUID, Task]:
    tasks: dict[UUID, Task] = {}
    for root in workflow.tasks.values():
        for item in [root, *root.get_all_subtasks_flat()]:
            tasks[item.id] = item
    return tasks


def canonicalize(workflow: Workflow, namespace: UUID) -> None:
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
    actors = {stakeholder.agent_id: stakeholder.model_dump(mode="json")}
    for events in spec.create_team_timeline().values():
        for action, actor, _reason in events:
            if action == "add":
                actors[actor.agent_id] = actor.model_dump(mode="json")
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
    """Source arithmetic, with copy-on-update so future changes cannot mutate history."""
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
    # Upstream PreferenceWeights normalizes even when request.normalize is False.
    return PreferenceWeights(
        preferences=[Preference(name=k, weight=v) for k, v in result.items()]
    ).get_preference_dict()


def apply_timeline(state: EpisodeState) -> None:
    spec = SCENARIOS[state.config.scenario]
    for action, actor, _reason in spec.create_team_timeline().get(state.timestep, []):
        key = actor.agent_id if isinstance(actor, AgentConfig) else str(actor)
        if action == "add" and key not in state.active_actors:
            state.active_actors.append(key)
        elif action == "remove" and key in state.active_actors:
            state.active_actors.remove(key)
    for request in (
        spec.create_preference_update_requests() if spec.create_preference_update_requests else []
    ):
        if request.timestep == state.timestep:
            state.weights = update_weights(state.weights, request)
            state.preference_history.append(
                {"timestep": state.timestep, "weights": dict(state.weights)}
            )


def project_tool_usage(
    session: Session, sample_id: UUID, bindings: dict[str, UUID]
) -> dict[UUID, list[AgentToolUseEvent]]:
    logical_ids = {native: UUID(logical) for logical, native in bindings.items()}
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


async def project_native_state(state: EpisodeState, context: WorkerContext) -> EpisodeState:
    """Capture committed execution state once per durable observation step."""
    state = state.model_copy(deep=True)
    state.observed_at = datetime.now(UTC)
    tasks = all_tasks(state.workflow)
    with context.session_factory() as session:
        for logical, native in state.bindings.items():
            if UUID(logical) not in tasks:
                continue
            task = tasks[UUID(logical)]
            result = context.task_inspect.completion(
                session, sample_id=context.sample_id, task_id=native
            )
            task.status = (
                TaskStatus(result.status)
                if result.status in TaskStatus._value2member_map_
                else TaskStatus.FAILED
            )
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
            if result.status == "failed" and str(native) not in state.infrastructure_errors:
                state.infrastructure_errors.append(str(native))
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
                message_type=MessageType(row.metadata_json.get("message_type", "general"))
                if row.metadata_json.get("message_type", "general")
                in MessageType._value2member_map_
                else MessageType.GENERAL,
                related_task_id=row.metadata_json.get("logical_task_id"),
                timestamp=row.created_at,
                metadata={
                    **row.metadata_json,
                    "timestep": row.metadata_json.get(
                        "timestep", state.message_ticks.get(str(row.id), state.timestep)
                    ),
                },
            )
            for row in rows
        ]
        state.tool_usage = project_tool_usage(session, context.sample_id, state.bindings)
        for msg in state.workflow.messages:
            state.message_ticks.setdefault(str(msg.message_id), state.timestep)
    for task in reversed(list(tasks.values())):
        if task.subtasks:
            leaves = task.get_atomic_subtasks()
            task.status = (
                TaskStatus.COMPLETED
                if all(t.status == TaskStatus.COMPLETED for t in leaves)
                else TaskStatus.PENDING
            )
            task.effective_status = task.status.value
    state.workflow.total_cost = sum(t.actual_cost or 0 for t in tasks.values() if not t.subtasks)
    state.workflow.total_simulated_hours = sum(
        t.actual_duration_hours or 0 for t in tasks.values() if not t.subtasks
    )
    return state


def public_observation(state: EpisodeState) -> dict[str, Any]:
    stakeholder = next(a for a in state.actors.values() if a["agent_type"] == "stakeholder")
    return {
        "timestep": state.timestep,
        "max_timesteps": state.config.max_decisions,
        "timesteps_remaining": max(0, state.config.max_decisions - state.timestep - 1),
        "goal": state.workflow.workflow_goal,
        "stakeholder_profile": {
            "display_name": stakeholder["name"],
            "role": stakeholder["role"],
            "preference_summary": PreferenceWeights.model_validate(
                stakeholder["initial_preferences"]
            ).get_preference_summary(),
        },
        "total_cost": state.workflow.total_cost,
        "total_simulated_hours": state.workflow.total_simulated_hours,
        "tasks": [
            {
                **task.model_dump(mode="json", exclude={"subtasks", "execution_notes"}),
                "is_composite": bool(task.subtasks),
                "child_task_ids": [str(t.id) for t in task.subtasks],
            }
            for task in all_tasks(state.workflow).values()
        ],
        "agents": [
            {
                "id": k,
                "type": state.actors[k]["agent_type"],
                "description": state.actors[k]["agent_description"],
                "capabilities": state.actors[k]["agent_capabilities"],
                "name": state.actors[k].get("name", k),
                "role": state.actors[k].get("role"),
                "hourly_rate": state.actors[k].get("hourly_rate"),
                "max_concurrent_tasks": state.actors[k].get("max_concurrent_tasks"),
                "current_task_ids": [
                    str(t.id)
                    for t in all_tasks(state.workflow).values()
                    if t.assigned_agent_id == k and t.status.value == "running"
                ],
            }
            for k in state.active_actors
        ],
        "constraints": [c.model_dump(mode="json") for c in state.workflow.constraints],
        # Match the source workflow's 300-character resource preview. Full
        # contents stay in native artifacts and the frozen evaluation state.
        "resources": [
            {
                **r.model_dump(mode="json", exclude={"content"}),
                "content": (r.content or "")[:300],
                "content_characters": len(r.content or ""),
            }
            for r in state.workflow.resources.values()
        ],
        "messages": [
            {
                **m.model_dump(mode="json", exclude={"content", "metadata"}),
                "content": m.content[:140],
            }
            for m in sorted(state.workflow.messages, key=lambda m: m.timestamp, reverse=True)[:10]
        ],
        "recent_actions": [
            {**a.model_dump(mode="json", exclude={"data", "summary"}), "summary": a.summary[:120]}
            for a in state.actions[-10:]
        ],
    }


def snapshot_hash(state: EpisodeState) -> str:
    return sha256(
        json.dumps(state.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
