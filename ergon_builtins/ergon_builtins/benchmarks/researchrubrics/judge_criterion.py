from typing import ClassVar

from ergon_core.api.criterion import Criterion
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import (
    CriterionObservation,
    CriterionObservationMessage,
    CriterionResult,
    CriterionScoreSpec,
)
from ergon_core.core.runtime.resources import RunResourceKind, RunResourceView
from pydantic import BaseModel

from ergon_builtins.benchmarks.researchrubrics.task_schemas import RubricCriterion
from ergon_builtins.common.llm.structured_judge import (
    JudgeMessage,
    call_structured_judge,
)


class _ResourceEvidence(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    resource: RunResourceView
    text: str


class ResearchRubricsVerdict(BaseModel):
    reasoning: str
    passed: bool


class ResearchRubricsJudgeCriterion(Criterion):
    """ResearchRubrics-specific LLM judge for one dataset rubric item."""

    type_slug: ClassVar[str] = "researchrubrics-llm-judge"

    def __init__(
        self,
        *,
        slug: str,
        rubric: RubricCriterion,
        model: str = "openai:gpt-4o",
    ) -> None:
        super().__init__(
            slug=slug,
            description=rubric.criterion,
            weight=rubric.weight,
            score_spec=CriterionScoreSpec(max_score=abs(rubric.weight)),
        )
        self.rubric = rubric
        self.model = model
        self.system_prompt = self._build_system_prompt(rubric)

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        final_outputs, scratch_outputs = await self._load_researchrubrics_evidence(context)
        user_prompt = self._build_user_prompt(
            context,
            final_outputs=final_outputs,
            scratch_outputs=scratch_outputs,
        )
        verdict = await self._call_judge(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
        )
        evaluated_resource_ids = [
            str(evidence.resource.id) for evidence in [*final_outputs, *scratch_outputs]
        ]
        return CriterionResult(
            slug=self.slug,
            name=self.slug,
            score=self.score_spec.max_score if verdict.passed else 0.0,
            passed=verdict.passed,
            weight=self.weight,
            max_score=self.score_spec.max_score,
            feedback=verdict.reasoning,
            model_reasoning=verdict.reasoning,
            evaluation_input=user_prompt,
            evaluated_resource_ids=evaluated_resource_ids,
            observation=self._build_observation(
                system_prompt=self.system_prompt,
                user_prompt=user_prompt,
                verdict=verdict,
                evaluated_resource_ids=evaluated_resource_ids,
                final_outputs=final_outputs,
                rubric=self.rubric,
                model=self.model,
            ),
        )

    @classmethod
    def _build_observation(
        cls,
        *,
        system_prompt: str,
        user_prompt: str,
        verdict: ResearchRubricsVerdict,
        evaluated_resource_ids: list[str],
        final_outputs: list[_ResourceEvidence],
        rubric: RubricCriterion,
        model: str,
    ) -> CriterionObservation:
        return CriterionObservation(
            prompt_messages=[
                CriterionObservationMessage(role="system", content=system_prompt),
                CriterionObservationMessage(role="user", content=user_prompt),
            ],
            evidence_resource_ids=evaluated_resource_ids,
            output=verdict.model_dump(mode="json"),
            model=model,
            details={
                "axis": rubric.axis,
                "rubric_weight": rubric.weight,
                "primary_evidence": (
                    f"run_resource:{final_outputs[0].resource.name}"
                    if final_outputs
                    else "worker_result.output"
                ),
            },
        )

    async def _call_judge(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> ResearchRubricsVerdict:
        return await call_structured_judge(
            messages=[
                JudgeMessage(role="system", content=system_prompt),
                JudgeMessage(role="user", content=user_prompt),
            ],
            response_type=ResearchRubricsVerdict,
            model=self.model,
        )

    @classmethod
    async def _load_researchrubrics_evidence(
        cls,
        context: EvaluationContext,
    ) -> tuple[list[_ResourceEvidence], list[_ResourceEvidence]]:
        if context.runtime is None:
            return [], []

        resources = await context.runtime.list_resources()
        evidence: list[_ResourceEvidence] = []
        for resource in resources:
            try:
                raw_content = await context.runtime.read_resource_by_id(resource.id)
            except OSError as exc:
                text = f"[Unable to read resource {resource.id}: {exc}]"
            else:
                text = raw_content.decode("utf-8", errors="replace")
            evidence.append(_ResourceEvidence(resource=resource, text=text))

        final_outputs = [item for item in evidence if cls._is_final_output_resource(item.resource)]
        scratch_outputs = [
            item for item in evidence if not cls._is_final_output_resource(item.resource)
        ]
        return final_outputs, scratch_outputs

    @classmethod
    def _is_final_output_resource(cls, resource: RunResourceView) -> bool:
        sandbox_origin = str(resource.metadata.get("sandbox_origin") or "")
        return resource.kind == RunResourceKind.REPORT or sandbox_origin.startswith(
            "/workspace/final_output/"
        )

    @classmethod
    def _format_resource_section(
        cls,
        title: str,
        evidence: list[_ResourceEvidence],
    ) -> str:
        if not evidence:
            return f"{title}:\n(none)"

        parts = [f"{title}:"]
        for idx, item in enumerate(evidence, start=1):
            resource = item.resource
            sandbox_origin = resource.metadata.get("sandbox_origin")
            provenance = (
                f"id={resource.id}; name={resource.name}; kind={resource.kind.value}; "
                f"sandbox_origin={sandbox_origin or '(unknown)'}"
            )
            parts.append(f"\n[{idx}] {provenance}\n{item.text}")
        return "\n".join(parts)

    @classmethod
    def _build_system_prompt(cls, criterion: RubricCriterion) -> str:
        axis_context = (
            f"\n\nThis criterion belongs to the ResearchRubrics '{criterion.axis}' axis."
            if criterion.axis
            else ""
        )
        weight_note = f"\n\nResearchRubrics weight: {criterion.weight}"
        return (
            "You are an expert ResearchRubrics evaluator assessing deep-research reports.\n\n"
            "Evaluate whether the report satisfies this exact rubric criterion:\n"
            f"{criterion.criterion}{axis_context}{weight_note}\n\n"
            "Judge the final output resources first. Use scratch/supporting resources "
            "only as secondary context, and use the final assistant message only as a "
            "status summary. Return a binary verdict: `passed=true` only when the "
            "criterion is clearly satisfied. Explain the decision with concrete "
            "evidence from the provided material."
        )

    @classmethod
    def _build_user_prompt(
        cls,
        context: EvaluationContext,
        *,
        final_outputs: list[_ResourceEvidence],
        scratch_outputs: list[_ResourceEvidence],
    ) -> str:
        return "\n\n".join(
            [
                f"Original research request:\n{context.task.description}",
                cls._format_resource_section("Final output resources", final_outputs),
                cls._format_resource_section(
                    "Scratch / supporting resources",
                    scratch_outputs,
                ),
                f"Final assistant message:\n{context.worker_result.output}",
            ]
        )
