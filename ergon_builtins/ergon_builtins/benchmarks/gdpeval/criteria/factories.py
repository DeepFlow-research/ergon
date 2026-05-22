"""Factory helpers for GDP-specific criterion configurations."""

from ergon_core.api.criterion import ScoreScale

from ergon_builtins.benchmarks.gdpeval.criteria.code_check import CodeCheckCriterion
from ergon_builtins.benchmarks.gdpeval.criteria.llm_judge import LLMJudgeCriterion


def make_code_check(
    name: str,
    code_template: str,
    *,
    description: str,
    weight: float = 1.0,
    score_spec: ScoreScale | None = None,
) -> CodeCheckCriterion:
    """Create a GDP code-check criterion."""
    return CodeCheckCriterion(
        slug=name,
        code_template=code_template,
        description=description,
        weight=weight,
        score_spec=score_spec or ScoreScale(),
    )


def make_llm_judge(
    name: str,
    prompt_template: str,
    *,
    description: str,
    weight: float = 1.0,
    score_spec: ScoreScale | None = None,
    model: str = "openai:gpt-4o",
) -> LLMJudgeCriterion:
    """Create a GDP LLM-judge criterion."""
    return LLMJudgeCriterion(
        slug=name,
        prompt_template=prompt_template,
        description=description,
        weight=weight,
        score_spec=score_spec or ScoreScale(),
        model=model,
    )


def output_file_exists(
    file_pattern: str = "*.docx",
    *,
    weight: float = 1.0,
    score_spec: ScoreScale | None = None,
) -> CodeCheckCriterion:
    """Check that at least one output file matching *file_pattern* exists."""
    return make_code_check(
        name=f"output-exists-{file_pattern}",
        code_template=(
            "import glob; "
            f"files = glob.glob('/workspace/final_output/{file_pattern}'); "
            "len(files) > 0"
        ),
        description=f"Verify output file matching {file_pattern} was produced",
        weight=weight,
        score_spec=score_spec,
    )


def content_quality_judge(
    aspect: str = "completeness",
    *,
    weight: float = 1.0,
    score_spec: ScoreScale | None = None,
    model: str = "openai:gpt-4o",
) -> LLMJudgeCriterion:
    """LLM judge that evaluates content quality on a specific *aspect*."""
    return make_llm_judge(
        name=f"content-quality-{aspect}",
        prompt_template=(
            f"Evaluate the {aspect} of the worker's output. "
            "Score 1.0 if the output fully satisfies expectations, "
            "0.5 for partial, 0.0 for absent or incorrect."
        ),
        description=f"Judge content quality on: {aspect}",
        weight=weight,
        score_spec=score_spec,
        model=model,
    )
