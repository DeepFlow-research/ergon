"""Discovery backed by explicit builtins maps."""

from ergon_builtins.registry_core import (
    BENCHMARKS as CORE_BENCHMARKS,
    EVALUATORS as CORE_EVALUATORS,
    WORKERS as CORE_WORKERS,
)


def _maps():
    benchmarks = dict(CORE_BENCHMARKS)
    evaluators = dict(CORE_EVALUATORS)
    workers = dict(CORE_WORKERS)
    try:
        from ergon_builtins.registry_data import (
            BENCHMARKS as DATA_BENCHMARKS,
            EVALUATORS as DATA_EVALUATORS,
            WORKERS as DATA_WORKERS,
        )
    except ImportError:
        pass
    else:
        benchmarks.update(DATA_BENCHMARKS)
        evaluators.update(DATA_EVALUATORS)
        workers.update(DATA_WORKERS)
    return benchmarks, evaluators, workers


def list_benchmarks() -> list[list[str]]:
    benchmarks, _, _ = _maps()
    rows = []
    for slug, cls in sorted(benchmarks.items()):
        name = getattr(cls, "type_slug", slug)  # slopcop: ignore[no-hasattr-getattr]
        desc = getattr(cls, "__doc__", "") or ""  # slopcop: ignore[no-hasattr-getattr]
        rows.append([slug, name, desc.strip().split("\n")[0] if desc else ""])
    return rows


def list_workers() -> list[list[str]]:
    _, _, workers = _maps()
    rows = []
    for slug, cls in sorted(workers.items()):
        name = getattr(cls, "type_slug", slug)  # slopcop: ignore[no-hasattr-getattr]
        rows.append([slug, name])
    return rows


def list_evaluators() -> list[list[str]]:
    _, evaluators, _ = _maps()
    rows = []
    for slug, cls in sorted(evaluators.items()):
        name = getattr(cls, "type_slug", slug)  # slopcop: ignore[no-hasattr-getattr]
        rows.append([slug, name])
    return rows
