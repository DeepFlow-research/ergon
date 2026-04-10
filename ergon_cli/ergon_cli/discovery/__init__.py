"""Registry discovery: reads BENCHMARKS/WORKERS/EVALUATORS from ergon_builtins.registry."""

from ergon_builtins.registry import BENCHMARKS, EVALUATORS, WORKERS


def list_benchmarks() -> list[list[str]]:
    rows = []
    for slug, cls in sorted(BENCHMARKS.items()):
        name = getattr(cls, "type_slug", slug)  # slopcop: ignore[no-hasattr-getattr]
        desc = getattr(cls, "__doc__", "") or ""  # slopcop: ignore[no-hasattr-getattr]
        rows.append([slug, name, desc.strip().split("\n")[0] if desc else ""])
    return rows


def list_workers() -> list[list[str]]:
    rows = []
    for slug, cls in sorted(WORKERS.items()):
        name = getattr(cls, "type_slug", slug)  # slopcop: ignore[no-hasattr-getattr]
        rows.append([slug, name])
    return rows


def list_evaluators() -> list[list[str]]:
    rows = []
    for slug, cls in sorted(EVALUATORS.items()):
        name = getattr(cls, "type_slug", slug)  # slopcop: ignore[no-hasattr-getattr]
        rows.append([slug, name])
    return rows
