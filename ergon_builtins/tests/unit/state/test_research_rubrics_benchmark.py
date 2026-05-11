"""Tests for ResearchRubrics benchmark registration and vanilla variant."""

from datetime import UTC, datetime
from collections.abc import AsyncGenerator
from typing import ClassVar
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
from ergon_core.api import Benchmark, Sandbox, Worker, WorkerContext
from ergon_core.api.criterion import CriterionContext
from ergon_core.api.criterion import CriterionOutcome
from ergon_core.api.worker import WorkerOutput
from ergon_core.core.application.resources import RunResourceView
from ergon_core.core.persistence.shared.enums import RunResourceKind
from ergon_core.api.benchmark import Task


class _Sandbox(Sandbox):
    async def provision(self) -> None:
        return None


class _Worker(Worker):
    type_slug: ClassVar[str] = "researchrubrics-test-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> AsyncGenerator[WorkerOutput, None]:
        yield WorkerOutput(output="", success=True)


def _task(**kwargs) -> Task:
    task_cls = (
        Task[ResearchRubricsTaskPayload]
        if isinstance(kwargs.get("task_payload"), ResearchRubricsTaskPayload)
        else Task
    )
    return task_cls(
        worker=_Worker(name="worker", model=None),
        sandbox=_Sandbox(),
        **kwargs,
    )


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
        task = _task(
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

        assert [criterion.max_score for criterion in criteria] == [2.0, 1.0]
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
        task = _task(
            task_slug="sample",
            instance_key="default",
            description="Write a report.",
        )

        result = rubric.aggregate_task(
            task,
            [
                CriterionOutcome(name="positive", score=1.0, passed=True, weight=2.0),
                CriterionOutcome(name="negative", score=0.0, passed=False, weight=-1.0),
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


