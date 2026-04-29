import importlib
import importlib.util


def test_inngest_infrastructure_lives_in_inngest_package() -> None:
    client_module = importlib.import_module("ergon_core.core.infrastructure.inngest.client")
    registry_spec = importlib.util.find_spec("ergon_core.core.infrastructure.inngest.registry")

    assert client_module.inngest_client is not None
    assert registry_spec is not None
