"""MiniF2F benchmark for formal math proof verification.

Loads problems from the facebook/miniF2F repository, each containing a Lean
theorem statement and ground-truth proof.
"""

import logging
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.task_types import BenchmarkTask

from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem, MiniF2FTaskPayload

logger = logging.getLogger(__name__)

MINIF2F_REPO = "https://github.com/facebookresearch/miniF2F"


class MiniF2FBenchmark(Benchmark):
    """Benchmark backed by the MiniF2F dataset of formal math problems.

    ``build_instances`` clones the repository (if needed), parses Lean
    theorem files, and returns one task per theorem.
    """

    type_slug: ClassVar[str] = "minif2f"

    def __init__(
        self,
        *,
        data_dir: Path | str | None = None,
        limit: int | None = None,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            name=name or "minif2f",
            description=description or "MiniF2F formal math proof benchmark",
            metadata=metadata,
        )
        self.data_dir = Path(data_dir) if data_dir else None
        self.limit = limit

    # ------------------------------------------------------------------

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask]]:
        problems = self._load_problems()
        tasks: list[BenchmarkTask] = []
        for problem in problems:
            payload = MiniF2FTaskPayload(
                problem_id=problem.problem_id,
                problem_statement=problem.problem_statement,
                ground_truth_proof=problem.ground_truth_proof,
                split=problem.split,
                proof_type=problem.proof_type,
            )
            tasks.append(
                BenchmarkTask(
                    task_key=problem.problem_id,
                    instance_key="default",
                    description=problem.problem_statement,
                    evaluator_binding_keys=("default",),
                    task_payload=payload.model_dump(),
                )
            )
        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ("default",)

    # ------------------------------------------------------------------

    def _ensure_repo(self) -> Path:
        """Clone the MiniF2F repo if it doesn't already exist."""
        base = self.data_dir or Path.cwd() / "data"
        minif2f_dir = base / "raw" / "minif2f"
        if not minif2f_dir.exists():
            logger.info("Cloning MiniF2F repository to %s …", minif2f_dir)
            subprocess.run(
                ["git", "clone", MINIF2F_REPO, str(minif2f_dir)],
                check=True,
            )
        return minif2f_dir

    def _load_problems(self) -> list[MiniF2FProblem]:
        minif2f_dir = self._ensure_repo()
        problems: list[MiniF2FProblem] = []

        for split in ("valid", "test"):
            lean_file = minif2f_dir / "lean" / "src" / f"{split}.lean"
            if not lean_file.exists():
                continue

            content = lean_file.read_text(encoding="utf-8")
            theorem_pattern = r"theorem\s+(\w+)\s+.*?(?=\n\s*theorem|\Z)"

            for match in re.finditer(theorem_pattern, content, re.DOTALL):
                if self.limit and len(problems) >= self.limit:
                    break

                theorem_name = match.group(1)
                theorem_content = match.group(0).strip()

                lines = theorem_content.split("\n")
                depth = 0
                end_idx = len(lines)
                for i, line in enumerate(lines):
                    if "begin" in line:
                        depth += 1
                    elif "end" in line:
                        depth -= 1
                        if depth == 0:
                            end_idx = i + 1
                            break

                theorem_block = "\n".join(lines[:end_idx])

                statement_lines: list[str] = []
                for line in theorem_block.split("\n"):
                    statement_lines.append(line)
                    if ":=" in line:
                        break
                problem_statement = "\n".join(statement_lines).strip()

                problems.append(
                    MiniF2FProblem(
                        problem_id=theorem_name,
                        problem_statement=problem_statement,
                        ground_truth_proof=theorem_block.strip(),
                        split=split,
                        lean_file_path=lean_file,
                    )
                )

            if self.limit and len(problems) >= self.limit:
                break

        return problems
