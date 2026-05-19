"""Compatibility wrapper for onboarding CLI command."""

from argparse import Namespace

from ergon_cli.domains.onboarding.commands import handle_onboard as handle_onboard_command


def handle_onboard(args: Namespace) -> int:
    return handle_onboard_command(args)
