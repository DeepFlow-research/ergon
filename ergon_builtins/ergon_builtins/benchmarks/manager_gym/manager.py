"""MAG manager policy using native durable steps and the WorkerContext task facade."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
import json
import random
from graphlib import TopologicalSorter
from typing import ClassVar, cast
from uuid import UUID, uuid5

from pydantic import BaseModel, Field, field_validator

from ergon_core.api import Task, Worker, WorkerContext, WorkerStreamItem
from ergon_core.core.application.runtime.errors import GraphError
from ergon_core.api.worker import WorkerOutput
from ergon_core.core.application.communication.models import CreateMessageRequest, MessageResponse
from ergon_core.core.application.communication.service import CommunicationService
from ergon_core.core.shared.context_parts import ContextPartChunk, ToolResultPart
from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox
from ergon_builtins.benchmarks.manager_gym.actions import (
    ManagerAction,
    ManagerDecision,
    ActionResult,
    AssignTaskAction,
    CreateTaskAction,
    RemoveTaskAction,
    RefineTaskAction,
    AddTaskDependencyAction,
    RemoveTaskDependencyAction,
    InspectTaskAction,
    DecomposeTaskAction,
    SendMessageAction,
    NoOpAction,
)
from ergon_builtins.benchmarks.manager_gym.inference import infer, InferenceResult
from ergon_builtins.benchmarks.manager_gym.baselines import (
    BaselineInference,
    baseline_infer,
    bulk_infer,
    bulk_assignments,
    random_schema,
)
from ergon_builtins.benchmarks.manager_gym.prompts.manager import (
    STRUCTURED_MANAGER_SYSTEM_PROMPT_TEMPLATE,
)
from ergon_builtins.benchmarks.manager_gym.prompts.decomposition import TASK_DECOMPOSITION_PROMPT
from ergon_builtins.benchmarks.manager_gym.source_types import Task as PlannedTask, TaskStatus
from ergon_builtins.benchmarks.manager_gym.state import (
    EpisodeConfig,
    EpisodeState,
    ScheduledMessage,
    new_episode,
    apply_timeline,
    all_tasks,
    project_native_state,
    public_observation,
    snapshot_hash,
    BENCHMARK_VERSION,
    SOURCE_REVISION,
)
from ergon_builtins.benchmarks.manager_gym.workers import (
    WorkTask,
    WorkPayload,
    MAGWorkWorker,
    MAGHumanWorker,
    MAGStakeholderWorker,
)


class EpisodeTask(Task[EpisodeConfig]):
    pass


class DecomposedSubtask(BaseModel):
    name: str
    executive_summary: str
    implementation_plan: str
    acceptance_criteria: str


class Decomposition(BaseModel):
    reasoning: str
    subtasks: list[DecomposedSubtask] = Field(min_length=3, max_length=6)

    @field_validator("subtasks", mode="before")
    @classmethod
    def decode_subtasks(cls, value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value


def dependency_leaves(state: EpisodeState, planned: PlannedTask) -> list[UUID]:
    tasks = all_tasks(state.workflow)
    dependencies = []
    inherited = list(planned.dependency_task_ids)
    parent = planned.parent_task_id
    while parent:
        inherited.extend(tasks[parent].dependency_task_ids)
        parent = tasks[parent].parent_task_id
    for dep in inherited:
        if dep == planned.id or dep not in tasks:
            raise ValueError("Dependency must identify another existing task")
        source = tasks[dep]
        for leaf in source.get_atomic_subtasks() if source.subtasks else [source]:
            if leaf.id == planned.id:
                raise ValueError("A task cannot depend on its own composite")
            native = state.bindings.get(str(leaf.id))
            if native is None:
                raise ValueError(f"Assign prerequisite {leaf.id} before admitting its dependent")
            dependencies.append(native)
    return list(dict.fromkeys(dependencies))


def work_task(
    state: EpisodeState, planned: PlannedTask, actor: str, model: str, dependencies: list[UUID]
) -> WorkTask:
    config = state.actors[actor]
    cls = {"ai": MAGWorkWorker, "human_mock": MAGHumanWorker, "stakeholder": MAGStakeholderWorker}[
        config["agent_type"]
    ]
    private_config = dict(config)
    if config["agent_type"] == "stakeholder":
        private_config["initial_preferences"] = {
            "preferences": [{"name": k, "weight": v} for k, v in state.weights.items()]
        }
    return WorkTask(
        task_slug=f"mag-work-{planned.id}",
        instance_key="default",
        description=planned.description,
        task_payload=WorkPayload(
            episode=state.config,
            planned_task=planned.model_copy(deep=True),
            actor=private_config,
            resources=[
                state.workflow.resources[key]
                for key in planned.input_resource_ids
                if key in state.workflow.resources
            ],
            dependencies=dependencies,
            permitted_recipients=["manager_agent", *state.active_actors],
            timestep=state.timestep,
        ),
        worker=cls(name=actor, actor_key=actor, model=model),
        sandbox=E2BSandbox(timeout_seconds=3600),
    )


async def assign(
    state: EpisodeState, action: AssignTaskAction, context: WorkerContext, model: str
) -> None:
    planned = all_tasks(state.workflow)[UUID(action.task_id)]
    if planned.subtasks:
        raise ValueError("Assign atomic leaves; a composite is an unbound plan")
    if action.agent_id not in state.active_actors:
        raise ValueError("Agent is not currently available")
    native = state.bindings.get(str(planned.id))
    dependencies = dependency_leaves(state, planned)
    # Reassignment preserves native prerequisites, not an actor queue. Optional
    # enclosing-composition dependencies (e.g. the contract gate) also survive.
    dependencies = list(
        dict.fromkeys([*dependencies, *state.native_dependencies.get(str(planned.id), [])])
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
    state.bindings[str(planned.id)] = native
    state.native_dependencies[str(planned.id)] = dependencies
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
    async def send() -> MessageResponse:
        return await CommunicationService().save_message(
            CreateMessageRequest(
                sample_id=context.sample_id,
                from_agent_id=sender,
                to_agent_id=recipient,
                thread_topic=f"mag:{':'.join(sorted([sender, recipient]))}",
                content=content,
                metadata={"timestep": state.timestep, "message_type": message_type},
                task_attempt_id=context.execution_id,
                idempotency_key=f"{context.execution_id}:{key}:{recipient}",
            )
        )

    receipt = await context.run_step(
        f"message-{key}-{recipient}", send, output_type=MessageResponse
    )
    state.message_ticks[str(receipt.message_id)] = state.timestep


async def stakeholder_tick(state: EpisodeState, context: WorkerContext) -> None:
    """Pinned scripted policy; each send is attributed to the stakeholder actor."""
    key = next(k for k in state.active_actors if state.actors[k]["agent_type"] == "stakeholder")
    actor = state.actors[key]
    due = [m for m in state.scheduled_messages if m.due <= state.timestep]
    state.scheduled_messages = [m for m in state.scheduled_messages if m.due > state.timestep]
    for item in due:
        await save_message(state, context, key, "manager_agent", item.content, item.key)
    rng = random.Random(f"{state.config.seed}:{key}:tick:{state.timestep}")
    # Upstream repeatedly considers the most recent 20 inbound messages: retain
    # that source quirk, rather than silently introducing a read-once inbox.
    inbox = [m for m in reversed(state.workflow.messages) if m.receiver_id == key][:20]
    for index, msg in enumerate(inbox):
        if rng.random() <= actor["clarification_reply_rate"]:
            delay = rng.randint(
                actor["response_latency_steps_min"],
                max(actor["response_latency_steps_min"], actor["response_latency_steps_max"]),
            )
            content = "Thanks for the update. My priorities remain as discussed; please proceed accordingly."
            if actor["verbosity"] > 1:
                content += f"\nRegarding your message: {msg.content[:200]}"
            state.scheduled_messages.append(
                ScheduledMessage(
                    due=state.timestep + delay,
                    content=content,
                    key=f"reply-{state.timestep}-{index}",
                )
            )
    if (
        rng.random() <= actor["push_probability_per_timestep"]
        and rng.random() <= actor["suggestion_rate"]
    ):
        await save_message(
            state,
            context,
            key,
            "manager_agent",
            f"Suggestion from {actor['name']} ({actor['role']}): Please prioritize critical-path tasks and ensure stakeholder review before final delivery.",
            f"push-{state.timestep}",
        )


async def remove_work(
    state: EpisodeState, action: RemoveTaskAction, context: WorkerContext, model: str
) -> list[ContextPartChunk]:
    tasks = all_tasks(state.workflow)
    chunks: list[ContextPartChunk] = []
    planned = tasks[action.task_id]
    affected = [planned, *planned.get_all_subtasks_flat()]
    for item in affected:
        native = state.bindings.get(str(item.id))
        if native:
            status = item.effective_status or item.status.value
            if status not in {"pending", "ready", "cancelled"}:
                raise ValueError("Remove only unstarted work")
    for item in affected:
        native = state.bindings.get(str(item.id))
        if native:
            await context.cancel_task(native)
    if planned.parent_task_id:
        tasks[planned.parent_task_id].remove_subtask(planned.id)
    else:
        del state.workflow.tasks[planned.id]
    return chunks


def patch_description(planned: PlannedTask, action: RefineTaskAction) -> None:
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
    """Validate authored references before asking the native scheduler to bind them."""
    tasks = all_tasks(state.workflow)
    tasks[replacement.id] = replacement
    graph: dict[UUID, set[UUID]] = {}
    for task in tasks.values():
        dependencies = set(task.dependency_task_ids)
        parent = task.parent_task_id
        while parent:
            dependencies.update(tasks[parent].dependency_task_ids)
            parent = tasks[parent].parent_task_id
        if not dependencies.issubset(tasks):
            raise ValueError("Dependency does not identify an existing plan")
        graph[task.id] = dependencies | {t.id for t in task.subtasks}
    TopologicalSorter(graph).prepare()


async def refine_work(
    state: EpisodeState,
    action: RefineTaskAction | AddTaskDependencyAction | RemoveTaskDependencyAction,
    context: WorkerContext,
    model: str,
) -> list[ContextPartChunk]:
    tasks = all_tasks(state.workflow)
    chunks: list[ContextPartChunk] = []
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
    validate_dependencies(state, planned)
    if planned.subtasks and any(
        (str(t.id) in state.bindings for t in planned.get_atomic_subtasks())
    ):
        raise ValueError("Refine a composite before assigning its descendants")
    native = state.bindings.get(str(task_id))
    if native:
        dependencies = dependency_leaves(state, planned)
        old_work_deps = dependency_leaves(state, tasks[task_id])
        dependencies.extend(
            (
                d
                for d in state.native_dependencies[str(task_id)]
                if d not in old_work_deps and d not in dependencies
            )
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
        state.native_dependencies[str(task_id)] = dependencies
    if planned.parent_task_id:
        parent = tasks[planned.parent_task_id]
        parent.subtasks = [planned if t.id == task_id else t for t in parent.subtasks]
    else:
        state.workflow.tasks[task_id] = planned
    return chunks


async def decompose_work(
    state: EpisodeState, action: DecomposeTaskAction, context: WorkerContext, model: str
) -> list[ContextPartChunk]:
    tasks = all_tasks(state.workflow)
    chunks: list[ContextPartChunk] = []
    planned = tasks[action.task_id]
    if planned.subtasks or str(planned.id) in state.bindings:
        raise ValueError("Decompose only an unassigned atomic plan")

    async def decompose() -> InferenceResult:
        return await infer(
            model=model,
            system="Decompose the supplied task into the requested structured plan.",
            prompt=TASK_DECOMPOSITION_PROMPT.format(
                task_name=planned.name, task_description=planned.description
            )
            + f"\n\nWorkflow goal: {state.workflow.workflow_goal}",
            output_type=Decomposition,
            temperature=1,
        )

    result = await context.run_step(
        f"decompose-{state.timestep}", decompose, output_type=InferenceResult
    )
    chunks.extend(result.chunks)
    parsed = Decomposition.model_validate(result.output)
    for index, item in enumerate(parsed.subtasks):
        planned.add_subtask(
            PlannedTask(
                id=uuid5(planned.id, f"decomposition/{index}"),
                name=item.name,
                input_resource_ids=list(planned.input_resource_ids),
                output_resource_ids=list(planned.output_resource_ids),
                description=f"Executive summary: {item.executive_summary}\nImplementation plan: {item.implementation_plan}\nAcceptance criteria: {item.acceptance_criteria}",
            )
        )
    return chunks


async def apply_action(
    state: EpisodeState, action: ManagerAction, context: WorkerContext, model: str
) -> list[ContextPartChunk]:
    tasks = all_tasks(state.workflow)
    chunks = []
    if isinstance(action, AssignTaskAction):
        await assign(state, action, context, model)
    elif isinstance(action, CreateTaskAction):
        task = PlannedTask(
            id=uuid5(state.workflow.id, f"created/{state.timestep}"),
            name=action.name,
            description=action.description,
            estimated_duration_hours=action.estimated_duration_hours,
            estimated_cost=action.estimated_cost,
        )
        state.workflow.tasks[task.id] = task
    elif isinstance(action, RemoveTaskAction):
        chunks.extend(await remove_work(state, action, context, model))
    elif isinstance(
        action, (RefineTaskAction, AddTaskDependencyAction, RemoveTaskDependencyAction)
    ):
        chunks.extend(await refine_work(state, action, context, model))
    elif isinstance(action, DecomposeTaskAction):
        chunks.extend(await decompose_work(state, action, context, model))
    else:
        await communicate_or_wait(state, action, context)
    return chunks


async def communicate_or_wait(
    state: EpisodeState, action: ManagerAction, context: WorkerContext
) -> None:
    if isinstance(action, SendMessageAction):
        recipients = [action.receiver_id] if action.receiver_id else state.active_actors
        if any((r not in state.active_actors for r in recipients)):
            raise ValueError("Recipient is not an available actor")
        for recipient in recipients:
            await save_message(
                state,
                context,
                "manager_agent",
                recipient,
                action.content,
                f"action-{state.timestep}",
                message_type="alert",
            )
    elif isinstance(action, NoOpAction):
        pending = [
            native
            for logical, native in sorted(state.bindings.items())
            if UUID(logical) in all_tasks(state.workflow)
            and all_tasks(state.workflow)[UUID(logical)].effective_status
            in {"running", "pending", "ready"}
        ]
        if pending and state.config.noop_wait_seconds:
            await context.wait_for_task(pending[0], timeout_seconds=state.config.noop_wait_seconds)


def record_action(state: EpisodeState, result: ActionResult) -> ContextPartChunk:
    state.actions.append(result)
    return ContextPartChunk(
        part=ToolResultPart(
            tool_call_id=f"mag-action-{state.timestep}",
            tool_name=result.action_type,
            content=result.model_dump_json(),
            is_error=not result.success,
        )
    )


async def bulk_turn(
    state: EpisodeState, context: WorkerContext, model: str
) -> AsyncGenerator[ContextPartChunk, None]:
    if state.actions:
        await communicate_or_wait(
            state, NoOpAction(reasoning="One-shot mapping already applied"), context
        )
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
    mapping = bulk_assignments(state, decision)
    plans = all_tasks(state.workflow)
    graph = {}
    for task in plans.values():
        dependencies = set(task.dependency_task_ids) | {t.id for t in task.subtasks}
        parent = task.parent_task_id
        while parent:
            dependencies.update(plans[parent].dependency_task_ids)
            parent = plans[parent].parent_task_id
        graph[task.id] = sorted(dependencies)
    failures = []
    assigned = []
    for task_id in TopologicalSorter(graph).static_order():
        if task_id not in mapping:
            continue
        try:
            await assign(
                state,
                AssignTaskAction(
                    reasoning="One-shot bulk mapping",
                    task_id=str(task_id),
                    agent_id=mapping[task_id],
                ),
                context,
                model,
            )
            assigned.append(str(task_id))
        except (ValueError, KeyError, GraphError) as exc:
            failures.append({"task_id": str(task_id), "error": str(exc)})
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


async def policy_turn(
    state: EpisodeState, context: WorkerContext, model: str
) -> AsyncGenerator[ContextPartChunk, None]:
    if state.config.manager_mode == "assign_all":
        async for chunk in bulk_turn(state, context, model):
            yield chunk
        return
    observation = public_observation(state)
    if state.workflow.started_at is None:
        raise ValueError("Episode is missing start time")
    schema = random_schema(state) if state.config.manager_mode == "random" else ManagerDecision
    system = STRUCTURED_MANAGER_SYSTEM_PROMPT_TEMPLATE.format(
        today_date=state.workflow.started_at.strftime("%d.%m.%Y"),
        available_agents=json.dumps(observation["agents"]),
        available_actions=json.dumps(schema.model_json_schema()),
    )
    system += "\nNative scheduling rules: assign prerequisite leaves first, then dependents. Assign only leaf tasks. Actor capacity is informational; only task dependencies constrain execution. Mutate/remove only unstarted work. Queries and invalid actions consume decisions. Noop yields briefly for running work. The episode drains admitted tasks before scoring."

    async def decide() -> BaselineInference:
        if state.config.manager_mode == "random":
            return await baseline_infer(
                model=model, system=system, prompt=json.dumps(observation), output_type=schema
            )
        return BaselineInference(
            result=await infer(
                model=model, system=system, prompt=json.dumps(observation), output_type=schema
            )
        )

    recorded = await context.run_step(
        f"manager-decision-{state.timestep}", decide, output_type=BaselineInference
    )
    decision = recorded.result
    if decision is None:
        yield record_action(
            state,
            ActionResult(
                action_type="failed_action",
                summary="Random baseline model fallback",
                kind="failed_action",
                data={"error": recorded.error},
                timestep=state.timestep,
                success=False,
            ),
        )
        return
    for chunk in decision.chunks:
        yield chunk
    parsed = ManagerDecision.model_validate(decision.output)
    try:
        chunks = await apply_action(state, parsed.action, context, model)
        for chunk in chunks:
            yield chunk
        result = successful_action_result(state, parsed.action)
    except (ValueError, KeyError, GraphError) as exc:
        result = ActionResult(
            action_type=parsed.action.action_type,
            summary=str(exc),
            kind="failed_action",
            data={},
            timestep=state.timestep,
            success=False,
        )
    yield record_action(state, result)


def successful_action_result(state: EpisodeState, action: ManagerAction) -> ActionResult:
    result = ActionResult(
        action_type=action.action_type,
        summary="Applied",
        kind="mutation",
        data={},
        timestep=state.timestep,
    )
    observation = public_observation(state)
    if isinstance(action, InspectTaskAction):
        result.data = all_tasks(state.workflow)[action.task_id].model_dump(mode="json")
        result.kind = "inspection"
    elif action.action_type.startswith("get_"):
        fields = {
            "get_workflow_status": (
                "goal",
                "tasks",
                "constraints",
                "total_cost",
                "total_simulated_hours",
            ),
            "get_available_agents": ("agents",),
            "get_pending_tasks": ("tasks",),
        }[action.action_type]
        result.data = {key: observation[key] for key in fields}
        if action.action_type == "get_pending_tasks":
            result.data["tasks"] = [t for t in observation["tasks"] if t["status"] == "pending"]
        result.kind = "info"
    elif isinstance(action, NoOpAction):
        result.kind = "noop"
    elif isinstance(action, SendMessageAction):
        result.kind = "message"
    return result


class DrainClassification(BaseModel):
    policy_blocked: bool


async def has_cancelled_prerequisite(context: WorkerContext, native: UUID) -> bool:
    """Classify unfinished work from the authoritative graph, without releasing it."""
    pending = [native]
    visited: set[UUID] = set()
    while pending:
        task_id = pending.pop()
        if task_id in visited:
            continue
        visited.add(task_id)
        task = await context.get_task(task_id)
        if task_id != native and task.status in {"cancelled", "blocked"}:
            return True
        pending.extend(task.depends_on)
    return False


async def drain_admitted_work(state: EpisodeState, context: WorkerContext) -> None:
    remaining = state.config.drain_timeout_seconds
    checked_at = state.observed_at.timestamp()
    for _, native in sorted(state.bindings.items()):
        result = await context.wait_for_task(native, timeout_seconds=max(0, remaining))
        remaining -= max(0, result.checked_at - checked_at)
        checked_at = result.checked_at
        if result.timed_out:

            async def classify() -> DrainClassification:
                return DrainClassification(
                    policy_blocked=await has_cancelled_prerequisite(context, native)
                )

            classification = await context.run_step(
                f"drain-blocked-{native}", classify, output_type=DrainClassification
            )
            await context.cancel_task(native, reason="MAG drain deadline")
            if not classification.policy_blocked:
                state.infrastructure_errors.append(f"drain timeout:{native}")


class MAGManagerWorker(Worker):
    type_slug: ClassVar[str] = "manager-gym-manager"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        config = EpisodeConfig.model_validate(task.task_payload.model_dump())

        async def initialize() -> EpisodeState:
            return new_episode(config)

        state = await context.run_step("episode-initialize", initialize, output_type=EpisodeState)
        if state.workflow.started_at is None:
            raise ValueError("Episode is missing its start time")
        started_at = state.workflow.started_at
        for tick in range(config.max_decisions):
            state.timestep = tick
            apply_timeline(state)

            async def observe() -> EpisodeState:
                return await project_native_state(state, context)

            state = await context.run_step(f"observe-{tick}", observe, output_type=EpisodeState)
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
            if state.stop_requested or all(
                t.status == TaskStatus.COMPLETED
                for t in all_tasks(state.workflow).values()
                if not t.subtasks
            ):
                break
        await drain_admitted_work(state, context)

        async def freeze() -> EpisodeState:
            final = await project_native_state(state, context)
            final.workflow.completed_at = datetime.now(UTC)
            final.workflow.is_active = False
            return final

        state = await context.run_step("episode-final-snapshot", freeze, output_type=EpisodeState)
        encoded = state.model_dump_json()
        await task.sandbox.write_file(
            "/workspace/final_output/manager-gym-snapshot.json", encoded.encode()
        )
        yield WorkerOutput(
            output=encoded,
            metadata={
                "benchmark_version": BENCHMARK_VERSION,
                "source_revision": SOURCE_REVISION,
                "snapshot_hash": snapshot_hash(state),
                "decision_count": len(state.actions),
                "native_task_count": len(state.bindings),
                "incomplete": bool(state.infrastructure_errors),
            },
        )
