from collections.abc import Callable, Sequence

from ergon_cli.domains.workers.models import WorkerCommand, WorkerListResult, WorkerRef
from ergon_cli.shared.errors import CliUsageError

_WORKER_ROWS = (
    ("react-v1", "ReActWorker"),
    ("training-stub", "TrainingStubWorker"),
)


def list_workers() -> list[list[str]]:
    return [list(row) for row in sorted(_WORKER_ROWS)]


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
