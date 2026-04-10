"""GDPEval benchmark definition.

Loads GDP document-processing tasks from a parquet dataset + staged
rubric file and exposes them via the :class:`Benchmark` interface.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import ClassVar

from h_arcane.api.benchmark import Benchmark
from h_arcane.api.task_types import BenchmarkTask

from arcane_builtins.benchmarks.gdpeval.loader import (
    extract_task_description,
    find_reference_files,
    load_task_ids,
)


class GDPEvalBenchmark(Benchmark):
    """Benchmark for GDP document-processing evaluation tasks.

    Each task asks an agent to produce document outputs (DOCX, Excel,
    CSV, …) from reference inputs.  Evaluation uses a staged rubric
    with sequential gating.
    """

    type_slug: ClassVar[str] = "gdpeval"
    required_packages: ClassVar[list[str]] = ["pandas"]
    install_hint: ClassVar[str] = "pip install 'arcane-builtins[data]'"

    def __init__(
        self,
        *,
        data_dir: str | Path | None = None,
        rubric_file: str | Path | None = None,
        reference_dir: str | Path | None = None,
        limit: int | None = None,
    ) -> None:
        super().__init__(
            name="gdpeval",
            description="GDP Evaluation benchmark for document-processing tasks",
        )
        self.data_dir = Path(data_dir) if data_dir else None
        self.rubric_file = Path(rubric_file) if rubric_file else None
        self.reference_dir = Path(reference_dir) if reference_dir else None
        self.limit = limit

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask]]:
        """Materialise one ``BenchmarkTask`` per GDP task.

        All tasks land in a single ``"default"`` instance since there is
        no multi-instance structure in the GDP dataset.
        """
        task_ids = load_task_ids(
            rubric_file=self._resolve_rubric_file(),
            limit=self.limit,
        )

        ref_dir = self._resolve_reference_dir()
        tasks: list[BenchmarkTask] = []

        for task_id in task_ids:
            description = extract_task_description(
                task_id,
                parquet_path=self._resolve_parquet_path(),
            )
            ref_files = find_reference_files(task_id, ref_dir)

            tasks.append(
                BenchmarkTask(
                    task_key=task_id,
                    instance_key="default",
                    description=description,
                    evaluator_binding_keys=("default",),
                    task_payload={
                        "workflow_type": "document_processing",
                        "reference_files": [str(p) for p in ref_files],
                    },
                )
            )

        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ["default"]

    # -- path helpers -------------------------------------------------------

    def _resolve_data_dir(self) -> Path:
        if self.data_dir is not None:
            return self.data_dir
        raise ValueError(
            "data_dir must be provided to GDPEvalBenchmark "
            "(no global settings fallback in the new architecture)"
        )

    def _resolve_parquet_path(self) -> Path:
        return self._resolve_data_dir() / "raw" / "gdpeval.parquet"

    def _resolve_rubric_file(self) -> Path:
        if self.rubric_file is not None:
            return self.rubric_file
        return self._resolve_data_dir() / "generated" / "staged_v2" / "staged_rubrics.jsonl"

    def _resolve_reference_dir(self) -> Path:
        if self.reference_dir is not None:
            return self.reference_dir
        return self._resolve_data_dir() / "raw" / "reference_files"
