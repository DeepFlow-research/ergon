import argparse

from ergon_cli.commands.doctor import handle_doctor


def register_doctor_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("doctor", help="Check environment health").set_defaults(
        handler=handle_doctor
    )
