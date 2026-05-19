from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from ergon_core.core.application.experiments import launch as launch_module
from ergon_core.core.application.experiments.errors import DefinitionNotFoundError
from ergon_core.core.application.experiments.launch import launch_run
from ergon_core.core.application.experiments.models import ExperimentRunRequest
from ergon_core.core.application.experiments.handles import DefinitionHandle
from ergon_core.core.application.experiments.service import run_experiment
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import RunRecord


class _FakeSession:
    def __init__(
        self,
        definition: ExperimentDefinition | None = None,
    ) -> None:
        self.definition = definition

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *args) -> None:
        return None

    def get(self, cls, row_id):
        if (
            cls is ExperimentDefinition
            and self.definition is not None
            and row_id == self.definition.id
        ):
            return self.definition
        return None

    def add(self, row) -> None:
        return None

    def commit(self) -> None:
        return None

    def refresh(self, row) -> None:
        return None


@pytest.mark.asyncio
async def test_run_experiment_creates_one_run_per_selected_sample(monkeypatch):
    definition = ExperimentDefinition(
        id=uuid4(),
        name="ci experiment",
        benchmark_type="ci-benchmark",
        metadata_json={},
    )
    created_runs: list[RunRecord] = []
    emitted: list[tuple] = []

    def fake_create_run(definition, **kwargs):
        run = RunRecord(
            id=uuid4(),
            status=RunStatus.PENDING,
            benchmark_type=definition.benchmark_type,
            **kwargs,
        )
        created_runs.append(run)
        return run

    async def fake_emit(run_id, definition_id):
        emitted.append((run_id, definition_id))

    monkeypatch.setattr(launch_module, "get_session", lambda: _FakeSession(definition=definition))
    monkeypatch.setattr(launch_module, "create_run", fake_create_run)

    result = await run_experiment(
        ExperimentRunRequest(definition_id=definition.id),
        emit_workflow_started=fake_emit,
    )

    assert result.definition_id == definition.id
    assert result.run_ids == [created_runs[0].id]
    assert result.definition_ids == [definition.id]
    assert [run.instance_key for run in created_runs] == ["default"]
    assert {run.definition_id for run in created_runs} == {definition.id}
    assert emitted == [(created_runs[0].id, definition.id)]


@pytest.mark.asyncio
async def test_launch_run_accepts_definition_id(monkeypatch):
    """``launch_run`` materializes a run straight from ``ExperimentDefinition``.

    The real DB write inside ``create_run`` is blocked by
    ``create_run`` is mocked here so the orchestration around the
    definition-first path can be exercised without a database write.
    The orchestration around it (session lookup, emitter, result shape)
    is still exercised end-to-end against the new definition-first path.
    """

    definition = ExperimentDefinition(
        id=uuid4(),
        benchmark_type="mini",
        name="mini",
        metadata_json={},
    )
    captured: dict = {}

    def fake_create_run(handle, **kwargs):
        captured["handle"] = handle
        captured["kwargs"] = kwargs
        return RunRecord(
            id=uuid4(),
            status=RunStatus.PENDING,
            benchmark_type=handle.benchmark_type,
            definition_id=kwargs.get("definition_id"),
            worker_team_json=kwargs.get("worker_team_json") or {},
            instance_key=kwargs.get("instance_key", "default"),
        )

    monkeypatch.setattr(launch_module, "get_session", lambda: _FakeSession(definition=definition))
    monkeypatch.setattr(launch_module, "create_run", fake_create_run)

    emitter = AsyncMock()
    result = await launch_run(definition.id, emit_workflow_started=emitter)

    # Orchestration: create_run was reached with the definition handle.
    assert captured["handle"].definition_id == definition.id
    assert captured["handle"].benchmark_type == "mini"
    assert captured["kwargs"]["definition_id"] == definition.id
    assert captured["kwargs"]["instance_key"] == "default"

    # Result shape mirrors the spec.
    assert result.definition_id == definition.id
    assert result.definition_ids == [definition.id]
    assert result.run_ids
    assert len(result.run_ids) == 1

    # Emitter was awaited with the new run id and the definition id.
    emitter.assert_awaited_once_with(result.run_ids[0], definition.id)


@pytest.mark.asyncio
async def test_launch_run_raises_typed_error_when_definition_missing(monkeypatch):
    """``launch_run`` raises ``DefinitionNotFoundError`` (not a generic
    ``ValueError``) when the requested ``ExperimentDefinition`` row is
    absent. Callers depend on the typed exception to differentiate
    "missing definition" from other lookup failures without string-
    matching the message — see 07-test-strategy.md Repository layer
    standard rule 8."""

    monkeypatch.setattr(launch_module, "get_session", lambda: _FakeSession())
    with pytest.raises(DefinitionNotFoundError):
        await launch_run(uuid4(), emit_workflow_started=AsyncMock())
