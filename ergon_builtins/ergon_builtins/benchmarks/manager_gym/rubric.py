"""Grade a frozen episode snapshot with upstream MAG's rubrics.

Each upstream rubric becomes one ``MAGCriterion``: callable rubrics run on a
validation context rebuilt from the snapshot, and LLM rubrics go to the judge
with upstream's prompt. ``MAGRubric`` combines the criteria into MAG's utility.
"""

import inspect
import math
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime
from functools import cache
from typing import ClassVar, Literal
from uuid import UUID

from ergon_core.api import Task
from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome
from ergon_core.api.criterion.score import ScoreScale
from ergon_core.api.rubric import Evaluator
from ergon_core.api.rubric.results import TaskEvaluationResult
from pydantic import BaseModel, Field
from pydantic_ai.exceptions import AgentRunError

from ergon_builtins.benchmarks.manager_gym.inference import InferenceResult, infer
from ergon_builtins.benchmarks.manager_gym.prompts import JUDGE_SYSTEM_PROMPT, judge_prompt
from ergon_builtins.benchmarks.manager_gym.rubric_versions import (
    LATEST_RUBRIC_VERSION,
    RubricVersion,
    corrected,
)
from ergon_builtins.benchmarks.manager_gym.state import (
    EpisodeState,
    all_tasks,
    snapshot_hash,
)
from ergon_builtins.benchmarks.manager_gym.upstream import (
    SCENARIOS,
    AdditionalContextItem,
    AgentPublicState,
    Preference,
    PreferenceWeights,
    RunCondition,
    SenderMessagesView,
    TaskStatus,
    ThreadMessagesView,
    ValidationContext,
    Workflow,
    WorkflowRubric,
    build_constraints_for_scenario,
    build_default_evaluators,
)
from ergon_builtins.benchmarks.manager_gym.upstream import (
    Evaluator as UpstreamEvaluator,
)
from ergon_builtins.benchmarks.manager_gym.upstream import Task as PlannedTask

OwnerKind = Literal["preference", "diagnostic"]

# Upstream parity: validation_rules.py passes a rubric at 80% of its maximum
# and maps categorical judge scores to these fractions of the maximum.
PASS_FRACTION = 0.8
CATEGORICAL_SCORE = {"low": 0.33, "medium": 0.66, "high": 1.0}


class RubricDefinition(BaseModel):
    """One upstream rubric and where it belongs in the scenario's evaluation.

    ``slug`` is ``<scenario>/<kind>/<owner index>/<rubric index>``, stable across
    rubric versions. Preference rubrics feed utility; diagnostics are reported only.
    """

    slug: str
    owner: str
    kind: OwnerKind
    rubric: WorkflowRubric


def _owners(scenario: str) -> list[tuple[OwnerKind, str, UpstreamEvaluator]]:
    """Preference evaluators, then diagnostic evaluators, in upstream's order."""
    spec = SCENARIOS[scenario]
    owners: list[tuple[OwnerKind, str, UpstreamEvaluator]] = [
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
    return owners


def definitions(
    scenario: str,
    *,
    terminal_only: bool = True,
    rubric_version: RubricVersion = LATEST_RUBRIC_VERSION,
) -> list[RubricDefinition]:
    """The rubrics that grade ``scenario`` under ``rubric_version``.

    Args:
        scenario: Scenario key.
        terminal_only: Keep only rubrics upstream runs at the end of an episode:
            every diagnostic, and preference rubrics declared ``ON_COMPLETION``.
        rubric_version: 1 for upstream's rubrics, 2 for the corrected set.
    """
    result = []
    for index, (kind, owner, evaluator) in enumerate(_owners(scenario)):
        for ordinal, upstream_rubric in enumerate(evaluator.rubrics):
            rubric = corrected(
                upstream_rubric, scenario=scenario, owner=owner, version=rubric_version
            )
            if rubric is None:
                continue
            if (
                terminal_only
                and kind == "preference"
                and rubric.run_condition != RunCondition.ON_COMPLETION
            ):
                continue
            result.append(
                RubricDefinition(
                    slug=f"{scenario}/{kind}/{index:02d}/{ordinal:02d}",
                    owner=owner,
                    kind=kind,
                    rubric=rubric,
                )
            )
    return result


@cache
def _definitions_by_slug(
    scenario: str, rubric_version: RubricVersion
) -> dict[str, RubricDefinition]:
    return {d.slug: d for d in definitions(scenario, rubric_version=rubric_version)}


def _group_senders(workflow: Workflow) -> list[SenderMessagesView]:
    groups = defaultdict(list)
    for m in workflow.messages:
        groups[m.sender_id].append(m)
    return [
        SenderMessagesView(
            sender_id=k,
            total_messages=len(messages),
            most_recent_at=max(m.timestamp for m in messages),
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
            last_activity=max(m.timestamp for m in messages),
            messages=messages,
        )
        for k, messages in threads.items()
    ]


def _agent_public_state(
    key: str, state: EpisodeState, tasks: dict[UUID, PlannedTask], joined_at: datetime
) -> AgentPublicState:
    mine = [t for t in tasks.values() if t.assigned_agent_id == key]
    running = [t for t in mine if t.status == TaskStatus.RUNNING]
    return AgentPublicState(
        agent_id=key,
        agent_type=state.actors[key].agent_type,
        is_available=not running,
        tasks_completed=sum(t.status == TaskStatus.COMPLETED and not t.subtasks for t in mine),
        joined_at=joined_at,
        current_task_ids=[t.id for t in running],
    )


def validation_context(state: EpisodeState, rubric: WorkflowRubric) -> ValidationContext:
    """The context upstream's validation engine would pass ``rubric``, from a frozen snapshot.

    Supplemental fields are filled only when the rubric requests them, as upstream does.
    """
    workflow = state.workflow.model_copy(deep=True)
    if workflow.started_at is None:
        raise ValueError("Frozen workflow has no start time")
    workflow.agents = {key: state.actors[key] for key in state.active_actors}
    current = PreferenceWeights(
        preferences=[Preference(name=k, weight=v) for k, v in state.weights.items()]
    )
    context = ValidationContext(
        workflow=workflow, current_preferences=current, timestep=state.timestep
    )
    required = rubric.required_context
    tasks = all_tasks(workflow)
    if AdditionalContextItem.MANAGER_ACTIONS in required:
        context.manager_actions = state.actions
    if AdditionalContextItem.PREFERENCE_HISTORY in required:
        context.preference_history = state.preference_history
    if AdditionalContextItem.COMMS_BY_SENDER in required:
        context.communications_by_sender = _group_senders(workflow)
    if AdditionalContextItem.COMMS_BY_THREAD in required:
        context.communications_by_thread = _group_threads(workflow)
    if AdditionalContextItem.RESOURCES_BY_TASK in required:
        context.resources_by_task = {
            k: workflow.get_task_output_resources(t) for k, t in tasks.items()
        }
        context.all_resources = workflow.get_all_resources()
    if AdditionalContextItem.STAKEHOLDER_PROFILE in required:
        context.stakeholder_profile = state.stakeholder().model_dump(mode="json")
    if AdditionalContextItem.AGENT_PUBLIC_STATES in required:
        context.agent_public_states = {
            k: _agent_public_state(k, state, tasks, workflow.started_at)
            for k in state.active_actors
        }
    if AdditionalContextItem.AGENT_TOOL_USAGE_BY_TASK in required:
        context.agent_tool_usage_by_task = state.tool_usage
    return context


# The judge's structured output: upstream's LLMScoredResponse. No docstring, so the
# schema the judge sees matches upstream's. The judge prompt also asks for a
# confidence, which upstream's schema omits too; it is not recorded.
class JudgeOutput(BaseModel):
    reasoning: str = Field(description="Explanation of the assessment and rationale for the score")
    score: float | Literal["low", "medium", "high"] | bool = Field(
        description="Numeric score assigned by LLM"
    )


def normalize_score(value: object, maximum: float, *, llm: bool) -> tuple[float, str]:
    """Convert a rubric's raw result to a score in ``[0, maximum]`` and its reasoning.

    Upstream parity: callable rubrics may return a number or a ``(score, reasoning)``
    tuple, and an unusable value scores 0 with an explanation. Judges may also answer
    with a boolean or ``"low"``/``"medium"``/``"high"``.

    Raises:
        ValueError: The score is not finite.
    """
    reasoning = ""
    if isinstance(value, tuple):
        if len(value) == 2:
            value, reasoning = value
        elif len(value) == 1:
            value = value[0]
        else:
            return 0.0, "Invalid tuple shape for score"
    if llm and isinstance(value, bool):
        score = maximum if value else 0.0
    elif llm and isinstance(value, str) and value in CATEGORICAL_SCORE:
        score = maximum * CATEGORICAL_SCORE[value]
    else:
        if not isinstance(value, int | float | str):
            return 0.0, "Normalization failed"
        try:
            score = float(value)
        except ValueError:
            return 0.0, "Normalization failed"
    if not math.isfinite(score):
        raise ValueError("Non-finite rubric score")
    return max(0.0, min(maximum, score)), str(reasoning)


def _call_rubric_function(
    fn: Callable[..., object], context: ValidationContext
) -> object | Awaitable[object]:
    """Call a callable rubric with the arguments its signature asks for.

    Upstream rubrics take ``(workflow, context)``, ``(context)`` or ``(workflow)``.
    """
    parameters = list(inspect.signature(fn).parameters.values())
    if len(parameters) >= 2:
        return fn(context.workflow, context)
    if parameters and parameters[0].name != "workflow":
        return fn(context)
    return fn(context.workflow)


class MAGCriterion(Criterion):
    """One upstream rubric, graded against the episode's frozen snapshot.

    The snapshot is the only evidence: no database read or later manager action
    can change what a criterion sees. LLM rubrics get upstream's rendering of the
    workflow (``Workflow.pretty_print``, with 300-character resource previews);
    callable rubrics get the full context they request.
    """

    type_slug: ClassVar[str] = "manager-gym-criterion"
    scenario: str
    model: str
    rubric_version: RubricVersion = LATEST_RUBRIC_VERSION

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        state = EpisodeState.model_validate_json(context.worker_result.output)
        if state.infrastructure_errors or context.worker_result.metadata.get("incomplete"):
            raise RuntimeError("MAG episode is incomplete: " + str(state.infrastructure_errors))
        expected_digest = context.worker_result.metadata.get("snapshot_hash")
        digest = snapshot_hash(state)
        if expected_digest is None:
            raise ValueError("MAG snapshot output has no snapshot_hash")
        if digest != expected_digest:
            raise ValueError("Frozen MAG snapshot digest mismatch")
        definition = self._definition()
        rubric = definition.rubric
        validation = validation_context(state, rubric)
        evaluation_input = None
        usage = None
        if rubric.evaluator_function:
            value = _call_rubric_function(rubric.evaluator_function, validation)
            if inspect.isawaitable(value):
                value = await value
            score, reasoning = normalize_score(value, rubric.max_score, llm=False)
        else:
            evaluation_input = judge_prompt(rubric, validation.workflow.pretty_print())
            response = await self._judge(state, rubric, evaluation_input)
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
            passed=score >= PASS_FRACTION * rubric.max_score,
            # Preference weights are applied in MAGRubric.aggregate_task, from metadata.
            weight=1,
            feedback=reasoning,
            evaluation_input=evaluation_input,
            metadata={
                "owner": definition.owner,
                "kind": definition.kind,
                "rubric_version": self.rubric_version,
                "snapshot_hash": digest,
                "preference_weight": state.weights.get(definition.owner, 0),
                "model": self.model if rubric.llm_prompt else None,
                "model_settings": (
                    state.config.inference.model_settings("judge") if rubric.llm_prompt else None
                ),
                "usage": usage,
            },
        )

    def _definition(self) -> RubricDefinition:
        by_slug = _definitions_by_slug(self.scenario, self.rubric_version)
        if self.slug not in by_slug:
            raise ValueError(
                f"No MAG rubric {self.slug!r} for {self.scenario} "
                f"under rubric version {self.rubric_version}"
            )
        return by_slug[self.slug]

    async def _judge(
        self, state: EpisodeState, rubric: WorkflowRubric, prompt: str
    ) -> InferenceResult:
        try:
            return await infer(
                model=self.model,
                role="judge",
                profile=state.config.inference,
                system=JUDGE_SYSTEM_PROMPT,
                prompt=prompt,
                output_type=JudgeOutput,
            )
        except (AgentRunError, TimeoutError) as error:
            error.add_note(f"MAG judge criterion: {self.slug} ({rubric.name})")
            raise


class MAGRubric(Evaluator):
    """MAG's terminal utility for one episode.

    A failed or missing criterion makes the evaluation incomplete (a null score)
    rather than zero.
    """

    type_slug: ClassVar[str] = "manager-gym-rubric"
    failure_policy: Literal["incomplete"] = "incomplete"
    scenario: str
    model: str
    rubric_version: RubricVersion = LATEST_RUBRIC_VERSION

    def criteria_for(self, task: Task) -> Iterable[Criterion]:
        return [
            MAGCriterion(
                slug=d.slug,
                description=d.rubric.description or d.rubric.name,
                score_spec=ScoreScale(max_score=d.rubric.max_score),
                scenario=self.scenario,
                model=self.model,
                rubric_version=self.rubric_version,
            )
            for d in definitions(self.scenario, rubric_version=self.rubric_version)
        ]

    def aggregate_task(
        self, task: Task, criterion_results: Iterable[CriterionOutcome]
    ) -> TaskEvaluationResult:
        """Combine criteria into MAG's utility, in ``[0, 1]``.

        Each preference scores ``sum(score) / sum(max_score)`` over its rubrics, and
        utility is the sum of preference scores weighted by the final preference
        weights. Diagnostics are recorded but excluded.

        Upstream parity: this is the arithmetic upstream uses for its reported
        utility. The ``aggregation`` strategy an upstream evaluator declares is not
        applied, because upstream's utility does not apply it either.

        Raises:
            ValueError: Criteria are missing, duplicated or graded different snapshots.
        """
        rows = list(criterion_results)
        expected = {d.slug for d in definitions(self.scenario, rubric_version=self.rubric_version)}
        if len(rows) != len(expected) or {r.slug for r in rows} != expected:
            raise ValueError("Incomplete or duplicate MAG criterion results")
        if len({r.metadata["snapshot_hash"] for r in rows}) != 1:
            raise ValueError("MAG criteria evaluated different snapshots")
        groups: dict[str, list[CriterionOutcome]] = defaultdict(list)
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
            passed=utility >= PASS_FRACTION,
            evaluator_name=self.name,
            criterion_results=rows,
            metadata={
                "score_scale": "normalized_0_1",
                "rubric_version": self.rubric_version,
                "preference_scores": scores,
                "preference_weights": weights,
                "diagnostic_count": sum(r.metadata["kind"] == "diagnostic" for r in rows),
                "snapshot_hash": rows[0].metadata["snapshot_hash"],
                "incomplete": False,
            },
        )
