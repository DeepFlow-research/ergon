"""GDPEval benchmark definition.

Loads GDP document-processing tasks from the HuggingFace dataset
cm2435-new/gdpval_preference_rubrics and exposes them via the
:class:`Benchmark` interface.
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.benchmark_deps import BenchmarkDeps
from ergon_core.api.task_types import BenchmarkTask

from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig
from ergon_builtins.benchmarks.gdpeval.loader import (
    HF_REPO_ID,
    extract_task_description,
    find_reference_files,
    load_task_ids,
)


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
    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(
        e2b=True,
        extras=("ergon-builtins[data]",),
    )
    required_packages: ClassVar[list[str]] = ["pandas", "huggingface_hub"]
    install_hint: ClassVar[str] = "pip install 'ergon-builtins[data]'"

    def __init__(
        self,
        *,
        dataset_repo: str = HF_REPO_ID,
        split: str = "train",
        limit: int | None = None,
    ) -> None:
        super().__init__(
            name="gdpeval",
            description="GDP Evaluation benchmark for document-processing tasks",
        )
        self.dataset_repo = dataset_repo
        self.split = split
        self.limit = limit

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask[GDPTaskConfig]]]:
        """Materialise one ``BenchmarkTask`` per GDP task.

        All tasks land in a single ``"default"`` instance since there is
        no multi-instance structure in the GDP dataset.
        """
        tasks: list[BenchmarkTask[GDPTaskConfig]] = []
        for payload in self._load_task_configs():
            description = extract_task_description(payload.task_id, repo_id=self.dataset_repo)
            tasks.append(
                BenchmarkTask[GDPTaskConfig](
                    task_slug=payload.task_id,
                    instance_key="default",
                    description=description,
                    evaluator_binding_keys=("default",),
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
