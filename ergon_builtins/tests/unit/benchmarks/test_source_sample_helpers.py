from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from ergon_builtins.benchmarks.gdpeval.dataset import load_gdpeval_rows
from ergon_builtins.benchmarks.gdpeval.sample import make_gdpeval_sample
from ergon_builtins.benchmarks.gdpeval.task import GDPEvalTask
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig
from ergon_builtins.benchmarks.minif2f.dataset import load_minif2f_rows
from ergon_builtins.benchmarks.minif2f.sample import make_minif2f_sample
from ergon_builtins.benchmarks.minif2f.task import MiniF2FTask
from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem
from ergon_builtins.benchmarks.researchrubrics.dataset import load_researchrubrics_rows
from ergon_builtins.benchmarks.researchrubrics.sample import make_researchrubrics_sample
from ergon_builtins.benchmarks.researchrubrics.task import ResearchRubricsTask
from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)
from ergon_builtins.benchmarks.swebench_verified.dataset import load_swebench_rows
from ergon_builtins.benchmarks.swebench_verified.sample import make_swebench_sample
from ergon_builtins.benchmarks.swebench_verified.task import SweBenchTask
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchInstance
from ergon_core.api.criterion import CriterionOutcome
from ergon_core.api.rubric import Evaluator, TaskEvaluationResult
from ergon_core.api.task import Task
from ergon_core.test_support.task_factory import TestSandbox as SupportSandbox
from ergon_core.test_support.task_factory import TestWorker as SupportWorker


class EvaluatorStub(Evaluator):
    type_slug = "test-evaluator"

    def criteria_for(self, task: Task) -> Iterable:
        return ()

    def aggregate_task(
        self,
        task: Task,
        criterion_results: Iterable[CriterionOutcome],
    ) -> TaskEvaluationResult:
        return TaskEvaluationResult(
            task_slug=task.task_slug,
            score=1.0,
            passed=True,
            evaluator_name=self.name,
            criterion_results=list(criterion_results),
        )


class SelectableRows(list[dict[str, object]]):
    def select(self, indexes: range) -> "SelectableRows":
        return SelectableRows([self[index] for index in indexes])


def test_load_minif2f_rows_reads_jsonl(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "mini.jsonl"
    path.write_text(
        "\n".join(
            [
                "",
                json.dumps(
                    {
                        "name": "mini-1",
                        "informal_statement": "Prove one equals one.",
                        "formal_statement": "theorem mini_1 : 1 = 1 := by",
                        "header": "import Mathlib\n",
                    }
                ),
                json.dumps(
                    {
                        "name": "mini-2",
                        "informal_statement": "Prove two equals two.",
                        "formal_statement": "theorem mini_2 : 2 = 2 := by",
                        "header": "import Mathlib\n",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.minif2f.dataset.hf_hub_download",
        lambda **_: str(path),
    )

    rows = load_minif2f_rows(limit=1)

    assert [row.name for row in rows] == ["mini-1"]


def test_load_swebench_rows_normalizes_raw_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.dataset.load_dataset",
        lambda *_args, **_kwargs: SelectableRows(
            [
                {
                    "instance_id": "swe-1",
                    "repo": "org/repo",
                    "base_commit": "abcdef123456",
                    "problem_statement": "Fix the parser.",
                    "hints_text": None,
                    "version": "1.0",
                    "FAIL_TO_PASS": '["tests/test_parser.py::test_fix"]',
                    "PASS_TO_PASS": "[]",
                    "test_patch": "diff --git a/tests/test_parser.py b/tests/test_parser.py\n",
                }
            ]
        ),
    )

    rows = load_swebench_rows(limit=1)

    assert rows[0].instance_id == "swe-1"
    assert rows[0].hints_text == ""


def test_load_researchrubrics_rows_builds_payloads(monkeypatch) -> None:
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.researchrubrics.dataset.load_dataset",
        lambda *_args, **_kwargs: {
            "train": SelectableRows(
                [
                    {
                        "sample_id": "research-1",
                        "domain": "analysis",
                        "prompt": "Write a concise analysis.",
                        "rubrics": [
                            {
                                "criterion": "Has a conclusion.",
                                "axis": "Communication Quality",
                                "weight": 1.0,
                            }
                        ],
                    }
                ]
            )
        },
    )

    rows = load_researchrubrics_rows(limit=1)

    assert rows[0].sample_id == "research-1"
    assert rows[0].rubrics[0].criterion == "Has a conclusion."


def test_load_gdpeval_rows_builds_task_configs(monkeypatch) -> None:
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.dataset.load_task_ids",
        lambda **_: ["gdp-1"],
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.dataset.find_reference_files",
        lambda *_args, **_kwargs: [Path("/tmp/reference.pdf")],
    )

    rows = load_gdpeval_rows(limit=1)

    assert rows == [
        GDPTaskConfig(
            task_id="gdp-1",
            workflow_type="document_processing",
            reference_files=["/tmp/reference.pdf"],
        )
    ]


def test_make_minif2f_sample_uses_resolved_components() -> None:
    worker = SupportWorker(name="worker", model="test:none")
    evaluator = EvaluatorStub(name="judge")
    sandbox = SupportSandbox()

    sample = make_minif2f_sample(
        MiniF2FProblem(
            name="mini-1",
            informal_statement="Prove one equals one.",
            formal_statement="theorem mini_1 : 1 = 1 := by",
            header="import Mathlib\n",
        ),
        environment_name="minif2f",
        worker=worker,
        evaluators=[evaluator],
        sandbox=sandbox,
    )

    assert sample.sample_key == "mini-1"
    assert isinstance(sample.tasks[0], MiniF2FTask)
    assert sample.tasks[0].worker is worker
    assert sample.tasks[0].evaluators == (evaluator,)
    assert sample.tasks[0].sandbox is sandbox


def test_make_swebench_sample_uses_resolved_components() -> None:
    worker = SupportWorker(name="worker", model="test:none")
    evaluator = EvaluatorStub(name="judge")
    sandbox = SupportSandbox()

    sample = make_swebench_sample(
        SWEBenchInstance(
            instance_id="swe-1",
            repo="org/repo",
            base_commit="abcdef123456",
            problem_statement="Fix the parser.",
            version="1.0",
            fail_to_pass=["tests/test_parser.py::test_fix"],
            pass_to_pass=[],
            environment_setup_commit="abcdef123456",
            test_patch="diff --git a/tests/test_parser.py b/tests/test_parser.py\n",
        ),
        environment_name="swebench-verified",
        worker=worker,
        evaluators=[evaluator],
        sandbox=sandbox,
    )

    assert sample.sample_key == "swe-1"
    assert isinstance(sample.tasks[0], SweBenchTask)
    assert sample.tasks[0].worker is worker
    assert sample.tasks[0].evaluators == (evaluator,)
    assert sample.tasks[0].sandbox is sandbox


def test_make_researchrubrics_sample_uses_resolved_components() -> None:
    worker = SupportWorker(name="worker", model="test:none")
    evaluator = EvaluatorStub(name="judge")
    sandbox = SupportSandbox()

    sample = make_researchrubrics_sample(
        ResearchRubricsTaskPayload(
            sample_id="research-1",
            domain="analysis",
            prompt="Write a concise analysis.",
            rubrics=[
                RubricCriterion(
                    criterion="Has a conclusion.",
                    axis="Communication Quality",
                    weight=1.0,
                )
            ],
        ),
        environment_name="researchrubrics",
        worker=worker,
        evaluators=[evaluator],
        sandbox=sandbox,
    )

    assert sample.sample_key == "research-1"
    assert isinstance(sample.tasks[0], ResearchRubricsTask)
    assert sample.tasks[0].worker is worker
    assert sample.tasks[0].evaluators == (evaluator,)
    assert sample.tasks[0].sandbox is sandbox


def test_make_gdpeval_sample_uses_resolved_components(monkeypatch) -> None:
    worker = SupportWorker(name="worker", model="test:none")
    evaluator = EvaluatorStub(name="judge")
    sandbox = SupportSandbox()
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.sample.extract_task_description",
        lambda *_args, **_kwargs: "Process gdp-1.",
    )

    sample = make_gdpeval_sample(
        GDPTaskConfig(
            task_id="gdp-1",
            workflow_type="document_processing",
            reference_files=["/tmp/reference.pdf"],
        ),
        environment_name="gdpeval",
        worker=worker,
        evaluators=[evaluator],
        sandbox=sandbox,
    )

    assert sample.sample_key == "gdp-1"
    assert isinstance(sample.tasks[0], GDPEvalTask)
    assert sample.tasks[0].description == "Process gdp-1."
    assert sample.tasks[0].worker is worker
    assert sample.tasks[0].evaluators == (evaluator,)
    assert sample.tasks[0].sandbox is sandbox
