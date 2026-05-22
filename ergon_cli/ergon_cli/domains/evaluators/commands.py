from argparse import Namespace

from ergon_cli.domains.evaluators.models import EvaluatorCommand, EvaluatorListResult
from ergon_cli.domains.evaluators.service import list_evaluator_refs
from ergon_cli.shared.errors import CliError, CliUsageError
from ergon_cli.shared.exit_codes import OK
from ergon_cli.shared.output import render_table


def handle_evaluator(args: Namespace) -> int:
    try:
        action = args.evaluator_action
        if action != "list":
            raise CliUsageError("Usage: ergon evaluator list")
        result = list_evaluator_refs(EvaluatorCommand(action=action))
    except CliError as exc:
        print(exc.message)
        return exc.exit_code
    print(render_evaluator_list(result))
    return OK


def render_evaluator_list(result: EvaluatorListResult) -> str:
    return render_table(
        ["Slug", "Name"],
        [[evaluator.slug, evaluator.name] for evaluator in result.evaluators],
    )
