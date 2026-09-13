"""Native criteria over one frozen terminal snapshot, retaining MAG utility arithmetic."""

from collections import defaultdict
from collections.abc import Iterable
import inspect
import json
import math
from typing import Any, ClassVar, Literal, cast

from pydantic import BaseModel, Field

from ergon_core.api import Task
from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome
from ergon_core.api.criterion.score import ScoreScale
from ergon_core.api.rubric import Evaluator
from ergon_core.api.rubric.results import TaskEvaluationResult
from ergon_builtins.benchmarks.manager_gym.definitions.common_evaluators import (
    build_default_evaluators,
)
from ergon_builtins.benchmarks.manager_gym.definitions.scenario_constraints import (
    build_constraints_for_scenario,
)
from ergon_builtins.benchmarks.manager_gym.inference import infer, model_settings
from ergon_builtins.benchmarks.manager_gym.scenario_catalog import SCENARIOS
from ergon_builtins.benchmarks.manager_gym.source_types import (
    Workflow,
    WorkflowRubric,
    RunCondition,
    ValidationContext,
    SenderMessagesView,
    ThreadMessagesView,
    PreferenceWeights,
    Preference,
    AgentPublicState,
)
from ergon_builtins.benchmarks.manager_gym.state import (
    EpisodeState,
    all_tasks,
    actor_config,
    snapshot_hash,
)
from ergon_builtins.benchmarks.manager_gym.prompts.judge import judge_prompt


class RubricDefinition(BaseModel):
    slug: str
    owner: str
    kind: Literal["preference", "diagnostic"]
    rubric: WorkflowRubric


def definitions(scenario: str, *, terminal_only: bool = True) -> list[RubricDefinition]:
    spec = SCENARIOS[scenario]
    owners = [
        ("preference", p.name, p.evaluator)
        for p in spec.create_preferences().preferences
        if p.evaluator
    ]
    diagnostics = build_default_evaluators(None)
    if spec.create_evaluator_to_measure_goal_achievement:
        diagnostics.append(spec.create_evaluator_to_measure_goal_achievement())
    constraint = build_constraints_for_scenario(scenario)
    if constraint:
        diagnostics.append(constraint)
    owners.extend(("diagnostic", e.name, e) for e in diagnostics)
    result = []
    for index, (kind, owner, evaluator) in enumerate(owners):
        for ordinal, rubric in enumerate(evaluator.rubrics):
            if (
                terminal_only
                and kind != "diagnostic"
                and rubric.run_condition != RunCondition.ON_COMPLETION
            ):
                continue
            result.append(
                RubricDefinition(
                    slug=f"{scenario}/{kind}/{index:02d}/{ordinal:02d}",
                    owner=owner,
                    kind=cast(Literal["preference", "diagnostic"], kind),
                    rubric=rubric,
                )
            )
    return result


def _group_senders(workflow: Workflow) -> list[SenderMessagesView]:
    groups = defaultdict(list)
    for m in workflow.messages:
        groups[m.sender_id].append(m)
    return [
        SenderMessagesView(
            sender_id=k,
            total_messages=len(messages),
            most_recent_at=max((m.timestamp for m in messages)),
            messages=messages,
        )
        for k, messages in groups.items()
    ]


def _group_threads(workflow: Workflow) -> list[ThreadMessagesView]:
    threads = defaultdict(list)
    for m in workflow.messages:
        threads[m.thread_id].append(m)
    return [
        ThreadMessagesView(
            thread_id=k,
            total_messages=len(messages),
            last_activity=max((m.timestamp for m in messages)),
            messages=messages,
        )
        for k, messages in threads.items()
    ]


def validation_context(state: EpisodeState, rubric: WorkflowRubric) -> ValidationContext:
    workflow = state.workflow.model_copy(deep=True)
    if workflow.started_at is None:
        raise ValueError("Frozen workflow has no start time")
    workflow.agents = {key: actor_config(state.actors[key]) for key in state.active_actors}
    current = PreferenceWeights(
        preferences=[Preference(name=k, weight=v) for k, v in state.weights.items()]
    )
    context = ValidationContext(
        workflow=workflow, current_preferences=current, timestep=state.timestep
    )
    required = {item.value for item in rubric.required_context}
    if "manager_actions" in required:
        context.manager_actions = state.actions
    if "preference_history" in required:
        context.preference_history = state.preference_history
    if "communications_by_sender" in required:
        context.communications_by_sender = _group_senders(workflow)
    if "communications_by_thread" in required:
        context.communications_by_thread = _group_threads(workflow)
    if "resources_by_task" in required:
        context.resources_by_task = {
            k: workflow.get_task_output_resources(t) for k, t in all_tasks(workflow).items()
        }
        context.all_resources = workflow.get_all_resources()
    if "stakeholder_profile" in required:
        context.stakeholder_profile = next(
            (v for v in state.actors.values() if v["agent_type"] == "stakeholder")
        )
    if "agent_public_states" in required:
        context.agent_public_states = {
            k: AgentPublicState(
                agent_id=k,
                agent_type=state.actors[k]["agent_type"],
                is_available=not any(
                    t.assigned_agent_id == k and t.status.value == "running"
                    for t in all_tasks(workflow).values()
                ),
                tasks_completed=sum(
                    t.assigned_agent_id == k and t.status.value == "completed" and not t.subtasks
                    for t in all_tasks(workflow).values()
                ),
                joined_at=workflow.started_at,
                current_task_ids=[
                    t.id
                    for t in all_tasks(workflow).values()
                    if t.assigned_agent_id == k and t.status.value == "running"
                ],
            )
            for k in state.active_actors
        }
    if "agent_tool_usage_by_task" in required:
        context.agent_tool_usage_by_task = state.tool_usage
    return context


class JudgeOutput(BaseModel):
    score: float | bool | Literal["low", "medium", "high"]
    reasoning: str
    confidence: float = Field(ge=0, le=1)


def normalize_score(value: Any, maximum: float, *, llm: bool) -> tuple[float, str]:
    reasoning = ""
    if isinstance(value, tuple):
        if len(value) == 2:
            value, reasoning = value
        elif len(value) == 1:
            value = value[0]
        else:
            return 0, "Invalid tuple shape for score"
    if llm and isinstance(value, bool):
        score = maximum if value else 0
    elif llm and isinstance(value, str) and value in {"low", "medium", "high"}:
        score = maximum * {"low": 0.33, "medium": 0.66, "high": 1}[value]
    else:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0, "Normalization failed"
    if not math.isfinite(score):
        raise ValueError("Non-finite rubric score")
    return max(0, min(maximum, score)), str(reasoning)


class MAGCriterion(Criterion):
    type_slug: ClassVar[str] = "manager-gym-criterion"
    scenario: str
    model: str

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        state = EpisodeState.model_validate_json(context.worker_result.output)
        if state.infrastructure_errors or context.worker_result.metadata.get("incomplete"):
            raise RuntimeError("MAG episode is incomplete: " + str(state.infrastructure_errors))
        digest = snapshot_hash(state)
        if digest != context.worker_result.metadata["snapshot_hash"]:
            raise ValueError("Frozen MAG snapshot digest mismatch")
        definition = next(d for d in definitions(self.scenario) if d.slug == self.slug)
        rubric = definition.rubric
        validation = validation_context(state, rubric)
        evaluation_input = None
        usage = None
        if rubric.evaluator_function:
            fn = rubric.evaluator_function
            parameters = list(inspect.signature(fn).parameters.values())
            if len(parameters) >= 2:
                value = fn(validation.workflow, validation)
            elif parameters and parameters[0].name != "workflow":
                value = fn(validation)
            else:
                value = fn(validation.workflow)
            if inspect.isawaitable(value):
                value = await value
            score, reasoning = normalize_score(value, rubric.max_score, llm=False)
        else:
            # Context consists solely of the frozen artifact; no mutable DB query
            # or subsequent manager action can change one criterion's evidence.
            # The pinned rubric runner creates WorkflowValidationRule without
            # a scope, which renders Workflow.pretty_print (300-char resources).
            # Callable rubrics still receive the complete requested context.
            evaluation_input = judge_prompt(rubric, validation.workflow.pretty_print())
            response = await infer(
                model=self.model,
                system="You are a validation expert.",
                prompt=evaluation_input,
                output_type=JudgeOutput,
            )
            judged = JudgeOutput.model_validate(response.output)
            score, _ = normalize_score(judged.score, rubric.max_score, llm=True)
            reasoning = judged.reasoning
            usage = {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "elapsed_seconds": response.elapsed_seconds,
            }
        return CriterionOutcome(
            slug=self.slug,
            name=rubric.name,
            score=score,
            max_score=rubric.max_score,
            passed=score >= 0.8 * rubric.max_score,
            weight=1,
            feedback=reasoning,
            evaluation_input=evaluation_input,
            metadata={
                "owner": definition.owner,
                "kind": definition.kind,
                "snapshot_hash": digest,
                "preference_weight": state.weights.get(definition.owner, 0),
                "model": self.model if rubric.llm_prompt else None,
                "model_settings": model_settings() if rubric.llm_prompt else None,
                "usage": usage,
            },
        )


class MAGRubric(Evaluator):
    type_slug: ClassVar[str] = "manager-gym-rubric"
    failure_policy: Literal["incomplete"] = "incomplete"
    scenario: str
    model: str

    def criteria_for(self, task: Task) -> Iterable[Criterion]:
        return [
            MAGCriterion(
                slug=d.slug,
                description=d.rubric.description or d.rubric.name,
                score_spec=ScoreScale(max_score=d.rubric.max_score),
                scenario=self.scenario,
                model=self.model,
            )
            for d in definitions(self.scenario)
        ]

    def aggregate_task(
        self, task: Task, criterion_results: Iterable[CriterionOutcome]
    ) -> TaskEvaluationResult:
        rows = list(criterion_results)
        expected = {d.slug for d in definitions(self.scenario)}
        if len(rows) != len(expected) or {r.slug for r in rows} != expected:
            raise ValueError("Incomplete or duplicate MAG criterion results")
        if len({r.metadata["snapshot_hash"] for r in rows}) != 1:
            raise ValueError("MAG criteria evaluated different snapshots")
        groups = defaultdict(list)
        for row in rows:
            if row.metadata["kind"] == "preference":
                groups[row.metadata["owner"]].append(row)
        scores = {
            key: sum(r.score for r in group) / sum(r.max_score for r in group)
            for key, group in groups.items()
        }
        weights = {key: group[0].metadata["preference_weight"] for key, group in groups.items()}
        utility = sum(scores[key] * weights[key] for key in groups)
        return TaskEvaluationResult(
            task_slug=task.task_slug,
            score=utility,
            passed=utility >= 0.8,
            evaluator_name=self.name,
            criterion_results=rows,
            metadata={
                "score_scale": "normalized_0_1",
                "preference_scores": scores,
                "preference_weights": weights,
                "diagnostic_count": sum(r.metadata["kind"] == "diagnostic" for r in rows),
                "snapshot_hash": rows[0].metadata["snapshot_hash"],
                "incomplete": False,
            },
        )
