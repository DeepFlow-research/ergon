from ergon_builtins.workers import ReActWorker, TrainingStubWorker

from ergon_cli.domains.workers.service import list_workers


def test_worker_discovery_lists_current_builtin_worker_slugs() -> None:
    rows = list_workers()
    slugs = {row[0] for row in rows}

    assert ReActWorker.type_slug in slugs
    assert TrainingStubWorker.type_slug in slugs
    assert "react-worker" not in slugs
    assert "training-stub-worker" not in slugs
