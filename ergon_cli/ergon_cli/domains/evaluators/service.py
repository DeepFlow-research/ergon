from collections.abc import Callable, Sequence

from ergon_cli.domains.evaluators.models import (
    EvaluatorCommand,
    EvaluatorListResult,
    EvaluatorRef,
)
from ergon_cli.shared.errors import CliUsageError

_EVALUATOR_ROWS = (
    ("gdpeval-staged-rubric", "StagedRubric"),
    ("minif2f-rubric", "MiniF2FRubric"),
    ("researchrubrics-rubric", "ResearchRubricsRubric"),
    ("swebench-rubric", "SWEBenchRubric"),
)


def list_evaluators() -> list[list[str]]:
    return [list(row) for row in sorted(_EVALUATOR_ROWS)]


def list_evaluator_refs(
    command: EvaluatorCommand,
    *,
    discover: Callable[[], Sequence[Sequence[str]]] = list_evaluators,
) -> EvaluatorListResult:
    if command.action != "list":
        raise CliUsageError("Usage: ergon evaluator list")
    return EvaluatorListResult(
        evaluators=tuple(EvaluatorRef(slug=row[0], name=row[1]) for row in discover())
    )
