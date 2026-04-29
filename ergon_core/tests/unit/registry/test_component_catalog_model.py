import pytest

from ergon_core.core.persistence.components.models import ComponentCatalogEntry


def test_component_catalog_entry_round_trips_metadata() -> None:
    entry = ComponentCatalogEntry(
        kind="worker",
        slug="training-stub",
        module="ergon_builtins.shared.workers.training_stub_worker",
        qualname="TrainingStubWorker",
        package="ergon-builtins",
        metadata_json={"description": "offline worker"},
    )

    assert entry.parsed_metadata() == {"description": "offline worker"}


def test_component_catalog_entry_rejects_invalid_kind() -> None:
    with pytest.raises(ValueError, match="kind must be one of"):
        ComponentCatalogEntry(
            kind="not-a-kind",
            slug="bad",
            module="pkg.mod",
            qualname="Thing",
        )
