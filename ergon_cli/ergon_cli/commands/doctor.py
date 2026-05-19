"""Compatibility wrapper for the doctor CLI domain."""

from argparse import Namespace

from ergon_cli.domains.doctor.commands import handle_doctor as handle_doctor_command


def handle_doctor(args: Namespace) -> int:
    return handle_doctor_command(args)
