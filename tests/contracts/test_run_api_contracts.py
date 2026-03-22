"""Contract tests for the typed run detail API boundary."""

from __future__ import annotations

from h_arcane.core._internal.api.main import app
from h_arcane.core._internal.api.run_schemas import RunSnapshotDto
from h_arcane.core._internal.api.runs import build_run_snapshot
from tests.utils.cohort_helpers import create_experiment, create_run


def test_openapi_exposes_typed_run_snapshot_response() -> None:
    openapi = app.openapi()

    response_schema = openapi["paths"]["/runs/{run_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    assert response_schema["$ref"] == "#/components/schemas/RunSnapshotDto"
    assert "RunSnapshotDto" in openapi["components"]["schemas"]


def test_build_run_snapshot_emits_object_maps_for_frontend(clean_db) -> None:
    experiment = create_experiment("smoke_test", "typed-run-snapshot")
    run = create_run(experiment.id)

    snapshot = build_run_snapshot(run.id)

    assert snapshot is not None
    assert isinstance(snapshot, RunSnapshotDto)
    assert isinstance(snapshot.tasks, dict)
    assert snapshot.root_task_id

    payload = snapshot.model_dump(mode="json", by_alias=True)
    task_id = next(iter(payload["tasks"]))

    assert isinstance(payload["tasks"], dict)
    assert payload["actionsByTask"] == {}
    assert payload["resourcesByTask"] == {}
    assert payload["executionsByTask"] == {}
    assert payload["sandboxesByTask"] == {}
    assert payload["evaluationsByTask"] == {}
    assert isinstance(payload["tasks"][task_id], dict)
    assert payload["tasks"][task_id]["status"] == "pending"
