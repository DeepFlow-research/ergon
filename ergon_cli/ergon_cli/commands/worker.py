from argparse import Namespace

from ergon_cli.domains.workers.commands import handle_worker as handle_worker_command


def handle_worker(args: Namespace) -> int:
    return handle_worker_command(args)
