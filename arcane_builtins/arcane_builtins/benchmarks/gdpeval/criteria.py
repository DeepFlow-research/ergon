"""GDP-specific criterion configurations.

Provides a union type for criteria used in GDP rubrics and factory
helpers that produce pre-configured CodeCheckCriterion /
LLMJudgeCriterion instances tuned for document-processing evaluation.
"""

from arcane_builtins.evaluators.criteria.code_check import CodeCheckCriterion
from arcane_builtins.evaluators.criteria.llm_judge import LLMJudgeCriterion

GDPEvalCriterion = CodeCheckCriterion | LLMJudgeCriterion

def make_code_check(
    name: str,
    code_template: str,
    *,
    description: str = "",  # slopcop: ignore[no-str-empty-default]
    weight: float = 1.0,
    max_score: float = 1.0,
) -> CodeCheckCriterion:
    """Create a GDP code-check criterion."""
    return CodeCheckCriterion(
        name=name,
        code_template=code_template,
        description=description,
        weight=weight,
        max_score=max_score,
    )

def make_llm_judge(
    name: str,
    prompt_template: str,
    *,
    description: str = "",  # slopcop: ignore[no-str-empty-default]
    weight: float = 1.0,
    max_score: float = 1.0,
    model: str = "gpt-4o",
) -> LLMJudgeCriterion:
    """Create a GDP LLM-judge criterion."""
    return LLMJudgeCriterion(
        name=name,
        prompt_template=prompt_template,
        description=description,
        weight=weight,
        max_score=max_score,
        model=model,
    )

# ---------------------------------------------------------------------------
# Common GDP criterion presets
# ---------------------------------------------------------------------------

def output_file_exists(
    file_pattern: str = "*.docx",
    *,
    weight: float = 1.0,
    max_score: float = 1.0,
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
        max_score=max_score,
    )

def content_quality_judge(
    aspect: str = "completeness",
    *,
    weight: float = 1.0,
    max_score: float = 1.0,
    model: str = "gpt-4o",
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
        max_score=max_score,
        model=model,
    )
