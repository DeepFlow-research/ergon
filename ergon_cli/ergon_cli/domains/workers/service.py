from collections.abc import Callable, Sequence

from ergon_cli.discovery import list_workers
from ergon_cli.domains.workers.models import WorkerCommand, WorkerListResult, WorkerRef
from ergon_cli.shared.errors import CliUsageError


def list_worker_refs(
    command: WorkerCommand,
    *,
    discover: Callable[[], Sequence[Sequence[str]]] = list_workers,
) -> WorkerListResult:
    if command.action != "list":
        raise CliUsageError("Usage: ergon worker list")
    return WorkerListResult(
        workers=tuple(WorkerRef(slug=row[0], name=row[1]) for row in discover())
    )
