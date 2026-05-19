"""Compatibility wrappers for run CLI commands."""

from argparse import Namespace

from ergon_cli.domains.runs.commands import (
    cancel_run_command,
    list_runs_command,
    status_run_command,
)
from ergon_cli.domains.runs.commands import handle_run as handle_run_command
from ergon_core.core.persistence.shared.db import ensure_db


def handle_run(args: Namespace) -> int:
    ensure_db()
    return handle_run_command(args)


def list_runs(args: Namespace) -> int:
    ensure_db()
    return list_runs_command(args)


def cancel_run(args: Namespace) -> int:
    ensure_db()
    return cancel_run_command(args)


def status_run(args: Namespace) -> int:
    ensure_db()
    return status_run_command(args)
