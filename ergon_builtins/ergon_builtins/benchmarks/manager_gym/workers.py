"""Native MAG work roles, with human state derived from committed Ergon outputs."""

from collections.abc import AsyncGenerator
import json
from dataclasses import dataclass
import random
from typing import Any, ClassVar
from uuid import UUID, uuid5

from pydantic import BaseModel, Field
from sqlmodel import select, col

from ergon_core.api import Task, Worker, WorkerContext, WorkerStreamItem
from ergon_core.api.worker import WorkerOutput
from ergon_core.core.application.communication.models import CreateMessageRequest
from ergon_core.core.application.communication.service import CommunicationService
from ergon_core.core.persistence.telemetry.models import SampleTaskAttempt, ThreadMessage
from ergon_builtins.benchmarks.manager_gym.communication import MAGCommunication
from ergon_builtins.benchmarks.manager_gym.inference import infer, InferenceResult
from ergon_builtins.benchmarks.manager_gym.outputs import (
    AITaskOutput,
    HumanWorkOutput,
    HumanTimeEstimation,
)
from ergon_builtins.benchmarks.manager_gym.prompts.ai_agent_prompts import AI_AGENT_TASK_TEMPLATE
from ergon_builtins.benchmarks.manager_gym.prompts.human_agent_prompts import (
    HUMAN_TASK_ASSIGNMENT_TEMPLATE,
    HUMAN_SIMULATION_INSTRUCTIONS_TEMPLATE,
)
from ergon_builtins.benchmarks.manager_gym.source_types import (
    Task as PlannedTask,
    Resource,
    HumanAgentConfig,
)
from ergon_builtins.benchmarks.manager_gym.state import EpisodeConfig, actor_config


class WorkPayload(BaseModel):
    episode: EpisodeConfig
    planned_task: PlannedTask
    actor: dict[str, Any]
    resources: list[Resource] = Field(default_factory=list)
    dependencies: list[UUID] = Field(default_factory=list)
    permitted_recipients: list[str] = Field(default_factory=list)
    timestep: int = 0


class WorkTask(Task[WorkPayload]):
    pass


class WorkInputs(BaseModel):
    resources: list[Resource]
    hours_worked: float = 0
    completed_tasks: int = 0
    prior_attempt_ids: list[UUID] = Field(default_factory=list)
    inbox: list[dict[str, Any]] = Field(default_factory=list)


class WorkResult(BaseModel):
    inference: InferenceResult
    estimator: InferenceResult | None = None
    resources: list[Resource]
    simulated_hours: float
    simulated_cost: float
    fatigue: float = 0
    accounted_hours: float = 0
    prior_hours: float = 0
    prior_attempt_ids: list[UUID] = Field(default_factory=list)
    quality_modifier: float | None = None
    speed_modifier: float | None = None
    misunderstanding: bool = False
    execution_notes: list[str] = Field(default_factory=list)


async def read_inputs(payload: WorkPayload, context: WorkerContext) -> WorkInputs:
    resources = {r.id: r for r in payload.resources}
    hours, count = 0.0, 0
    prior_attempt_ids = []
    with context.session_factory() as session:
        for task_id in payload.dependencies:
            result = context.task_inspect.completion(
                session, sample_id=context.sample_id, task_id=task_id
            )
            if result.status != "completed" or result.output is None:
                raise RuntimeError(f"Native prerequisite {task_id} has no completed output")
            for raw in result.output.metadata.get("resources", []):
                r = Resource.model_validate(raw)
                resources[r.id] = r
        # Capture committed prior work once. Concurrent invocations may see the
        # same history; only authored native prerequisites impose ordering.
        rows = session.exec(
            select(SampleTaskAttempt).where(
                SampleTaskAttempt.sample_id == context.sample_id,
                SampleTaskAttempt.status == "completed",
            )
        ).all()
        for row in rows:
            if row.worker_output_json:
                metadata = row.worker_output_json.get("metadata", {})
                if metadata.get("actor_key") == payload.actor["agent_id"]:
                    prior_attempt_ids.append(row.id)
                    hours += float(metadata.get("accounted_hours", 0))
                    count += int(not metadata.get("misunderstanding", False))
        messages = session.exec(
            select(ThreadMessage)
            .where(
                ThreadMessage.sample_id == context.sample_id,
                ThreadMessage.to_agent_id == payload.actor["agent_id"],
            )
            .order_by(col(ThreadMessage.created_at), col(ThreadMessage.id))
        ).all()
        inbox = [{"from": m.from_agent_id, "content": m.content, "id": str(m.id)} for m in messages]
    return WorkInputs(
        resources=list(resources.values()),
        hours_worked=hours,
        completed_tasks=count,
        inbox=inbox,
        prior_attempt_ids=sorted(prior_attempt_ids),
    )


@dataclass
class HumanPreparation:
    system: str
    prompt: str
    fatigue: float
    quality: float
    speed: float
    misunderstood: bool
    hours: float
    estimator: InferenceResult | None


class MAGWorkWorker(Worker):
    type_slug: ClassVar[str] = "manager-gym-work"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem, None]:
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
                f"/workspace/final_output/{resource.id}.txt", (resource.content or "").encode()
            )
        metadata = result.model_dump(mode="json", exclude={"inference", "estimator"})
        metadata.update(
            actor_key=self.binding_key,
            role=payload.actor["agent_type"],
            logical_task_id=str(payload.planned_task.id),
            model=self.model,
            input_tokens=result.inference.input_tokens
            + (result.estimator.input_tokens if result.estimator else 0),
            output_tokens=result.inference.output_tokens
            + (result.estimator.output_tokens if result.estimator else 0),
        )
        yield WorkerOutput(output=json.dumps(result.inference.output), metadata=metadata)

    async def _prepare_human(
        self, payload: WorkPayload, inputs: WorkInputs, actor: HumanAgentConfig, resources_text: str
    ) -> HumanPreparation:
        planned = payload.planned_task
        estimator = None
        rng = random.Random(f"{payload.episode.seed}:{actor.agent_id}:{planned.id}")
        fatigue = min(inputs.hours_worked * actor.fatigue_rate, 0.5)
        quality = max(0, min(1, rng.gauss(actor.base_quality_mean, 0.1) - fatigue))
        speed = max(0.1, rng.gauss(1, 0.2))
        misunderstood = rng.random() < actor.misunderstanding_rate
        system = actor.generate_roleplay_prompt() + HUMAN_SIMULATION_INSTRUCTIONS_TEMPLATE.format(
            persona_name=actor.name,
            experience_years=actor.experience_years,
            work_style=actor.work_style,
            expertise_areas=", ".join(actor.expertise_areas),
        )
        hours = planned.estimated_duration_hours or 0
        if not hours:
            estimator = await infer(
                model=self.model,
                system=f"You are {actor.role}, with {actor.experience_years} years of experience. Estimate realistic hours including research, review, breaks and obstacles. Background: {actor.background}; expertise: {actor.expertise_areas}; style: {actor.work_style}.",
                prompt=planned.description,
                output_type=HumanTimeEstimation,
            )
            hours = max(0.1, HumanTimeEstimation.model_validate(estimator.output).estimated_hours)
        if not misunderstood:
            hours *= speed
        prompt = HUMAN_TASK_ASSIGNMENT_TEMPLATE.format(
            persona_name=actor.name,
            task_name=planned.name,
            task_description=planned.description,
            resources_list=resources_text,
            time_constraints="",
            dependencies="",
        )
        if quality < 0.7:
            prompt += "\n(Note: You're feeling a bit tired/stressed today.)"
        prompt += f"\nApply your {actor.work_style} work style and {actor.experience_years} years of experience."
        if misunderstood:
            prompt += "\nYou slightly misunderstand one important requirement in a realistic, plausible way. Proceed confidently without flagging confusion; produce a complete work product consistent with that misunderstanding."
        return HumanPreparation(
            system, prompt, fatigue, quality, speed, misunderstood, hours, estimator
        )

    async def _work(
        self, payload: WorkPayload, inputs: WorkInputs, context: WorkerContext
    ) -> WorkResult:
        actor = actor_config(payload.actor)
        planned = payload.planned_task
        resources_text = (
            "\n\n".join(
                f"{r.name}: {r.description}\n{(r.content or '')[:200]}"
                + ("..." if len(r.content or "") > 200 else "")
                for r in inputs.resources
            )
            or "No specific input resources provided"
        )
        prompt = AI_AGENT_TASK_TEMPLATE.format(
            task_name=planned.name,
            task_description=planned.description,
            input_resources=resources_text,
        )
        system = actor.system_prompt
        output_type = AITaskOutput
        fatigue = 0.0
        quality = None
        speed = None
        misunderstood = False
        hours = 0.0
        estimator = None
        if isinstance(actor, HumanAgentConfig):
            prepared = await self._prepare_human(payload, inputs, actor, resources_text)
            system, prompt = prepared.system, prepared.prompt
            fatigue, quality, speed = prepared.fatigue, prepared.quality, prepared.speed
            misunderstood, hours, estimator = (
                prepared.misunderstood,
                prepared.hours,
                prepared.estimator,
            )
            output_type = HumanWorkOutput
        if actor.agent_type == "stakeholder":
            system += f"\nReview and approval persona: {payload.actor['persona_description']}; strictness {payload.actor['strictness']}. Private priorities: {payload.actor['initial_preferences']}"
        prompt += (
            "\nManager instructions:\n"
            + "\n".join(planned.execution_notes)
            + "\nInbox:\n"
            + json.dumps(inputs.inbox)
        )
        inference = await infer(
            model=self.model,
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
            temperature=0.7 if isinstance(actor, HumanAgentConfig) else 0,
        )
        output = output_type.model_validate(inference.output)
        resources = output.resources
        if not resources:
            if actor.agent_type != "ai":
                raise ValueError("Human/stakeholder generated no resources")
            resources = [
                Resource(
                    name=f"Completed: {planned.name}",
                    description=planned.description,
                    content=json.dumps(inference.output),
                )
            ]
        for index, resource in enumerate(resources):
            resource.id = uuid5(planned.id, f"output/{index}")
        if isinstance(actor, HumanAgentConfig):
            cost = hours * actor.hourly_rate
            human_output = HumanWorkOutput.model_validate(inference.output)
            notes = [human_output.work_process, human_output.quality_notes]
            if misunderstood:
                notes = [
                    "Task execution under a subtle misunderstanding of requirements",
                    "Output may be misaligned with the original intent",
                ]
        else:
            hours = inference.elapsed_seconds / 3600
            cost = (
                inference.input_tokens * payload.episode.input_token_price_per_million
                + inference.output_tokens * payload.episode.output_token_price_per_million
            ) / 1e6
            notes = AITaskOutput.model_validate(inference.output).execution_notes
        return WorkResult(
            inference=inference,
            estimator=estimator,
            resources=resources,
            simulated_hours=hours,
            simulated_cost=cost,
            fatigue=fatigue,
            accounted_hours=hours
            if isinstance(actor, HumanAgentConfig) and not misunderstood
            else 0,
            prior_hours=inputs.hours_worked,
            prior_attempt_ids=inputs.prior_attempt_ids,
            quality_modifier=quality,
            speed_modifier=speed,
            misunderstanding=misunderstood,
            execution_notes=notes,
        )


class MAGHumanWorker(MAGWorkWorker):
    type_slug: ClassVar[str] = "manager-gym-human"


class MAGStakeholderWorker(MAGWorkWorker):
    type_slug: ClassVar[str] = "manager-gym-stakeholder"
