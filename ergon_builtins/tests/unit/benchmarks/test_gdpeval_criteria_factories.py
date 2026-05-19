import pytest
from ergon_core.api.criterion import ScoreScale
from pydantic import ValidationError

from ergon_builtins.benchmarks.gdpeval.criteria import (
    GDPEvalCriterion,
    content_quality_judge,
    make_code_check,
    make_llm_judge,
    output_file_exists,
)
from ergon_builtins.benchmarks.gdpeval.criteria.code_check import CodeCheckCriterion
from ergon_builtins.benchmarks.gdpeval.criteria.llm_judge import LLMJudgeCriterion


def test_gdpeval_criterion_union_accepts_domain_criteria() -> None:
    criterion: GDPEvalCriterion = make_code_check(
        name="has-output",
        code_template="True",
        description="checks output",
    )

    assert isinstance(criterion, CodeCheckCriterion)


def test_make_code_check_requires_explicit_description() -> None:
    criterion = make_code_check(
        name="has-output",
        code_template="True",
        description="checks output",
        score_spec=ScoreScale(max_score=2.5),
    )

    assert criterion.slug == "has-output"
    assert criterion.description == "checks output"
    assert criterion.score_spec.max_score == 2.5


def test_make_llm_judge_requires_explicit_description() -> None:
    criterion = make_llm_judge(
        name="quality",
        prompt_template="Judge this.",
        description="checks quality",
        model="openai:gpt-4o-mini",
        score_spec=ScoreScale(max_score=3.0),
    )

    assert isinstance(criterion, LLMJudgeCriterion)
    assert criterion.description == "checks quality"
    assert criterion.score_spec.max_score == 3.0


def test_gdpeval_presets_supply_descriptions() -> None:
    assert output_file_exists("*.docx").description == (
        "Verify output file matching *.docx was produced"
    )
    assert content_quality_judge("accuracy").description == "Judge content quality on: accuracy"


def test_code_check_rejects_legacy_max_score_constructor_input() -> None:
    with pytest.raises(ValidationError):
        CodeCheckCriterion.model_validate(
            {"slug": "code", "code_template": "True", "max_score": 4.0}
        )


def test_llm_judge_rejects_legacy_max_score_constructor_input() -> None:
    with pytest.raises(ValidationError):
        LLMJudgeCriterion.model_validate(
            {"slug": "judge", "prompt_template": "Judge.", "max_score": 5.0}
        )


def test_gdpeval_criteria_accept_canonical_score_spec() -> None:
    code = CodeCheckCriterion(
        slug="code",
        code_template="True",
        score_spec=ScoreScale(max_score=4.0),
    )
    judge = LLMJudgeCriterion(
        slug="judge",
        prompt_template="Judge.",
        score_spec=ScoreScale(max_score=5.0),
    )

    assert code.score_spec.max_score == 4.0
    assert judge.score_spec.max_score == 5.0
