import pytest

from ergon_core.api.registry import registry
from ergon_core.core.domain.experiments import WorkerSpec


def test_worker_spec_unknown_worker_lists_registered_workers() -> None:
    original_workers = dict(registry.workers)
    registry.workers.clear()
    registry.workers["known-worker"] = object
    try:
        spec = WorkerSpec(worker_slug="missing-worker", name="primary", model="stub:constant")

        with pytest.raises(
            ValueError,
            match="Unknown worker slug 'missing-worker'; registered workers: known-worker",
        ):
            spec.validate_spec()
    finally:
        registry.workers.clear()
        registry.workers.update(original_workers)
