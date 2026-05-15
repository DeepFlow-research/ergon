from uuid import uuid4

import pytest
from ergon_core.core.application.experiments import launch as launch_module
from ergon_core.core.application.experiments.models import ExperimentRunRequest, RunAssignment
from ergon_core.core.domain.experiments import DefinitionHandle
from ergon_core.core.application.experiments.service import ExperimentService
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import BenchmarkDefinitionRecord, RunRecord


class _FakeSession:
    def __init__(self, experiment: BenchmarkDefinitionRecord) -> None:
        self.experiment = experiment

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *args) -> None:
        return None

    def get(self, cls, row_id):
        if cls is BenchmarkDefinitionRecord and row_id == self.experiment.id:
            return self.experiment
        return None

    def add(self, row) -> None:
        return None

    def commit(self) -> None:
        return None

    def refresh(self, row) -> None:
        return None


@pytest.mark.asyncio
async def test_run_experiment_creates_one_run_per_selected_sample(monkeypatch):
    experiment = BenchmarkDefinitionRecord(
        id=uuid4(),
        name="ci experiment",
        benchmark_type="ci-benchmark",
        sample_count=2,
        sample_selection_json={"instance_keys": ["sample-a", "sample-b"]},
        default_worker_team_json={"primary": "test-worker"},
        default_evaluator_slug="test-rubric",
        default_model_target="openai:gpt-4o",
        sandbox_slug="test-sandbox",
        dependency_extras_json={"extras": ["none"]},
        design_json={},
        metadata_json={},
        status="defined",
    )
    created_runs: list[RunRecord] = []
    emitted: list[tuple] = []

    def workflow_factory(
        experiment_record: BenchmarkDefinitionRecord,
        assignment: RunAssignment,
    ) -> DefinitionHandle:
        return DefinitionHandle(
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

    monkeypatch.setattr(launch_module, "get_session", lambda: _FakeSession(experiment))
    monkeypatch.setattr(launch_module, "create_run", fake_create_run)

    service = ExperimentService(
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
    assert [run.evaluator_slug for run in created_runs] == ["test-rubric", "test-rubric"]
    assert [run.sandbox_slug for run in created_runs] == ["test-sandbox", "test-sandbox"]
    assert [run.dependency_extras_json for run in created_runs] == [
        {"extras": ["none"]},
        {"extras": ["none"]},
    ]
    assert len(emitted) == 2
