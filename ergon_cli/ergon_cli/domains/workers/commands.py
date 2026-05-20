from argparse import Namespace

from ergon_cli.domains.workers.models import WorkerCommand, WorkerListResult
from ergon_cli.domains.workers.service import list_worker_refs
from ergon_cli.shared.errors import CliError, CliUsageError
from ergon_cli.shared.exit_codes import OK
from ergon_cli.shared.output import render_table


def handle_worker(args: Namespace) -> int:
    try:
        action = args.worker_action
        if action != "list":
            raise CliUsageError("Usage: ergon worker list")
        result = list_worker_refs(WorkerCommand(action=action))
    except CliError as exc:
        print(exc.message)
        return exc.exit_code
    print(render_worker_list(result))
    return OK


def render_worker_list(result: WorkerListResult) -> str:
    return render_table(
        ["Slug", "Name"],
        [[worker.slug, worker.name] for worker in result.workers],
    )
