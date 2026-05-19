"""ResearchRubrics v2 authoring shape: task JSON definition + reconstruction.

PR 10b: assert ``ResearchRubricsBenchmark`` returns ``Task`` instances
that serialize to the object-bound JSON shape (``_type`` on worker,
sandbox, every evaluator entry, no ``_legacy`` marker) and that the
snapshot round-trips through ``Task.from_definition``.

The benchmark's ``build_instances`` hits HuggingFace by default; we
monkeypatch ``_load_rows`` so the unit test stays offline.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.researchrubrics.benchmark import (
    ResearchRubricsBenchmark,
)
from ergon_builtins.benchmarks.researchrubrics.sandbox import ResearchE2BSandbox
from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)
from ergon_builtins.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit
from ergon_builtins.benchmarks.researchrubrics.worker_factory import (
    make_research_rubric,
    make_research_worker,
)
from ergon_core.api.benchmark.task import Task


FAKE_PAYLOAD = ResearchRubricsTaskPayload(
    sample_id="rr-sample-1",
    domain="quality",
    prompt="Write a short report on the value of unit-test fixtures.",
    rubrics=[
        RubricCriterion(
            criterion="Includes a Findings section.",
            axis="Communication Quality",
            weight=2.0,
        ),
        RubricCriterion(
            criterion="Cites at least one source.",
            axis="References & Citation Quality",
            weight=1.0,
        ),
    ],
)


def _fake_load_rows(self):
    return [FAKE_PAYLOAD]


# ── Component-level serialization sanity ────────────────────────────────


def test_research_rubrics_toolkit_round_trips_through_json() -> None:
    tk = ResearchRubricsToolkit(judge_model="openai:gpt-4o-mini", max_search_calls=8)
    serialized = tk.model_dump(mode="json")
    assert serialized["_type"].endswith(":ResearchRubricsToolkit")
    rebuilt = ResearchRubricsToolkit.model_validate(serialized)
    assert rebuilt.judge_model == "openai:gpt-4o-mini"
    assert rebuilt.max_search_calls == 8


def test_research_e2b_sandbox_serializes_with_type_discriminator() -> None:
    sb = ResearchE2BSandbox()
    serialized = sb.model_dump(mode="json")
    assert serialized["_type"].endswith(":ResearchE2BSandbox")


def test_make_research_worker_serializes_with_nested_toolkit_type() -> None:
    worker = make_research_worker()
    serialized = worker.model_dump(mode="json")
    assert serialized["_type"].endswith(":ReActWorker"), serialized["_type"]
    toolkit_json = serialized.get("toolkit")
    assert toolkit_json is not None, "toolkit must be present in worker JSON"
    assert toolkit_json["_type"].endswith(":ResearchRubricsToolkit"), toolkit_json["_type"]


def test_make_research_rubric_serializes_with_type_discriminator() -> None:
    rubric = make_research_rubric()
    serialized = rubric.model_dump(mode="json")
    assert serialized["_type"].endswith(":ResearchRubricsRubric"), serialized["_type"]


# ── Task-level v2 shape ─────────────────────────────────────────────────


def test_research_rubrics_task_json_has_v2_object_bound_shape() -> None:
    """A ResearchRubrics Task serializes to the v2 object-bound shape."""
    with patch.object(ResearchRubricsBenchmark, "_load_rows", _fake_load_rows):
        benchmark = ResearchRubricsBenchmark(limit=1)
        task = benchmark.build_instances()["default"][0]

    task_json = task.model_dump(mode="json")

    assert task_json["worker"]["_type"].endswith(":ReActWorker")
    assert task_json["worker"]["toolkit"]["_type"].endswith(":ResearchRubricsToolkit")
    assert task_json["sandbox"]["_type"].endswith(":ResearchE2BSandbox")
    assert task_json["evaluators"], "evaluators must persist"
    assert all(ev.get("_type") for ev in task_json["evaluators"]), (
        "every evaluator entry must carry a `_type` discriminator"
    )
    assert task_json["evaluators"][0]["_type"].endswith(":ResearchRubricsRubric")
    assert "_legacy" not in task_json, (
        "ResearchRubrics is now object-bound; the _legacy bridge marker should be absent"
    )


def test_research_rubric_judge_model_round_trips_through_evaluator_json() -> None:
    """Per plan Task 7 Step 2: judge model field must round-trip in JSON.

    ResearchRubrics rubrics materialise per-task ``ResearchRubricsJudgeCriterion``
    instances from the task payload at criteria-resolution time.  Each
    criterion's ``judge_model`` field is a first-class Pydantic field, so
    the value survives a ``model_dump`` / ``model_validate`` round trip
    even though the rubric body itself only serializes the authoring
    config.
    """
    from ergon_builtins.benchmarks.researchrubrics.criteria.judge import (
        ResearchRubricsJudgeCriterion,
    )

    criterion = ResearchRubricsJudgeCriterion(
        slug="includes_findings",
        rubric=RubricCriterion(
            criterion="Includes a Findings section.",
            axis="Communication Quality",
            weight=2.0,
        ),
        judge_model="openai:gpt-4o-mini",
    )
    serialized = criterion.model_dump(mode="json")
    assert serialized["judge_model"] == "openai:gpt-4o-mini", (
        f"judge_model must round-trip in JSON; got {serialized.get('judge_model')!r}"
    )
    assert serialized.get("rubric_text"), "rubric_text must round-trip alongside judge_model"

    rebuilt = ResearchRubricsJudgeCriterion.model_validate(serialized)
    assert rebuilt.judge_model == "openai:gpt-4o-mini"
    assert rebuilt.rubric_text == "Includes a Findings section."


def test_research_rubrics_benchmark_accepts_custom_worker_factory() -> None:
    """The benchmark uses the worker_factory passed to its constructor."""
    from unittest.mock import MagicMock

    sentinel_worker = make_research_worker()
    sentinel_worker.name = "sentinel"
    factory = MagicMock(return_value=sentinel_worker)

    with patch.object(ResearchRubricsBenchmark, "_load_rows", _fake_load_rows):
        benchmark = ResearchRubricsBenchmark(worker_factory=factory, limit=1)
        tasks = list(benchmark.build_instances().values())[0]

    assert tasks[0].worker is sentinel_worker
    factory.assert_called_once()


@pytest.mark.asyncio
async def test_research_rubrics_task_json_round_trips_through_from_definition() -> None:
    """Definition JSON inflates back to a Task whose sandbox is ResearchE2BSandbox."""
    with patch.object(ResearchRubricsBenchmark, "_load_rows", _fake_load_rows):
        benchmark = ResearchRubricsBenchmark(limit=1)
        task = benchmark.build_instances()["default"][0]

    task_json = task.model_dump(mode="json")

    rebuilt = await Task.from_definition(task_json, task_id=uuid4())

    assert rebuilt.worker is not None
    assert rebuilt.sandbox is not None
    assert isinstance(rebuilt.sandbox, type(task.sandbox))
    assert rebuilt.evaluators
    assert all(ev is not None for ev in rebuilt.evaluators)
