from collections.abc import Mapping, Sequence
from typing import ClassVar

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.benchmark.task import EmptyTaskPayload, Task
from ergon_core.api.rubric import Rubric
from ergon_core.core.application.experiments import definition_writer as module
from ergon_core.core.application.experiments.definition_writer import persist_benchmark
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinitionEvaluator,
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionTaskEvaluator,
    ExperimentDefinitionWorker,
)
from ergon_core.tests.unit.runtime._test_workers import EchoSandbox, EchoWorker


class _InlineTask(Task[EmptyTaskPayload]):
    pass


class _InlineBenchmark(Benchmark):
    type_slug: ClassVar[str] = "inline-evaluator-test"

    def __init__(self, evaluators: tuple[Rubric, ...]) -> None:
        super().__init__(name="inline evals", description="inline evaluator test")
        self._evaluators = evaluators

    def build_instances(self) -> Mapping[str, Sequence[Task]]:
        return {
            "sample-1": (
                _InlineTask(
                    task_slug="root",
                    instance_key="sample-1",
                    description="root task",
                    worker=EchoWorker(name="worker", model="echo-model"),
                    sandbox=EchoSandbox(),
                    evaluators=self._evaluators,
                    evaluator_binding_keys=(),
                ),
            )
        }


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_persist_benchmark_writes_definition_rows_for_inline_evaluators(
    monkeypatch,
) -> None:
    session = _session()
    monkeypatch.setattr(module, "get_session", lambda: session)
    monkeypatch.setattr(session, "close", lambda: None)

    handle = persist_benchmark(_InlineBenchmark((Rubric(name="judge"),)))

    evaluators = session.exec(select(ExperimentDefinitionEvaluator)).all()
    bindings = session.exec(select(ExperimentDefinitionTaskEvaluator)).all()
    workers = session.exec(select(ExperimentDefinitionWorker)).all()
    assignments = session.exec(select(ExperimentDefinitionTaskAssignment)).all()

    assert [(row.binding_key, row.evaluator_type) for row in evaluators] == [("judge", "rubric")]
    assert evaluators[0].experiment_definition_id == handle.definition_id
    assert evaluators[0].snapshot_json["name"] == "judge"
    assert evaluators[0].snapshot_json["_type"].endswith(":Rubric")
    assert [row.evaluator_binding_key for row in bindings] == ["judge"]
    assert [(row.binding_key, row.worker_type, row.model_target) for row in workers] == [
        ("echo", "echo", "echo-model")
    ]
    assert [row.worker_binding_key for row in assignments] == ["echo"]


def test_persist_benchmark_rejects_duplicate_inline_evaluator_names(
    monkeypatch,
) -> None:
    session = _session()
    monkeypatch.setattr(module, "get_session", lambda: session)
    monkeypatch.setattr(session, "close", lambda: None)

    with pytest.raises(ValueError, match="Duplicate inline evaluator name"):
        persist_benchmark(_InlineBenchmark((Rubric(name="judge"), Rubric(name="judge"))))
