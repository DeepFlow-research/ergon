from uuid import uuid4

import pytest
from ergon_core.api.handles import PersistedExperimentDefinition
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import ExperimentRecord, RunRecord
from ergon_core.core.runtime.services import experiment_launch_service as service_module
from ergon_core.core.runtime.services.experiment_launch_service import ExperimentLaunchService
from ergon_core.core.runtime.services.experiment_schemas import ExperimentRunRequest, RunAssignment


class _FakeSession:
    def __init__(self, experiment: ExperimentRecord) -> None:
        self.experiment = experiment

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *args) -> None:
        return None

    def get(self, cls, row_id):
        if cls is ExperimentRecord and row_id == self.experiment.id:
            return self.experiment
        return None

    def add(self, row) -> None:
        return None

    def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_run_experiment_creates_one_run_per_selected_sample(monkeypatch):
    experiment = ExperimentRecord(
        id=uuid4(),
        name="ci experiment",
        benchmark_type="ci-benchmark",
        sample_count=2,
        sample_selection_json={"instance_keys": ["sample-a", "sample-b"]},
        default_worker_team_json={"primary": "test-worker"},
        default_evaluator_slug=None,
        default_model_target="openai:gpt-4o",
        design_json={},
        metadata_json={},
        status="defined",
    )
    created_runs: list[RunRecord] = []
    emitted: list[tuple] = []

    def workflow_factory(
        experiment_record: ExperimentRecord,
        assignment: RunAssignment,
    ) -> PersistedExperimentDefinition:
        return PersistedExperimentDefinition(
            definition_id=uuid4(),
            benchmark_type=experiment_record.benchmark_type,
            worker_bindings=assignment.worker_team,
        )

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

    monkeypatch.setattr(service_module, "get_session", lambda: _FakeSession(experiment))
    monkeypatch.setattr(service_module, "create_run", fake_create_run)

    service = ExperimentLaunchService(
        workflow_definition_factory=workflow_factory,
        emit_workflow_started=fake_emit,
    )

    result = await service.run_experiment(ExperimentRunRequest(experiment_id=experiment.id))

    assert result.experiment_id == experiment.id
    assert result.run_ids == [run.id for run in created_runs]
    assert len(result.workflow_definition_ids) == 2
    assert [run.instance_key for run in created_runs] == ["sample-a", "sample-b"]
    assert {run.experiment_id for run in created_runs} == {experiment.id}
    assert [run.worker_team_json for run in created_runs] == [
        {"primary": "test-worker"},
        {"primary": "test-worker"},
    ]
    assert len(emitted) == 2

