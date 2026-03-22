"""Export REST and realtime contract schemas for dashboard codegen."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from h_arcane.core._internal.api.main import app
from h_arcane.core._internal.cohorts.events import CohortUpdatedEvent
from h_arcane.core.dashboard.events import (
    DashboardAgentActionCompletedEvent,
    DashboardAgentActionStartedEvent,
    DashboardSandboxClosedEvent,
    DashboardSandboxCommandEvent,
    DashboardSandboxCreatedEvent,
    DashboardTaskEvaluationUpdatedEvent,
    DashboardTaskStatusChangedEvent,
    DashboardThreadMessageCreatedEvent,
    DashboardWorkflowCompletedEvent,
    DashboardWorkflowStartedEvent,
    DashboardResourcePublishedEvent,
)


ROOT = Path(__file__).resolve().parents[1]
GENERATED_ROOT = ROOT / "arcane-dashboard" / "src" / "generated"
REST_ROOT = GENERATED_ROOT / "rest"
EVENT_SCHEMA_ROOT = GENERATED_ROOT / "events" / "schemas"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _schema_filename(model_name: str) -> str:
    return f"{model_name}.schema.json"


def export_openapi() -> None:
    """Write the FastAPI OpenAPI document used for REST codegen."""
    _write_json(REST_ROOT / "openapi.json", app.openapi())


def export_event_schemas() -> None:
    """Write JSON Schemas for all frontend-facing dashboard events."""
    event_models: list[type[BaseModel]] = [
        CohortUpdatedEvent,
        DashboardWorkflowStartedEvent,
        DashboardWorkflowCompletedEvent,
        DashboardTaskStatusChangedEvent,
        DashboardAgentActionStartedEvent,
        DashboardAgentActionCompletedEvent,
        DashboardResourcePublishedEvent,
        DashboardSandboxCreatedEvent,
        DashboardSandboxCommandEvent,
        DashboardSandboxClosedEvent,
        DashboardThreadMessageCreatedEvent,
        DashboardTaskEvaluationUpdatedEvent,
    ]

    manifest = []
    for model in event_models:
        schema_name = _schema_filename(model.__name__)
        event_name = getattr(model, "name")
        _write_json(
            EVENT_SCHEMA_ROOT / schema_name,
            model.model_json_schema(),
        )
        manifest.append(
            {
                "eventName": event_name,
                "modelName": model.__name__,
                "schemaFile": schema_name,
            }
        )

    _write_json(EVENT_SCHEMA_ROOT / "manifest.json", manifest)


def main() -> None:
    export_openapi()
    export_event_schemas()


if __name__ == "__main__":
    main()
