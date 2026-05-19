from typing import Any, ClassVar

from ergon_core.api.criterion import (
    Criterion,
    CriterionContext,
    CriterionEvidence,
    CriterionOutcome,
    EvidenceMessage,
    ScoreScale,
)
from pydantic import BaseModel, model_validator

from ergon_builtins.benchmarks.researchrubrics.criteria.evidence import (
    ResourceEvidence,
    load_researchrubrics_evidence,
)
from ergon_builtins.benchmarks.researchrubrics.criteria.prompts import (
    build_system_prompt,
    build_user_prompt,
)
from ergon_builtins.benchmarks.researchrubrics.task_schemas import RubricCriterion
from ergon_builtins.common.llm.structured_judge import (
    JudgeMessage,
    call_structured_judge,
)


class ResearchRubricsVerdict(BaseModel):
    reasoning: str
    passed: bool


class ResearchRubricsJudgeCriterion(Criterion):
    """ResearchRubrics-specific LLM judge for one dataset rubric item.

    ``judge_model`` and ``rubric_text`` are first-class Pydantic fields
    so they survive a ``task_json`` round trip alongside the object-bound
    rubric. ``rubric_text`` mirrors ``rubric.criterion`` for snapshots
    that need the prompt body without re-walking the rubric structure.
    """

    type_slug: ClassVar[str] = "researchrubrics-llm-judge"

    rubric: RubricCriterion
    judge_model: str = "openai:gpt-4o"
    rubric_text: str = ""  # slopcop: ignore[no-str-empty-default]

    @model_validator(mode="before")
    @classmethod
    def _reject_model_alias(cls, data: Any) -> Any:  # slopcop: ignore[no-typing-any]
        if isinstance(data, dict) and "model" in data:
            raise ValueError(
                "ResearchRubricsJudgeCriterion uses judge_model; model is not accepted"
            )
        return data

    def __init__(self, **data: Any) -> None:  # slopcop: ignore[no-typing-any]
        rubric = data.get("rubric")
        if isinstance(rubric, RubricCriterion):
            if "description" not in data:
                data["description"] = rubric.criterion
            if "weight" not in data:
                data["weight"] = rubric.weight
            if "score_spec" not in data:
                data["score_spec"] = ScoreScale(max_score=abs(rubric.weight))
            if "rubric_text" not in data:
                data["rubric_text"] = rubric.criterion
        super().__init__(**data)

    @property
    def system_prompt(self) -> str:
        """Rendered system prompt for this rubric criterion.

        Derived lazily from ``self.rubric`` so the criterion remains
        round-trippable through ``task_json`` — only the persisted fields
        (``rubric``, ``judge_model``, ``slug``, ...) need to survive serialization.
        """
        return build_system_prompt(self.rubric)

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        final_outputs, scratch_outputs = await load_researchrubrics_evidence(context)
        user_prompt = build_user_prompt(
            context,
            final_outputs=final_outputs,
            scratch_outputs=scratch_outputs,
        )
        system_prompt = self.system_prompt
        verdict = await self._call_judge(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        evaluated_resource_ids = [
            str(evidence.resource.id) for evidence in [*final_outputs, *scratch_outputs]
        ]
        return CriterionOutcome(
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
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                verdict=verdict,
                evaluated_resource_ids=evaluated_resource_ids,
                final_outputs=final_outputs,
                rubric=self.rubric,
                model=self.judge_model,
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
        final_outputs: list[ResourceEvidence],
        rubric: RubricCriterion,
        model: str,
    ) -> CriterionEvidence:
        return CriterionEvidence(
            prompt_messages=[
                EvidenceMessage(role="system", content=system_prompt),
                EvidenceMessage(role="user", content=user_prompt),
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
            model=self.judge_model,
        )
