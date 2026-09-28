import pytest
from ergon_core.test_support.runtime_harness import runtime_harness


@pytest.fixture
def graph_runtime(monkeypatch):
    """A seeded in-memory sample and its task service; see ``runtime_harness``."""
    with runtime_harness(monkeypatch) as harness:
        yield harness
