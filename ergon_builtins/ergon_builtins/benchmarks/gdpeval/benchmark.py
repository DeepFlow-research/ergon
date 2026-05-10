"""GDPEval benchmark definition.

Loads GDP document-processing tasks from the HuggingFace dataset
cm2435-new/gdpval_preference_rubrics and exposes them via the
:class:`Benchmark` interface.
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from ergon_core.api import Evaluator, Sandbox, Task, Worker
from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements

from ergon_builtins.benchmarks.gdpeval.loader import (
    HF_REPO_ID,
    extract_task_description,
    find_reference_files,
    load_task_ids,
)
from ergon_builtins.benchmarks.gdpeval.rubric import StagedRubric
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandbox
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig
from ergon_builtins.benchmarks.gdpeval.worker_factory import GDPEvalReactWorker


class GDPEvalBenchmark(Benchmark):
    """Benchmark for GDP document-processing evaluation tasks.

    Each task asks an agent to produce document outputs (DOCX, Excel,
    CSV, …) from reference inputs.  Evaluation uses a staged rubric
    with sequential gating.

    Data is fetched from HuggingFace on first use and cached locally —
    no local data directory required.
    """

    type_slug: ClassVar[str] = "gdpeval"
    task_payload_model: ClassVar[type[GDPTaskConfig]] = GDPTaskConfig
    onboarding_deps: ClassVar[BenchmarkRequirements] = BenchmarkRequirements(
        e2b=True,
        extras=("ergon-builtins[data]",),
    )
    required_packages: ClassVar[list[str]] = ["pandas", "huggingface_hub"]
    install_hint: ClassVar[str] = "pip install 'ergon-builtins[data]'"

    dataset_repo: str = HF_REPO_ID
    split: str = "train"
    limit: int | None = None
    worker: Worker
    sandbox: Sandbox
    evaluators: tuple[Evaluator, ...]

    def __init__(
        self,
        *,
        dataset_repo: str = HF_REPO_ID,
        split: str = "train",
        limit: int | None = None,
        worker: Worker | None = None,
        sandbox: Sandbox | None = None,
        evaluators: tuple[Evaluator, ...] | None = None,
    ) -> None:
        super().__init__(
            name="gdpeval",
            description="GDP Evaluation benchmark for document-processing tasks",
            dataset_repo=dataset_repo,
            split=split,
            limit=limit,
            worker=worker or GDPEvalReactWorker(name="default", model=None),
            sandbox=sandbox or GDPEvalSandbox(),
            evaluators=evaluators
            or (
                StagedRubric(
                    name="default",
                    category_name="default",
                    max_total_score=1.0,
                    stages=[],
                ),
            ),
        )

    def build_instances(self) -> Mapping[str, Sequence[Task[GDPTaskConfig]]]:
        """Materialise one ``BenchmarkTask`` per GDP task.

        All tasks land in a single ``"default"`` instance since there is
        no multi-instance structure in the GDP dataset.
        """
        tasks: list[Task[GDPTaskConfig]] = []
        for payload in self._load_task_configs():
            description = extract_task_description(payload.task_id, repo_id=self.dataset_repo)
            tasks.append(
                Task[GDPTaskConfig](
                    task_slug=payload.task_id,
                    instance_key="default",
                    description=description,
                    worker=self.worker.model_copy(deep=True),
                    sandbox=self.sandbox.model_copy(deep=True),
                    evaluators=tuple(e.model_copy(deep=True) for e in self.evaluators),
                    task_payload=payload,
                )
            )

        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ["default"]

    def _load_task_configs(self) -> list[GDPTaskConfig]:
        """Load and validate GDP task payload configs from the dataset."""
        task_ids = load_task_ids(
            split=self.split,
            repo_id=self.dataset_repo,
            limit=self.limit,
        )
        configs: list[GDPTaskConfig] = []
        for task_id in task_ids:
            ref_files = find_reference_files(task_id, repo_id=self.dataset_repo)
            configs.append(
                GDPTaskConfig(
                    task_id=task_id,
                    workflow_type="document_processing",
                    reference_files=[str(p) for p in ref_files],
                )
            )
        return configs
