from uuid import uuid4

from ergon_core.core.application.experiments.handles import DefinitionHandle
from ergon_core.core.application.runtime import samples as sample_service
from ergon_core.core.persistence.shared.enums import SampleStatus


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


def test_create_definition_backed_sample_records_assignment(monkeypatch):
    session = _FakeSession()
    definition_id = uuid4()
    definition = DefinitionHandle(
        definition_id=definition_id,
        benchmark_type="ci-benchmark",
        worker_bindings={"primary": "test-worker"},
        evaluator_bindings={"primary": "test-evaluator"},
    )

    monkeypatch.setattr(sample_service, "get_session", lambda: session)

    sample = sample_service.create_definition_backed_sample(
        definition,
        definition_id=definition_id,
        instance_key="sample-1",
        worker_team_json={"primary": "test-worker"},
        evaluator_slug="test-evaluator",
        model_target="openai:gpt-4o",
        assignment_json={"arm_key": "default"},
        seed=123,
    )

    assert session.added == [sample]
    assert sample.definition_id == definition_id
    assert sample.benchmark_type == "ci-benchmark"
    assert sample.instance_key == "sample-1"
    assert sample.worker_team_json == {"primary": "test-worker"}
    assert sample.evaluator_slug == "test-evaluator"
    assert sample.model_target == "openai:gpt-4o"
    assert sample.assignment_json == {"arm_key": "default"}
    assert sample.seed == 123
    assert sample.status == SampleStatus.PENDING
