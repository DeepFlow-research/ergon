"""Registry discovery backed by the process-local catalog."""

from ergon_core.api.registry import registry


def list_benchmarks() -> list[list[str]]:
    rows = []
    for slug, cls in sorted(registry.benchmarks.items()):
        desc = cls.__doc__ or ""
        rows.append([slug, cls.type_slug, desc.strip().split("\n")[0]])
    return rows


def list_workers() -> list[list[str]]:
    return [[slug, cls.type_slug] for slug, cls in sorted(registry.workers.items())]


def list_evaluators() -> list[list[str]]:
    return [[slug, cls.type_slug] for slug, cls in sorted(registry.evaluators.items())]
