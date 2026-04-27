"""Tests for ResearchRubrics benchmark registration and vanilla variant."""

import pytest
from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.task_schemas import ResearchRubricsTaskPayload
from ergon_builtins.benchmarks.researchrubrics.vanilla import ResearchRubricsVanillaBenchmark
from ergon_builtins.registry_data import BENCHMARKS, EVALUATORS, WORKERS
from ergon_core.api import Benchmark
from ergon_core.api.results import CriterionResult
from ergon_core.api.task_types import BenchmarkTask


class TestResearchRubricsBenchmarkRegistration:
    """Verify benchmark slugs resolve correctly in the registry."""

    def test_researchrubrics_ablated_registered(self):
        """researchrubrics-ablated resolves to ResearchRubricsBenchmark."""
        assert "researchrubrics-ablated" in BENCHMARKS
        assert BENCHMARKS["researchrubrics-ablated"] is ResearchRubricsBenchmark
        assert issubclass(ResearchRubricsBenchmark, Benchmark)

    def test_researchrubrics_vanilla_registered(self):
        """researchrubrics-vanilla resolves to ResearchRubricsVanillaBenchmark."""
        assert "researchrubrics-vanilla" in BENCHMARKS
        assert BENCHMARKS["researchrubrics-vanilla"] is ResearchRubricsVanillaBenchmark
        assert issubclass(ResearchRubricsVanillaBenchmark, Benchmark)

    def test_worker_slugs_registered(self):
        expected = {"researchrubrics-researcher"}
        missing = expected - set(WORKERS.keys())
        assert not missing, f"Expected worker slugs missing from registry: {missing}"

    def test_rubric_registered_by_cli_and_type_slug(self):
        assert EVALUATORS["research-rubric"] is ResearchRubricsRubric
        assert EVALUATORS["researchrubrics-rubric"] is ResearchRubricsRubric


class TestResearchRubricsVanillaBenchmark:
    """Verify the vanilla benchmark subclass."""

    def test_vanilla_type_slug(self):
        assert ResearchRubricsVanillaBenchmark.type_slug == "researchrubrics-vanilla"

    def test_vanilla_uses_scaleai_dataset(self):
        # Construction should set dataset_name to ScaleAI's
        benchmark = ResearchRubricsVanillaBenchmark(limit=1)
        assert benchmark.dataset_name == "ScaleAI/researchrubrics"
        assert benchmark.name == "researchrubrics-vanilla"


class TestResearchRubricsDatasetLoading:
    def test_load_rows_returns_typed_payloads(self, monkeypatch: pytest.MonkeyPatch):
        class FakeTrainDataset:
            def __len__(self):
                return 1

            def __getitem__(self, idx):
                assert idx == 0
                return {
                    "sample_id": "sample",
                    "domain": "quality",
                    "ablated_prompt": "Write a report.",
                    "rubrics": [
                        {"criterion": "Includes citations.", "axis": "quality", "weight": 2.0},
                    ],
                }

        monkeypatch.setattr(
            "ergon_builtins.benchmarks.researchrubrics.benchmark.load_dataset",
            lambda *args, **kwargs: {"train": FakeTrainDataset()},
        )

        rows = ResearchRubricsBenchmark(dataset_name="fake/researchrubrics")._load_rows()

        assert rows == [
            ResearchRubricsTaskPayload(
                sample_id="sample",
                domain="quality",
                ablated_prompt="Write a report.",
                rubrics=[{"criterion": "Includes citations.", "axis": "quality", "weight": 2.0}],
            )
        ]

    def test_load_rows_accepts_vanilla_prompt_field(self, monkeypatch: pytest.MonkeyPatch):
        class FakeTrainDataset:
            def __len__(self):
                return 1

            def __getitem__(self, idx):
                assert idx == 0
                return {
                    "sample_id": "vanilla-sample",
                    "domain": "planning",
                    "prompt": "Plan a day in Washington DC.",
                    "rubrics": [
                        {"criterion": "Includes a timed itinerary.", "axis": "quality", "weight": 5.0},
                    ],
                }

        monkeypatch.setattr(
            "ergon_builtins.benchmarks.researchrubrics.benchmark.load_dataset",
            lambda *args, **kwargs: {"train": FakeTrainDataset()},
        )

        rows = ResearchRubricsBenchmark(dataset_name="ScaleAI/researchrubrics")._load_rows()

        assert rows == [
            ResearchRubricsTaskPayload(
                sample_id="vanilla-sample",
                domain="planning",
                ablated_prompt="Plan a day in Washington DC.",
                rubrics=[
                    {"criterion": "Includes a timed itinerary.", "axis": "quality", "weight": 5.0}
                ],
            )
        ]


class TestResearchRubricsRubric:
    """Verify task-payload-driven rubric construction."""

    def test_can_construct_without_prebound_criteria(self):
        rubric = ResearchRubricsRubric(name="evaluator")
        task = BenchmarkTask[ResearchRubricsTaskPayload](
            task_slug="sample",
            instance_key="default",
            description="Write a report.",
            evaluator_binding_keys=("default",),
            task_payload=ResearchRubricsTaskPayload.model_validate(
                {
                    "sample_id": "sample",
                    "domain": "quality",
                    "ablated_prompt": "Write a report.",
                    "rubrics": [
                        {"criterion": "Includes citations.", "axis": "quality", "weight": 2.0},
                        {"criterion": "No unsupported claims.", "axis": "quality", "weight": -1.0},
                    ],
                }
            ),
        )

        criteria = list(rubric.criteria_for(task))

        assert [criterion.weight for criterion in criteria] == [2.0, -1.0]
        assert [type(criterion).__name__ for criterion in criteria] == [
            "ResearchRubricsJudgeCriterion",
            "ResearchRubricsJudgeCriterion",
        ]
        assert "ResearchRubrics" in criteria[0].system_prompt
        assert "Includes citations." in criteria[0].system_prompt

    def test_aggregate_uses_result_weights(self):
        rubric = ResearchRubricsRubric(name="evaluator")
        task = BenchmarkTask(
            task_slug="sample",
            instance_key="default",
            description="Write a report.",
            evaluator_binding_keys=("default",),
        )

        result = rubric.aggregate_task(
            task,
            [
                CriterionResult(name="positive", score=1.0, passed=True, weight=2.0),
                CriterionResult(name="negative", score=0.0, passed=False, weight=-1.0),
            ],
        )

        assert result.score == 1.0
        assert result.metadata == {
            "total_score": 2.0,
            "max_possible": 2.0,
            "min_possible": -1.0,
        }
