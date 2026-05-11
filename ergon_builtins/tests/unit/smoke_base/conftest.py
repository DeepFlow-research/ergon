"""Keep smoke fixture registry overrides local to each smoke test."""

from collections.abc import Iterator

import pytest
from ergon_core.api.registry import registry


@pytest.fixture(autouse=True)
def restore_component_registry() -> Iterator[None]:
    workers = dict(registry.workers)
    benchmarks = dict(registry.benchmarks)
    evaluators = dict(registry.evaluators)
    sandbox_managers = dict(registry.sandbox_managers)
    component_refs = dict(registry.component_refs)

    yield

    registry.workers = workers
    registry.benchmarks = benchmarks
    registry.evaluators = evaluators
    registry.sandbox_managers = sandbox_managers
    registry.component_refs = component_refs
