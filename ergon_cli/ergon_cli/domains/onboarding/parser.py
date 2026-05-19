import argparse

from ergon_cli.domains.onboarding.commands import handle_onboard


def register_onboard_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser(
        "onboard",
        help="Interactive environment setup wizard",
    ).set_defaults(handler=handle_onboard)
