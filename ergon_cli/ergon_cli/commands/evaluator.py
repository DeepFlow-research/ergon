from argparse import Namespace

from ergon_cli.domains.evaluators.commands import handle_evaluator as handle_evaluator_command


def handle_evaluator(args: Namespace) -> int:
    return handle_evaluator_command(args)
