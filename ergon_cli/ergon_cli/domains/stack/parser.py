import argparse

from ergon_cli.commands.stack import handle_start, handle_stop


def register_stack_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser(
        "start",
        help="Start the local dev stack (postgres + api + inngest + dashboard)",
    ).set_defaults(handler=handle_start)
    subparsers.add_parser("stop", help="Stop the local dev stack").set_defaults(handler=handle_stop)
