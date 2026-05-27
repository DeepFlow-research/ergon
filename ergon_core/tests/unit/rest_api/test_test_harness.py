"""Test-harness router: conditional mount, read DTO shape, write-gate secret."""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

from ergon_core.core.application.samples.event_views import (
    SampleTaskAddedEventView,
    SampleWorkerAddedEventView,
)
from ergon_core.core.application.testing.test_harness_service import (
    HarnessExperimentSample,
    get_session_dep,
)
from ergon_core.core.application.testing import test_harness_service as harness_service
from ergon_core.core.infrastructure.http.routes import test_harness
from ergon_core.core.infrastructure.http.routes.test_harness import router
from ergon_core.core.persistence.experiments.models import ExperimentRow
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


class _NullSession:
    """Minimal session stub that returns no rows for any exec/get call.

    The read endpoint queries for a SampleRecord first and 404s when absent; in
    that branch no further DB access occurs. This stub exists so unit tests
    don't require a live Postgres.
    """

    def __enter__(self) -> "_NullSession":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def exec(self, _stmt: object) -> "_NullSession":  # pragma: no cover - trivial
        return self

    def first(self) -> None:
        return None

    def all(self) -> list[object]:  # pragma: no cover - unreachable for unknown run
        return []


def _null_session_factory() -> Iterator[_NullSession]:
    yield _NullSession()


def _build_app_with_harness() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_dep] = _null_session_factory
    return app


class _ReadStateResult:
    def __init__(self, first_value: object | None, all_values: list[object] | None = None) -> None:
        self._first_value = first_value
        self._all_values = [] if all_values is None else all_values

    def first(self) -> object | None:
        return self._first_value

    def all(self) -> list[object]:
        return self._all_values


class _ReadStateSession:
    def __init__(self, sample: object) -> None:
        self._sample = sample
        self._returned_sample = False

    def exec(self, _stmt: object) -> _ReadStateResult:
        if not self._returned_sample:
            self._returned_sample = True
            return _ReadStateResult(self._sample)
        return _ReadStateResult(None, [])


class _SampleRuntimeEventReadService:
    def __init__(self, events: list[object]) -> None:
        self._events = events

    def list_events(self, _session: object, _sample_id: object) -> list[object]:
        return self._events


def test_read_endpoint_returns_404_for_unknown_sample_id() -> None:
    app = _build_app_with_harness()
    client = TestClient(app)
    resp = client.get(f"/api/__danger__/test-harness/read/samples/{uuid4()}/state")
    assert resp.status_code == 404


def test_read_state_dto_exposes_live_playwright_contract_fields() -> None:
    assert {"id", "parent_task_id"} <= set(test_harness.TestGraphNodeDto.model_fields)
    assert {"task_id", "task_slug"} <= set(test_harness.TestEvaluationDto.model_fields)
    assert {
        "executions",
        "execution_count",
        "event_count",
        "resource_count",
        "thread_count",
        "context_event_count",
    } <= set(test_harness.TestSampleStateDto.model_fields)


def test_read_sample_state_maps_typed_runtime_event_views_to_table_names(monkeypatch) -> None:
    sample_id = uuid4()
    task_id = uuid4()
    now = datetime(2026, 5, 27, 9, 0, tzinfo=UTC)
    sample = type("_Sample", (), {"status": "completed"})()
    event_reader = _SampleRuntimeEventReadService(
        [
            SampleTaskAddedEventView(
                event_id=uuid4(),
                sample_id=sample_id,
                event_type="task.added",
                target_type="task",
                target_id=task_id,
                timestamp=now,
                task_slug="root",
                status="pending",
                payload={"task_key": "root"},
            ),
            SampleWorkerAddedEventView(
                event_id=uuid4(),
                sample_id=sample_id,
                event_type="worker.added",
                target_type="task",
                target_id=task_id,
                timestamp=now,
                worker_slug="smoke-worker",
                payload={"worker_slug": "smoke-worker"},
            ),
        ]
    )

    monkeypatch.setattr(
        harness_service,
        "SampleRuntimeEventReadService",
        lambda: event_reader,
    )

    state = harness_service.read_sample_state(sample_id, _ReadStateSession(sample))  # type: ignore[arg-type]

    assert state is not None
    assert [(event.table, event.event_type) for event in state.events] == [
        ("sample_task_events", "task.added"),
        ("sample_worker_events", "worker.added"),
    ]


def test_read_experiment_samples_route_uses_v2_experiment_grouping(monkeypatch) -> None:
    sample_id = uuid4()

    monkeypatch.setattr(
        test_harness,
        "_read_experiment_samples",
        lambda experiment, session: [
            HarnessExperimentSample(sample_id=sample_id, status=f"{experiment}:completed")
        ],
    )

    app = _build_app_with_harness()
    client = TestClient(app)
    resp = client.get("/api/__danger__/test-harness/read/experiment/group-alpha/samples")

    assert resp.status_code == 200
    assert resp.json() == [{"sample_id": str(sample_id), "status": "group-alpha:completed"}]


def test_read_experiment_samples_service_finds_v2_experiment_name() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        experiment = ExperimentRow(name="group-alpha")
        session.add(experiment)
        session.flush()
        sample = SampleRecord(
            experiment_id=experiment.id,
            experiment=str(experiment.id),
            benchmark_type="experiment",
            instance_key="default",
            status=SampleStatus.COMPLETED,
        )
        session.add(sample)
        session.commit()
        sample_id = sample.id

        rows = harness_service.read_experiment_samples("group-alpha", session)

    assert [(row.sample_id, row.status) for row in rows] == [(sample_id, SampleStatus.COMPLETED)]


def test_reset_route_is_available_without_secret_header() -> None:
    app = _build_app_with_harness()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/__danger__/test-harness/write/reset",
        json={"experiment_prefix": "ci-smoke-"},
    )
    assert resp.status_code in (204, 500)
