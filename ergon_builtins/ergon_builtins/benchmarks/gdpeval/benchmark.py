"""GDPEval benchmark definition.

Loads GDP document-processing tasks from the HuggingFace dataset
cm2435-new/gdpval_preference_rubrics and exposes them via the
:class:`Benchmark` interface.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar

from ergon_core.api import Benchmark, BenchmarkRequirements, Task
from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker

from ergon_builtins.benchmarks.gdpeval.loader import (
    HF_REPO_ID,
    extract_task_description,
    find_reference_files,
    load_task_ids,
)
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandbox
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig
from ergon_builtins.benchmarks.gdpeval.workers import (
    make_gdpeval_rubric,
    make_gdpeval_worker,
)


def _default_gdpeval_sandbox() -> Sandbox:
    return GDPEvalSandbox()


class GDPEvalTask(Task[GDPTaskConfig]):
    """Concrete Task subclass for GDPEval instances.

    Named so ``Task.from_definition`` can resolve the ``_type``
    discriminator as a plain module attribute.  The parameterized
    generic ``Task[GDPTaskConfig]`` cannot be looked up that way —
    its ``__qualname__`` includes ``[...]``.
    """


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

    def __init__(
        self,
        *,
        dataset_repo: str = HF_REPO_ID,
        split: str = "train",
        limit: int | None = None,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
        worker_factory: Callable[[], Worker] = make_gdpeval_worker,
        sandbox_factory: Callable[[], Sandbox] = _default_gdpeval_sandbox,
        evaluator_factory: Callable[[], Evaluator] = make_gdpeval_rubric,
    ) -> None:
        super().__init__(
            name=name or "gdpeval",
            description=description or "GDP Evaluation benchmark for document-processing tasks",
            metadata=metadata,
        )
        self.dataset_repo = dataset_repo
        self.split = split
        self.limit = limit
        self._worker_factory = worker_factory
        self._sandbox_factory = sandbox_factory
        self._evaluator_factory = evaluator_factory

    def build_instances(self) -> Mapping[str, Sequence[Task[GDPTaskConfig]]]:
        """Materialise one ``Task`` per GDP task.

        All tasks land in a single ``"default"`` instance since there is
        no multi-instance structure in the GDP dataset.
        """
        tasks: list[Task[GDPTaskConfig]] = []
        for payload in self._load_task_configs():
            description = extract_task_description(payload.task_id, repo_id=self.dataset_repo)
            tasks.append(
                GDPEvalTask(
                    task_slug=payload.task_id,
                    instance_key="default",
                    description=description,
                    task_payload=payload,
                    worker=self._worker_factory(),
                    sandbox=self._sandbox_factory(),
                    evaluators=(self._evaluator_factory(),),
                )
            )

        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ()

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
