from collections.abc import Mapping, Sequence

from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FTaskPayload
from ergon_builtins.benchmarks.minif2f.worker_factory import (
    make_minif2f_rubric,
    make_minif2f_worker,
)
from ergon_builtins.sandboxes.lean import LeanSandbox
from ergon_core.api.benchmark import Benchmark, Task
from ergon_core.api.benchmark import TaskSpec
from ergon_core.core.application.experiments import service as service_module
from ergon_core.core.application.experiments.models import ExperimentDefineRequest
from ergon_core.core.persistence.telemetry.models import ExperimentRecord, RunRecord
from ergon_core.core.application.experiments.service import (
    ExperimentService,
)
from pydantic import BaseModel


class _Payload(BaseModel):
    value: int


class _Benchmark(Benchmark):
    type_slug = "ci-benchmark"
    task_payload_model = _Payload

    def __init__(self, *, limit: int | None = None) -> None:
        super().__init__()
        self.limit = limit

    def build_instances(self) -> Mapping[str, Sequence[TaskSpec[BaseModel]]]:
        selected = ["sample-a", "sample-b", "sample-c"][: self.limit]
        return {
            key: [
                TaskSpec[_Payload](
                    instance_key=key,
                    task_slug=f"{key}-root",
                    description=f"Task for {key}",
                    task_payload=_Payload(value=index),
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
    service = ExperimentService(benchmarks={"ci-benchmark": _Benchmark})

    result = service.define_benchmark_experiment(
        ExperimentDefineRequest(
            benchmark_slug="ci-benchmark",
            limit=2,
            default_model_target="openai:gpt-4o",
            default_worker_team={"primary": "test-worker"},
            default_evaluator_slug="test-rubric",
            evaluator_bindings={"post-root": "timing-rubric"},
            sandbox_slug="test-sandbox",
            dependency_extras=("none",),
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
    assert experiment.default_evaluator_slug == "test-rubric"
    assert experiment.design_json == {"evaluator_bindings": {"post-root": "timing-rubric"}}
    assert experiment.sandbox_slug == "test-sandbox"
    assert experiment.dependency_extras_json == {"extras": ["none"]}
    assert experiment.status == "defined"


class _MiniF2FLikeBenchmark(Benchmark):
    """Minimal benchmark that returns v2 object-bound Tasks (like MiniF2F post-PR6)."""

    type_slug = "minif2f-like"
    task_payload_model = MiniF2FTaskPayload

    def __init__(self, *, limit: int | None = None) -> None:
        super().__init__()
        self.limit = limit

    def build_instances(self) -> Mapping[str, Sequence[Task[MiniF2FTaskPayload]]]:
        keys = ["sample-a", "sample-b"][: self.limit]
        return {
            key: [
                Task[MiniF2FTaskPayload](
                    task_slug=key,
                    instance_key=key,
                    description=f"Prove theorem {key}.",
                    task_payload=MiniF2FTaskPayload(
                        name=key,
                        informal_statement=f"Prove {key}.",
                        formal_statement=f"theorem {key} : True := by",
                        header="import Mathlib\n",
                    ),
                    worker=make_minif2f_worker(),
                    sandbox=LeanSandbox(),
                    evaluators=(make_minif2f_rubric(),),
                )
            ]
            for key in keys
        }


def test_define_minif2f_like_experiment_accepts_v2_task_objects(monkeypatch):
    """ExperimentService handles benchmarks returning object-bound Task instances."""
    session = _FakeSession()
    monkeypatch.setattr(service_module, "get_session", lambda: session)
    service = ExperimentService(benchmarks={"minif2f-like": _MiniF2FLikeBenchmark})

    result = service.define_benchmark_experiment(
        ExperimentDefineRequest(
            benchmark_slug="minif2f-like",
            limit=2,
            default_model_target="openai:gpt-4o",
            default_worker_team={"primary": "solver"},
            default_evaluator_slug="minif2f-rubric",
            evaluator_bindings={},
            sandbox_slug="minif2f",
            dependency_extras=("none",),
        )
    )

    assert result.benchmark_type == "minif2f-like"
    assert result.sample_count == 2
    assert len(session.added) == 1
    assert isinstance(session.added[0], ExperimentRecord)
    assert session.added[0].status == "defined"
