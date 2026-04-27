from uuid import uuid4

from ergon_core.api.handles import PersistedExperimentDefinition
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.runtime.services import run_service


class _FakeSession:
    def __init__(self) -> None:
        self.added = []

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *args) -> None:
        return None

    def add(self, row) -> None:
        self.added.append(row)

    def commit(self) -> None:
        return None

    def refresh(self, row) -> None:
        return None


def test_create_run_requires_experiment_identity_and_records_workflow_assignment(monkeypatch):
    session = _FakeSession()
    experiment_id = uuid4()
    workflow_definition_id = uuid4()
    definition = PersistedExperimentDefinition(
        definition_id=workflow_definition_id,
        benchmark_type="ci-benchmark",
        worker_bindings={"primary": "test-worker"},
        evaluator_bindings={"primary": "test-evaluator"},
    )

    monkeypatch.setattr(run_service, "get_session", lambda: session)

    run = run_service.create_run(
        definition,
        experiment_id=experiment_id,
        workflow_definition_id=workflow_definition_id,
        instance_key="sample-1",
        worker_team_json={"primary": "test-worker"},
        evaluator_slug="test-evaluator",
        model_target="openai:gpt-4o",
        assignment_json={"arm_key": "default"},
        seed=123,
    )

    assert session.added == [run]
    assert run.experiment_id == experiment_id
    assert run.workflow_definition_id == workflow_definition_id
    assert run.benchmark_type == "ci-benchmark"
    assert run.instance_key == "sample-1"
    assert run.worker_team_json == {"primary": "test-worker"}
    assert run.evaluator_slug == "test-evaluator"
    assert run.model_target == "openai:gpt-4o"
    assert run.assignment_json == {"arm_key": "default"}
    assert run.seed == 123
    assert run.status == RunStatus.PENDING

