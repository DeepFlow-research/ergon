"""Tests for ResearchRubrics benchmark registration and vanilla variant."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
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
from ergon_core.api import Benchmark
from ergon_core.api.criterion import CriterionContext
from ergon_core.api.criterion import CriterionOutcome
from ergon_core.api.worker import WorkerOutput
from ergon_core.core.application.resources import RunResourceView
from ergon_core.core.persistence.shared.enums import RunResourceKind
from ergon_core.api.benchmark import Task
from ergon_core.test_support.task_factory import task_with_id


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
    """Verify benchmark classes expose the final object-bound surface."""

    def test_researchrubrics_type_slug(self):
        assert ResearchRubricsBenchmark.type_slug == "researchrubrics"
        assert issubclass(ResearchRubricsBenchmark, Benchmark)

    def test_researchrubrics_vanilla_type_slug(self):
        assert ResearchRubricsVanillaBenchmark.type_slug == "researchrubrics-vanilla"
        assert issubclass(ResearchRubricsVanillaBenchmark, Benchmark)

    def test_rubric_type_slug(self):
        assert ResearchRubricsRubric.type_slug == "researchrubrics-rubric"


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
        task = task_with_id(
            uuid4(),
            cls=Task[ResearchRubricsTaskPayload],
            task_slug="sample",
            instance_key="default",
            description="Write a report.",
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
        task = task_with_id(
            uuid4(),
            task_slug="sample",
            instance_key="default",
            description="Write a report.",
        )

        result = rubric.aggregate_task(
            task,
            [
                CriterionOutcome(
                    slug="positive",
                    name="positive",
                    score=1.0,
                    passed=True,
                    weight=2.0,
                ),
                CriterionOutcome(
                    slug="negative",
                    name="negative",
                    score=0.0,
                    passed=False,
                    weight=-1.0,
                ),
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
    async def test_judge_prioritizes_final_resources_over_final_message(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
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
        final_path = tmp_path / "report.md"
        final_path.write_bytes(final_blob)
        scratch_path = tmp_path / "notes.md"
        scratch_path.write_bytes(scratch_blob)
        final_resource = final_resource.model_copy(update={"file_path": str(final_path)})
        scratch_resource = scratch_resource.model_copy(update={"file_path": str(scratch_path)})
        listed: list[tuple[object, object]] = []

        class FakeRepo:
            def list_for_run(self, session, *, run_id, task_execution_id):
                listed.append((run_id, task_execution_id))
                return [scratch_resource, final_resource]

        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        monkeypatch.setattr(
            "ergon_builtins.benchmarks.researchrubrics.judge_criterion.RunResourceRepository",
            lambda: FakeRepo(),
        )
        monkeypatch.setattr(
            "ergon_builtins.benchmarks.researchrubrics.judge_criterion.get_session",
            lambda: FakeSession(),
        )
        captured_user_prompts: list[str] = []

        context = CriterionContext(
            run_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            task=task_with_id(
                uuid4(),
                task_slug="sample",
                instance_key="default",
                description="Write a report.",
            ),
            worker_result=WorkerOutput(output="assistant summary only"),
        )

        class Criterion(ResearchRubricsJudgeCriterion):
            async def _call_judge(self, *, system_prompt: str, user_prompt: str):
                captured_user_prompts.append(user_prompt)
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

        assert listed == [(context.run_id, context.execution_id)]
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
        assert len(captured_user_prompts) == 1
        assert "This is the primary answer artifact." in captured_user_prompts[0]
        assert "assistant summary only" in captured_user_prompts[0]

    def test_rejects_model_alias(self) -> None:
        with pytest.raises(ValidationError, match="model"):
            ResearchRubricsJudgeCriterion(
                slug="includes_findings",
                rubric=RubricCriterion(
                    criterion="Includes findings",
                    axis="quality",
                    weight=1.0,
                ),
                model="openai:gpt-4o-mini",
            )

    def test_does_not_expose_model_alias(self) -> None:
        criterion = ResearchRubricsJudgeCriterion(
            slug="includes_findings",
            rubric=RubricCriterion(
                criterion="Includes findings",
                axis="quality",
                weight=1.0,
            ),
            judge_model="openai:gpt-4o-mini",
        )

        assert criterion.judge_model == "openai:gpt-4o-mini"
        assert not hasattr(criterion, "model")
