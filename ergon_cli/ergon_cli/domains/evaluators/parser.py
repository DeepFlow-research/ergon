import argparse

from ergon_cli.commands.evaluator import handle_evaluator


def register_evaluator_parser(subparsers: argparse._SubParsersAction) -> None:
    evaluator = subparsers.add_parser("evaluator", help="Evaluator operations")
    evaluator.set_defaults(handler=handle_evaluator)
    evaluator_sub = evaluator.add_subparsers(dest="evaluator_action")
    evaluator_sub.add_parser("list", help="List available evaluators")
