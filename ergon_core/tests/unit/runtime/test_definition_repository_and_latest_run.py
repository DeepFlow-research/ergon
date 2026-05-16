"""Unit tests for DefinitionRepository tag helpers and latest_run_for_definition."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from ergon_core.core.application.experiments.repository import DefinitionRepository
from ergon_core.core.application.workflows import runs as runs_module
from ergon_core.core.application.workflows.runs import latest_run_for_definition
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import BenchmarkDefinitionRecord, RunRecord
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


# ---------------------------------------------------------------------------
# Shared session factory
# ---------------------------------------------------------------------------


@pytest.fixture()
def session_factory():
    _ = BenchmarkDefinitionRecord
    _ = ExperimentDefinition
    _ = RunGraphNode
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _get_session() -> Session:
        return Session(engine)

    return _get_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bdr(*, experiment: str | None = None) -> BenchmarkDefinitionRecord:
    return BenchmarkDefinitionRecord(
        id=uuid4(),
        name="ci experiment",
        benchmark_type="ci-benchmark",
        sample_count=1,
        experiment=experiment,
    )


def _run(
    *,
    experiment_id: object,
    workflow_definition_id: object,
    created_at: datetime | None = None,
) -> RunRecord:
    return RunRecord(
        id=uuid4(),
        experiment_id=experiment_id,
        workflow_definition_id=workflow_definition_id,
        benchmark_type="ci-benchmark",
        instance_key="k",
        worker_team_json={},
        status=RunStatus.PENDING,
        created_at=created_at or datetime(2026, 1, 1, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# DefinitionRepository.list_by_experiment_tag
# ---------------------------------------------------------------------------


def test_list_by_experiment_tag_returns_matching_records(session_factory) -> None:
    repo = DefinitionRepository()
    tagged = _bdr(experiment="exp-alpha")
    untagged = _bdr(experiment=None)
    other = _bdr(experiment="exp-beta")

    with session_factory() as session:
        session.add(tagged)
        session.add(untagged)
        session.add(other)
        session.commit()

        results = repo.list_by_experiment_tag(session, "exp-alpha")

    assert len(results) == 1
    assert results[0].id == tagged.id


def test_list_by_experiment_tag_excludes_non_matching(session_factory) -> None:
    repo = DefinitionRepository()
    a = _bdr(experiment="exp-alpha")
    b = _bdr(experiment="exp-alpha")
    c = _bdr(experiment="exp-beta")

    with session_factory() as session:
        session.add(a)
        session.add(b)
        session.add(c)
        session.commit()

        results = repo.list_by_experiment_tag(session, "exp-alpha")
        result_ids = {r.id for r in results}
        c_id = c.id

    assert result_ids == {a.id, b.id}
    assert c_id not in result_ids


def test_list_by_experiment_tag_empty_when_no_match(session_factory) -> None:
    repo = DefinitionRepository()
    with session_factory() as session:
        session.add(_bdr(experiment="other-tag"))
        session.commit()

        results = repo.list_by_experiment_tag(session, "missing-tag")

    assert results == []


# ---------------------------------------------------------------------------
# DefinitionRepository.distinct_experiment_tags
# ---------------------------------------------------------------------------


def test_distinct_experiment_tags_returns_unique_non_null_tags(session_factory) -> None:
    repo = DefinitionRepository()

    with session_factory() as session:
        session.add(_bdr(experiment="alpha"))
        session.add(_bdr(experiment="alpha"))  # duplicate — should appear once
        session.add(_bdr(experiment="beta"))
        session.add(_bdr(experiment=None))  # null — must be excluded
        session.commit()

        tags = repo.distinct_experiment_tags(session)

    assert sorted(tags) == ["alpha", "beta"]


def test_distinct_experiment_tags_excludes_null(session_factory) -> None:
    repo = DefinitionRepository()

    with session_factory() as session:
        session.add(_bdr(experiment=None))
        session.add(_bdr(experiment=None))
        session.commit()

        tags = repo.distinct_experiment_tags(session)

    assert tags == []


def test_distinct_experiment_tags_empty_table(session_factory) -> None:
    repo = DefinitionRepository()

    with session_factory() as session:
        tags = repo.distinct_experiment_tags(session)

    assert tags == []


# ---------------------------------------------------------------------------
# latest_run_for_definition
# ---------------------------------------------------------------------------


def test_latest_run_for_definition_returns_most_recent(monkeypatch, session_factory) -> None:
    definition_id = uuid4()
    experiment_id = uuid4()

    now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    older = _run(
        experiment_id=experiment_id,
        workflow_definition_id=definition_id,
        created_at=now - timedelta(hours=1),
    )
    newest = _run(
        experiment_id=experiment_id,
        workflow_definition_id=definition_id,
        created_at=now,
    )
    newest_id = newest.id

    with session_factory() as session:
        session.add(
            BenchmarkDefinitionRecord(
                id=experiment_id,
                name="ci",
                benchmark_type="ci-benchmark",
                sample_count=1,
            )
        )
        session.add(
            ExperimentDefinition(
                id=definition_id,
                benchmark_type="ci-benchmark",
                name="ci",
                metadata_json={},
            )
        )
        session.add(older)
        session.add(newest)
        session.commit()

    monkeypatch.setattr(runs_module, "get_session", session_factory)

    result = latest_run_for_definition(definition_id)

    assert result is not None
    assert result.id == newest_id


def test_latest_run_for_definition_ignores_other_definitions(monkeypatch, session_factory) -> None:
    def_a = uuid4()
    def_b = uuid4()
    experiment_id = uuid4()

    now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    run_a = _run(experiment_id=experiment_id, workflow_definition_id=def_a, created_at=now)
    run_b = _run(
        experiment_id=experiment_id,
        workflow_definition_id=def_b,
        created_at=now + timedelta(hours=1),
    )
    run_a_id = run_a.id

    with session_factory() as session:
        session.add(
            BenchmarkDefinitionRecord(
                id=experiment_id,
                name="ci",
                benchmark_type="ci-benchmark",
                sample_count=1,
            )
        )
        session.add(
            ExperimentDefinition(
                id=def_a,
                benchmark_type="ci-benchmark",
                name="ci-a",
                metadata_json={},
            )
        )
        session.add(
            ExperimentDefinition(
                id=def_b,
                benchmark_type="ci-benchmark",
                name="ci-b",
                metadata_json={},
            )
        )
        session.add(run_a)
        session.add(run_b)
        session.commit()

    monkeypatch.setattr(runs_module, "get_session", session_factory)

    result = latest_run_for_definition(def_a)

    assert result is not None
    assert result.id == run_a_id


def test_latest_run_for_definition_returns_none_when_no_runs(monkeypatch, session_factory) -> None:
    definition_id = uuid4()

    monkeypatch.setattr(runs_module, "get_session", session_factory)

    result = latest_run_for_definition(definition_id)

    assert result is None
