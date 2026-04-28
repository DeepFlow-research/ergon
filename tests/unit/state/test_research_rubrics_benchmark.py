"""Tests for ResearchRubrics benchmark registration and vanilla variant."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from ergon_builtins.benchmarks.researchrubrics.judge_criterion import (
    ResearchRubricsJudgeCriterion,
)
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)
from ergon_builtins.benchmarks.researchrubrics.vanilla import ResearchRubricsVanillaBenchmark
from ergon_builtins.registry_data import BENCHMARKS, EVALUATORS, WORKERS
from ergon_core.api import Benchmark
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import CriterionResult, WorkerOutput
from ergon_core.core.runtime.resources import RunResourceKind, RunResourceView
from ergon_core.api.task_types import BenchmarkTask


class _FakeJudgeRuntime:
    def __init__(self, resources: list[RunResourceView], blobs: dict[str, bytes]) -> None:
        self._resources = resources
        self._blobs = blobs
        self.listed_task_execution_ids: list[object] = []
        self.read_resource_ids: list[str] = []

    async def list_resources(self, task_execution_id=None):
        self.listed_task_execution_ids.append(task_execution_id)
        return self._resources

    async def read_resource_by_id(self, resource_id):
        self.read_resource_ids.append(str(resource_id))
        return self._blobs[str(resource_id)]


def _resource_view(
    *,
    kind: RunResourceKind,
    name: str,
    sandbox_origin: str,
    text: str,
) -> tuple[RunResourceView, bytes]:
    resource_id = uuid4()
    return (
        RunResourceView(
            id=resource_id,
            run_id=uuid4(),
            task_execution_id=uuid4(),
            kind=kind,
            name=name,
            mime_type="text/markdown",
            file_path=f"/durable/{resource_id}",
            size_bytes=len(text.encode()),
            content_hash=None,
            error=None,
            metadata={"sandbox_origin": sandbox_origin},
            created_at=datetime.now(UTC),
        ),
        text.encode(),
    )


class TestResearchRubricsBenchmarkRegistration:
    """Verify benchmark slugs resolve correctly in the registry."""

    def test_researchrubrics_registered(self):
        """researchrubrics resolves to the official ScaleAI dataset benchmark."""
        assert BENCHMARKS["researchrubrics"] is ResearchRubricsBenchmark
        assert set(BENCHMARKS) == {"gdpeval", "researchrubrics", "researchrubrics-vanilla"}
        assert issubclass(ResearchRubricsBenchmark, Benchmark)

    def test_researchrubrics_vanilla_registered(self):
        """researchrubrics-vanilla resolves to ResearchRubricsVanillaBenchmark."""
        assert "researchrubrics-vanilla" in BENCHMARKS
        assert BENCHMARKS["researchrubrics-vanilla"] is ResearchRubricsVanillaBenchmark
        assert issubclass(ResearchRubricsVanillaBenchmark, Benchmark)

    def test_worker_slugs_registered(self):
        expected = {
            "researchrubrics-researcher",
            "researchrubrics-workflow-cli-react",
        }
        missing = expected - set(WORKERS.keys())
        assert not missing, f"Expected worker slugs missing from registry: {missing}"

    def test_rubric_registered_by_cli_and_type_slug(self):
        assert EVALUATORS["research-rubric"] is ResearchRubricsRubric
        assert EVALUATORS["researchrubrics-rubric"] is ResearchRubricsRubric

    def test_manager_composition_registers_specialist_bindings(self, monkeypatch):
        from ergon_cli.composition import build_experiment

        class FakeTrainDataset:
            def __len__(self):
                return 1

            def __getitem__(self, idx):
                assert idx == 0
                return {
                    "sample_id": "sample",
                    "domain": "quality",
                    "prompt": "Write a report.",
                    "rubrics": [
                        {"criterion": "Includes citations.", "axis": "quality", "weight": 2.0},
                    ],
                }

            def select(self, indexes):
                assert list(indexes) == [0]
                return self

        monkeypatch.setattr(
            "ergon_builtins.benchmarks.researchrubrics.benchmark.load_dataset",
            lambda *args, **kwargs: {"train": FakeTrainDataset()},
        )

        experiment = build_experiment(
            "researchrubrics",
            model="stub:constant",
            worker_slug="researchrubrics-workflow-cli-react",
            evaluator_slug="research-rubric",
            limit=1,
        )

        assert set(experiment.workers) == {
            "manager",
            "researchrubrics-researcher",
            "researchrubrics-workflow-cli-react",
        }
        assert experiment.assignments == {"manager": ["sample"]}


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
                    "prompt": "Write a report.",
                    "rubrics": [
                        {"criterion": "Includes citations.", "axis": "quality", "weight": 2.0},
                    ],
                }

        monkeypatch.setattr(
            "ergon_builtins.benchmarks.researchrubrics.benchmark.load_dataset",
            lambda *args, **kwargs: {"train": FakeTrainDataset()},
        )

        rows = ResearchRubricsBenchmark()._load_rows()

        assert rows == [
            ResearchRubricsTaskPayload(
                sample_id="sample",
                domain="quality",
                prompt="Write a report.",
                rubrics=[{"criterion": "Includes citations.", "axis": "quality", "weight": 2.0}],
            )
        ]

    def test_default_dataset_is_official_scaleai_dataset(self):
        benchmark = ResearchRubricsBenchmark(limit=1)

        assert benchmark.dataset_name == "ScaleAI/researchrubrics"


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
                    "prompt": "Write a report.",
                    "rubrics": [
                        {"criterion": "Includes citations.", "axis": "quality", "weight": 2.0},
                        {"criterion": "No unsupported claims.", "axis": "quality", "weight": -1.0},
                    ],
                }
            ),
        )

        criteria = list(rubric.criteria_for(task))

        assert [criterion.weight for criterion in criteria] == [2.0, -1.0]
        assert [criterion.score_spec.max_score for criterion in criteria] == [2.0, 1.0]
        assert [criterion.description for criterion in criteria] == [
            "Includes citations.",
            "No unsupported claims.",
        ]
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
            "score_scale": "normalized_0_1",
            "raw_score": 2.0,
            "max_possible": 2.0,
            "min_possible": -1.0,
        }


class TestResearchRubricsJudgeCriterion:
    @pytest.mark.asyncio
    async def test_judge_prioritizes_final_resources_over_final_message(self) -> None:
        final_resource, final_blob = _resource_view(
            kind=RunResourceKind.REPORT,
            name="report.md",
            sandbox_origin="/workspace/final_output/report.md",
            text="# Final report\nThis is the primary answer artifact.",
        )
        scratch_resource, scratch_blob = _resource_view(
            kind=RunResourceKind.NOTE,
            name="notes.md",
            sandbox_origin="/workspace/notes.md",
            text="scratch notes",
        )
        runtime = _FakeJudgeRuntime(
            resources=[scratch_resource, final_resource],
            blobs={
                str(final_resource.id): final_blob,
                str(scratch_resource.id): scratch_blob,
            },
        )
        context = EvaluationContext(
            run_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            task=BenchmarkTask(
                task_slug="sample",
                instance_key="default",
                description="Write a report.",
                evaluator_binding_keys=("default",),
            ),
            worker_result=WorkerOutput(output="assistant summary only"),
            runtime=runtime,
        )

        class Criterion(ResearchRubricsJudgeCriterion):
            async def _call_judge(self, *, system_prompt: str, user_prompt: str):
                self.captured_user_prompt = user_prompt
                from ergon_builtins.benchmarks.researchrubrics.judge_criterion import (
                    ResearchRubricsVerdict,
                )

                return ResearchRubricsVerdict(
                    passed=True,
                    reasoning="The final report satisfies the criterion.",
                )

        criterion = Criterion(
            slug="includes_findings",
            rubric=RubricCriterion(
                criterion="Includes findings",
                axis="quality",
                weight=1.0,
            ),
        )

        result = await criterion.evaluate(context)

        assert runtime.listed_task_execution_ids == [None]
        assert set(runtime.read_resource_ids) == {
            str(final_resource.id),
            str(scratch_resource.id),
        }
        assert result.evaluated_resource_ids == [
            str(final_resource.id),
            str(scratch_resource.id),
        ]
        assert result.slug == "includes_findings"
        assert result.observation is not None
        assert result.observation.evidence_resource_ids == result.evaluated_resource_ids
        assert result.observation.output == {
            "passed": True,
            "reasoning": "The final report satisfies the criterion.",
        }
        assert result.evaluation_input is not None
        assert "Final output resources" in result.evaluation_input
        assert "Scratch / supporting resources" in result.evaluation_input
        assert "Final assistant message" in result.evaluation_input
        assert "This is the primary answer artifact." in criterion.captured_user_prompt
        assert "assistant summary only" in criterion.captured_user_prompt
