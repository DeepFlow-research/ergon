"""Worker subcommand: list available workers."""

from argparse import Namespace

from arcane_cli.discovery import list_workers
from arcane_cli.rendering import render_table


def handle_worker(args: Namespace) -> int:
    if args.worker_action == "list":
        workers = list_workers()
        render_table(["Slug", "Name"], workers)
        return 0
    print("Usage: arcane worker list")
    return 1
