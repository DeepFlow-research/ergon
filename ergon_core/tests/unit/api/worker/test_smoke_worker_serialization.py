"""Every existing smoke worker must survive the public worker JSON boundary."""

import pytest

from ergon_core.api.worker import Worker
from tests.fixtures.smoke_components.benchmarks import _SMOKE_WORKERS


@pytest.mark.parametrize("slug", sorted(_SMOKE_WORKERS))
@pytest.mark.parametrize("actor_key", [None, "configured-person"])
def test_smoke_worker_json_roundtrip_preserves_actor_binding(slug, actor_key):
    worker = _SMOKE_WORKERS[slug](name=slug, model="test:none", actor_key=actor_key)
    snapshot = worker.model_dump(mode="json")
    restored = Worker.from_definition(snapshot)
    assert type(restored) is type(worker)
    assert restored.model_dump(mode="json") == snapshot
    assert restored.binding_key == (actor_key or worker.type_slug)
