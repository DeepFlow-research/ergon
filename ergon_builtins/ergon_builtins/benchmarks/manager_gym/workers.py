"""Work roles: AI workers, simulated humans and the stakeholder.

Each assigned task runs as a native Ergon task whose worker plays one team
member. Simulated humans follow upstream MAG's noise model (fatigue, Gaussian
quality and speed, misunderstandings, hourly cost), with their workload read
from the attempts they already completed in this sample.
"""

import json
import random
from collections.abc import AsyncGenerator, Sequence
from typing import Any, ClassVar
from uuid import UUID, uuid5

from ergon_core.api import Task, Worker, WorkerContext, WorkerStreamItem
from ergon_core.api.worker import WorkerOutput
from ergon_core.core.application.runtime import status as graph_status
from ergon_core.core.persistence.telemetry.models import SampleTaskAttempt
from pydantic import BaseModel, Field
from sqlmodel import select

from ergon_builtins.benchmarks.manager_gym.communication import MAGCommunication
from ergon_builtins.benchmarks.manager_gym.constants import OUTPUT_DIR
from ergon_builtins.benchmarks.manager_gym.inference import (
    InferenceResult,
    ModelFailure,
    Role,
    infer,
)
from ergon_builtins.benchmarks.manager_gym.outputs import (
    AITaskOutput,
    HumanTimeEstimation,
    HumanWorkOutput,
    ResourceDraft,
)
from ergon_builtins.benchmarks.manager_gym.prompts import (
    FALLBACK_RESOURCE_NAME,
    HUMAN_ESTIMATOR_SYSTEM_PROMPT,
    HUMAN_MISUNDERSTANDING_EXECUTION_NOTES,
    HUMAN_MISUNDERSTANDING_NOTE,
    HUMAN_TIRED_NOTE,
    HUMAN_WORK_STYLE_NOTE,
    NO_INPUT_RESOURCES,
    STAKEHOLDER_WORK_PERSONA,
)
from ergon_builtins.benchmarks.manager_gym.state import Actor, EpisodeConfig
from ergon_builtins.benchmarks.manager_gym.upstream import (
    AI_AGENT_TASK_TEMPLATE,
    HUMAN_SIMULATION_INSTRUCTIONS_TEMPLATE,
    HUMAN_TASK_ASSIGNMENT_TEMPLATE,
    AgentConfig,
    AIAgentConfig,
    HumanAgentConfig,
    Resource,
    StakeholderConfig,
)
from ergon_builtins.benchmarks.manager_gym.upstream import Task as PlannedTask

# Upstream parity: HumanAgent's noise model (core/workflow_agents/human_agent.py).
MAX_FATIGUE = 0.5
QUALITY_STDDEV = 0.1
SPEED_STDDEV = 0.2
MIN_SPEED = 0.1
MIN_ESTIMATED_HOURS = 0.1
TIRED_BELOW_QUALITY = 0.7

# Upstream parity: characters of each input resource shown to a worker.
INPUT_RESOURCE_PREVIEW_CHARS = 200


class WorkPayload(BaseModel):
    """Everything a work task needs, frozen when the manager assigns it."""

    episode: EpisodeConfig
    planned_task: PlannedTask
    actor: Actor
    current_weights: dict[str, float] = Field(
        default_factory=dict,
        description="The stakeholder's current private preference weights; empty for other roles.",
    )
    resources: list[Resource] = Field(default_factory=list)
    dependencies: list[UUID] = Field(default_factory=list)
    permitted_recipients: list[str] = Field(default_factory=list)
    timestep: int = 0


class WorkTask(Task[WorkPayload]):
    """A planned task assigned to one team member."""


class WorkInputs(BaseModel):
    """What a worker reads from committed native records when it starts."""

    resources: list[Resource]
    hours_worked: float = 0.0
    prior_attempt_ids: list[UUID] = Field(default_factory=list)


class WorkResult(BaseModel):
    """The checkpointed outcome of one work role invocation."""

    inference: InferenceResult
    estimator: InferenceResult | None = None
    resources: list[Resource]
    simulated_hours: float
    simulated_cost: float
    fatigue: float = 0.0
    accounted_hours: float = 0.0
    prior_hours: float = 0.0
    prior_attempt_ids: list[UUID] = Field(default_factory=list)
    quality_modifier: float | None = None
    speed_modifier: float | None = None
    misunderstanding: bool = False
    execution_notes: list[str] = Field(default_factory=list)


class HumanDraws(BaseModel):
    """One task's noise for a simulated human, drawn from a seeded RNG."""

    fatigue: float
    quality: float
    speed: float
    misunderstood: bool

    def result_fields(self) -> dict[str, Any]:
        """The draws as ``WorkResult`` fields."""
        return {
            "fatigue": self.fatigue,
            "quality_modifier": self.quality,
            "speed_modifier": self.speed,
            "misunderstanding": self.misunderstood,
        }


def work_role(actor: AgentConfig) -> Role:
    """The inference role an actor's work runs under."""
    if isinstance(actor, HumanAgentConfig):
        return "human"
    if isinstance(actor, StakeholderConfig):
        return "stakeholder"
    return "ai"


async def read_inputs(payload: WorkPayload, context: WorkerContext) -> WorkInputs:
    """Collect prerequisite outputs and this actor's completed workload.

    Called once in a durable step. Concurrent invocations for one actor may see
    the same history; only authored prerequisites order work.
    """
    resources = {r.id: r for r in payload.resources}
    hours = 0.0
    prior_attempt_ids = []
    with context.session_factory() as session:
        for task_id in payload.dependencies:
            result = context.task_inspect.completion(
                session, sample_id=context.sample_id, task_id=task_id
            )
            if result.status != graph_status.COMPLETED or result.output is None:
                raise RuntimeError(f"Native prerequisite {task_id} has no completed output")
            for raw in result.output.metadata.get("resources", []):
                resource = Resource.model_validate(raw)
                resources[resource.id] = resource
        rows = session.exec(
            select(SampleTaskAttempt).where(
                SampleTaskAttempt.sample_id == context.sample_id,
                SampleTaskAttempt.status == graph_status.COMPLETED,
            )
        ).all()
        for row in rows:
            if row.worker_output_json:
                metadata = row.worker_output_json.get("metadata", {})
                if metadata.get("actor_key") == payload.actor.agent_id:
                    prior_attempt_ids.append(row.id)
                    hours += float(metadata.get("accounted_hours", 0))
    return WorkInputs(
        resources=list(resources.values()),
        hours_worked=hours,
        prior_attempt_ids=sorted(prior_attempt_ids),
    )


def format_input_resources(resources: Sequence[Resource]) -> str:
    """Render input resources for a worker prompt, previewing long contents."""
    return (
        "\n\n".join(
            f"{r.name}: {r.description}\n{(r.content or '')[:INPUT_RESOURCE_PREVIEW_CHARS]}"
            + ("..." if len(r.content or "") > INPUT_RESOURCE_PREVIEW_CHARS else "")
            for r in resources
        )
        or NO_INPUT_RESOURCES
    )


def draw_human_noise(
    payload: WorkPayload, inputs: WorkInputs, actor: HumanAgentConfig
) -> HumanDraws:
    """Draw fatigue, quality, speed and misunderstanding for one human task."""
    rng = random.Random(f"{payload.episode.seed}:{actor.agent_id}:{payload.planned_task.id}")
    fatigue = min(inputs.hours_worked * actor.fatigue_rate, MAX_FATIGUE)
    quality = max(0, min(1, rng.gauss(actor.base_quality_mean, QUALITY_STDDEV) - fatigue))
    speed = max(MIN_SPEED, rng.gauss(1, SPEED_STDDEV))
    misunderstood = rng.random() < actor.misunderstanding_rate
    return HumanDraws(fatigue=fatigue, quality=quality, speed=speed, misunderstood=misunderstood)


def human_system_prompt(actor: HumanAgentConfig) -> str:
    """Upstream's roleplay prompt and simulation instructions for a human."""
    return actor.generate_roleplay_prompt() + HUMAN_SIMULATION_INSTRUCTIONS_TEMPLATE.format(
        persona_name=actor.name,
        experience_years=actor.experience_years,
        work_style=actor.work_style,
        expertise_areas=", ".join(actor.expertise_areas),
    )


def human_task_prompt(
    planned: PlannedTask, actor: HumanAgentConfig, draws: HumanDraws, resources_text: str
) -> str:
    """The task assignment a human sees, with notes for fatigue and misunderstanding."""
    prompt = HUMAN_TASK_ASSIGNMENT_TEMPLATE.format(
        persona_name=actor.name,
        task_name=planned.name,
        task_description=planned.description,
        resources_list=resources_text,
        time_constraints="",
        dependencies="",
    )
    if draws.quality < TIRED_BELOW_QUALITY:
        prompt += HUMAN_TIRED_NOTE
    prompt += HUMAN_WORK_STYLE_NOTE.format(
        work_style=actor.work_style, experience_years=actor.experience_years
    )
    if draws.misunderstood:
        prompt += HUMAN_MISUNDERSTANDING_NOTE
    return prompt


def stakeholder_persona(actor: StakeholderConfig, weights: dict[str, float]) -> str:
    """Persona and current private priorities appended to the stakeholder's prompt."""
    priorities = {"preferences": [{"name": k, "weight": v} for k, v in weights.items()]}
    return STAKEHOLDER_WORK_PERSONA.format(
        persona_description=actor.persona_description,
        strictness=actor.strictness,
        priorities=priorities,
    )


def _output_resources(
    planned: PlannedTask, inference: InferenceResult, drafts: Sequence[ResourceDraft]
) -> list[Resource]:
    """Give drafts deterministic ids; an empty answer becomes one fallback resource."""
    resources = [
        Resource(id=uuid5(planned.id, f"output/{index}"), **draft.model_dump())
        for index, draft in enumerate(drafts)
    ]
    if resources:
        return resources
    return [
        Resource(
            id=uuid5(planned.id, "output/0"),
            name=FALLBACK_RESOURCE_NAME.format(task_name=planned.name),
            description=planned.description,
            content=json.dumps(inference.output),
        )
    ]


class MAGWorkWorker(Worker):
    """Performs one planned task as the team member named by ``actor_key``.

    Behaviour follows the actor in the payload. ``MAGHumanWorker`` and
    ``MAGStakeholderWorker`` differ only in ``type_slug``, so each role's attempts
    are labelled separately in Ergon's records.
    """

    type_slug: ClassVar[str] = "manager-gym-work"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem]:
        payload = WorkPayload.model_validate(task.task_payload.model_dump())

        async def capture() -> WorkInputs:
            return await read_inputs(payload, context)

        inputs = await context.run_step("work-inputs", capture, output_type=WorkInputs)

        async def work() -> WorkResult:
            return await self._work(payload, inputs, context)

        result = await context.run_step("role-work", work, output_type=WorkResult)
        if result.estimator:
            for chunk in result.estimator.chunks:
                yield chunk
        for chunk in result.inference.chunks:
            yield chunk
        for resource in result.resources:
            # UUID file names avoid treating model-authored names as filesystem paths.
            await task.sandbox.write_file(
                f"{OUTPUT_DIR}/{resource.id}.txt", (resource.content or "").encode()
            )
        yield self._output(payload, result)

    def _output(self, payload: WorkPayload, result: WorkResult) -> WorkerOutput:
        metadata = result.model_dump(mode="json", exclude={"inference", "estimator"})
        metadata.update(
            actor_key=self.binding_key,
            role=payload.actor.agent_type,
            logical_task_id=str(payload.planned_task.id),
            model=self.model,
            input_tokens=result.inference.input_tokens
            + (result.estimator.input_tokens if result.estimator else 0),
            output_tokens=result.inference.output_tokens
            + (result.estimator.output_tokens if result.estimator else 0),
        )
        failure = result.inference.failure
        if failure:
            metadata["model_failure"] = failure.model_dump(mode="json")
        return WorkerOutput(
            output=json.dumps(result.inference.output) if failure is None else failure.message,
            success=failure is None,
            metadata=metadata,
        )

    async def _human_hours(
        self, payload: WorkPayload, actor: HumanAgentConfig, draws: HumanDraws
    ) -> tuple[float, InferenceResult | None]:
        """Simulated hours for a human task, asking the model when the plan has none."""
        planned = payload.planned_task
        hours = planned.estimated_duration_hours or 0
        estimator = None
        if not hours:
            estimator = await infer(
                model=self.model,
                role="estimator",
                profile=payload.episode.inference,
                system=HUMAN_ESTIMATOR_SYSTEM_PROMPT.format(
                    role=actor.role,
                    experience_years=actor.experience_years,
                    background=actor.background,
                    expertise_areas=actor.expertise_areas,
                    work_style=actor.work_style,
                ),
                prompt=planned.description,
                output_type=HumanTimeEstimation,
            )
            estimated = HumanTimeEstimation.model_validate(estimator.output).estimated_hours
            hours = max(MIN_ESTIMATED_HOURS, estimated)
        if not draws.misunderstood:
            hours *= draws.speed
        return hours, estimator

    async def _work(
        self, payload: WorkPayload, inputs: WorkInputs, context: WorkerContext
    ) -> WorkResult:
        actor = payload.actor
        planned = payload.planned_task
        resources_text = format_input_resources(inputs.resources)
        draws, estimator, hours = None, None, 0.0
        output_type: type[AITaskOutput | HumanWorkOutput]
        if isinstance(actor, HumanAgentConfig):
            draws = draw_human_noise(payload, inputs, actor)
            hours, estimator = await self._human_hours(payload, actor, draws)
            system = human_system_prompt(actor)
            prompt = human_task_prompt(planned, actor, draws, resources_text)
            output_type = HumanWorkOutput
        else:
            system = actor.system_prompt
            if isinstance(actor, StakeholderConfig):
                system += stakeholder_persona(actor, payload.current_weights)
            prompt = AI_AGENT_TASK_TEMPLATE.format(
                task_name=planned.name,
                task_description=planned.description,
                input_resources=resources_text,
            )
            output_type = AITaskOutput
        inference = await infer(
            model=self.model,
            role=work_role(actor),
            profile=payload.episode.inference,
            system=system,
            prompt=prompt,
            output_type=output_type,
            tools=MAGCommunication(
                context=context,
                actor=actor.agent_id,
                recipients=payload.permitted_recipients,
                logical_task=str(planned.id),
                timestep=payload.timestep,
            ).tools(),
            accept_model_failure=True,
        )
        # Upstream parity: humans and the stakeholder fail without a work product;
        # an AI worker falls back to a resource holding its raw answer.
        if (
            inference.failure is None
            and not isinstance(actor, AIAgentConfig)
            and not output_type.model_validate(inference.output).resources
        ):
            inference = inference.model_copy(
                update={
                    "failure": ModelFailure(
                        kind="output_validation", message="Human/stakeholder generated no resources"
                    )
                }
            )
        result = WorkResult(
            inference=inference,
            estimator=estimator,
            resources=[],
            simulated_hours=0,
            simulated_cost=0,
            prior_hours=inputs.hours_worked,
            prior_attempt_ids=inputs.prior_attempt_ids,
            **(draws.result_fields() if draws else {}),
        )
        if inference.failure:
            notes = [f"Task model failed: {inference.failure.message}"]
            return result.model_copy(update={"execution_notes": notes})
        output = output_type.model_validate(inference.output)
        resources = _output_resources(planned, inference, output.resources)
        if draws is not None and isinstance(actor, HumanAgentConfig):
            human_output = HumanWorkOutput.model_validate(inference.output)
            return result.model_copy(
                update={
                    "resources": resources,
                    "simulated_hours": hours,
                    "simulated_cost": hours * actor.hourly_rate,
                    "accounted_hours": 0 if draws.misunderstood else hours,
                    "execution_notes": list(HUMAN_MISUNDERSTANDING_EXECUTION_NOTES)
                    if draws.misunderstood
                    else [human_output.work_process, human_output.quality_notes],
                }
            )
        episode = payload.episode
        cost = (
            inference.input_tokens * episode.input_token_price_per_million
            + inference.output_tokens * episode.output_token_price_per_million
        ) / 1e6
        return result.model_copy(
            update={
                "resources": resources,
                "simulated_hours": inference.elapsed_seconds / 3600,
                "simulated_cost": cost,
                "execution_notes": AITaskOutput.model_validate(inference.output).execution_notes,
            }
        )


class MAGHumanWorker(MAGWorkWorker):
    """A simulated human team member."""

    type_slug: ClassVar[str] = "manager-gym-human"


class MAGStakeholderWorker(MAGWorkWorker):
    """The stakeholder, when the manager assigns it review or approval work."""

    type_slug: ClassVar[str] = "manager-gym-stakeholder"
