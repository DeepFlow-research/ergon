from collections.abc import Mapping, Sequence

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.core.persistence.telemetry.models import ExperimentRecord, RunRecord
from ergon_core.core.runtime.services import experiment_definition_service as service_module
from ergon_core.core.runtime.services.experiment_definition_service import (
    ExperimentDefinitionService,
)
from ergon_core.core.runtime.services.experiment_schemas import ExperimentDefineRequest
from pydantic import BaseModel


class _Payload(BaseModel):
    value: int


class _Benchmark(Benchmark):
    type_slug = "ci-benchmark"
    task_payload_model = _Payload

    def __init__(self, *, limit: int | None = None) -> None:
        super().__init__()
        self.limit = limit

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask[BaseModel]]]:
        selected = ["sample-a", "sample-b", "sample-c"][: self.limit]
        return {
            key: [
                BenchmarkTask(
                    instance_key=key,
                    task_slug=f"{key}-root",
                    description=f"Task for {key}",
                    payload=_Payload(value=index),
                )
            ]
            for index, key in enumerate(selected)
        }


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


def test_define_benchmark_experiment_creates_experiment_record_without_runs(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(service_module, "get_session", lambda: session)
    service = ExperimentDefinitionService(benchmarks={"ci-benchmark": _Benchmark})

    result = service.define_benchmark_experiment(
        ExperimentDefineRequest(
            benchmark_slug="ci-benchmark",
            limit=2,
            default_model_target="openai:gpt-4o",
            default_worker_team={"primary": "test-worker"},
            default_evaluator_slug=None,
        )
    )

    assert result.benchmark_type == "ci-benchmark"
    assert result.sample_count == 2
    assert result.selected_samples == ["sample-a", "sample-b"]
    assert len(session.added) == 1
    assert isinstance(session.added[0], ExperimentRecord)
    assert not any(isinstance(row, RunRecord) for row in session.added)

    experiment = session.added[0]
    assert experiment.name.startswith("ci-benchmark n=2")
    assert experiment.cohort_id is None
    assert experiment.sample_selection_json == {"instance_keys": ["sample-a", "sample-b"]}
    assert experiment.default_worker_team_json == {"primary": "test-worker"}
    assert experiment.default_model_target == "openai:gpt-4o"
    assert experiment.default_evaluator_slug is None
    assert experiment.status == "defined"
