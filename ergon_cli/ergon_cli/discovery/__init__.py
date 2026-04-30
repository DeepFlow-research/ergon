"""Registry discovery backed by explicit builtins registration."""

from ergon_builtins.registry import register_builtins
from ergon_core.api.registry import registry

register_builtins(registry)


def list_benchmarks() -> list[list[str]]:
    rows = []
    for slug, cls in sorted(registry.benchmarks.items()):
        name = getattr(cls, "type_slug", slug)  # slopcop: ignore[no-hasattr-getattr]
        desc = getattr(cls, "__doc__", "") or ""  # slopcop: ignore[no-hasattr-getattr]
        rows.append([slug, name, desc.strip().split("\n")[0] if desc else ""])
    return rows


def list_workers() -> list[list[str]]:
    rows = []
    for slug, cls in sorted(registry.workers.items()):
        name = getattr(cls, "type_slug", slug)  # slopcop: ignore[no-hasattr-getattr]
        rows.append([slug, name])
    return rows


def list_evaluators() -> list[list[str]]:
    rows = []
    for slug, cls in sorted(registry.evaluators.items()):
        name = getattr(cls, "type_slug", slug)  # slopcop: ignore[no-hasattr-getattr]
        rows.append([slug, name])
    return rows
