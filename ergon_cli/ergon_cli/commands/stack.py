"""Compatibility wrappers for stack lifecycle commands."""

from argparse import Namespace
from pathlib import Path

from ergon_cli.domains.stack.commands import handle_start as handle_start_command
from ergon_cli.domains.stack.commands import handle_stop as handle_stop_command
from ergon_cli.domains.stack.service import find_compose_file


def _find_compose_file(start: Path) -> Path | None:
    return find_compose_file(start)


def handle_start(args: Namespace) -> int:
    return handle_start_command(args)


def handle_stop(args: Namespace) -> int:
    return handle_stop_command(args)
