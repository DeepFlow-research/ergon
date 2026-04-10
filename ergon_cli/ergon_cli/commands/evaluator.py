"""Evaluator subcommand: list available evaluators."""

from argparse import Namespace

from arcane_cli.discovery import list_evaluators
from arcane_cli.rendering import render_table


def handle_evaluator(args: Namespace) -> int:
    if args.evaluator_action == "list":
        evaluators = list_evaluators()
        render_table(["Slug", "Name"], evaluators)
        return 0
    print("Usage: arcane evaluator list")
    return 1
