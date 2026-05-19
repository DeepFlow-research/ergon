from collections.abc import Callable, Sequence

from ergon_cli.discovery import list_evaluators
from ergon_cli.domains.evaluators.models import (
    EvaluatorCommand,
    EvaluatorListResult,
    EvaluatorRef,
)
from ergon_cli.shared.errors import CliUsageError


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
