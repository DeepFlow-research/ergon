import argparse

from ergon_cli.domains.workers.commands import handle_worker


def register_worker_parser(subparsers: argparse._SubParsersAction) -> None:
    worker = subparsers.add_parser("worker", help="Worker operations")
    worker.set_defaults(handler=handle_worker)
    worker_sub = worker.add_subparsers(dest="worker_action")
    worker_sub.add_parser("list", help="List available workers")
