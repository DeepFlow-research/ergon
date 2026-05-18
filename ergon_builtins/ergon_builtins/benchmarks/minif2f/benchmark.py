"""MiniF2F benchmark for formal math proof verification (Lean 4, v2c).

Loads problems from the roozbeh-yz/miniF2F_v2 HuggingFace dataset repo,
specifically the ``miniF2F_v2c.jsonl`` file containing Lean 4 theorem
statements aligned with mathlib4.
"""

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar

from ergon_core.api import Benchmark, BenchmarkRequirements, Task
from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker
from huggingface_hub import hf_hub_download

from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem, MiniF2FTaskPayload
from ergon_builtins.benchmarks.minif2f.workers import (
    make_minif2f_rubric,
    make_minif2f_worker,
)
from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox

logger = logging.getLogger(__name__)

HF_REPO_ID = "roozbeh-yz/miniF2F_v2"
HF_FILENAME = "miniF2F_v2c.jsonl"


class MiniF2FTask(Task[MiniF2FTaskPayload]):
    """Concrete Task subclass for MiniF2F instances.

    Named so ``Task.from_definition`` can resolve the ``_type``
    discriminator as a plain module attribute. The parameterized
    generic ``Task[MiniF2FTaskPayload]`` cannot be looked up that way.
    """


class MiniF2FBenchmark(Benchmark):
    """Benchmark backed by the MiniF2F-v2c dataset of formal math problems.

    ``build_instances`` downloads the jsonl from HuggingFace Hub (cached
    locally) and returns one task per theorem.
    """

    type_slug: ClassVar[str] = "minif2f"
    task_payload_model: ClassVar[type[MiniF2FTaskPayload]] = MiniF2FTaskPayload
    onboarding_deps: ClassVar[BenchmarkRequirements] = BenchmarkRequirements(e2b=True)

    def __init__(
        self,
        *,
        data_dir: Path | str | None = None,
        limit: int | None = None,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
        worker_factory: Callable[[], Worker] = make_minif2f_worker,
        sandbox_factory: Callable[[], Sandbox] = LeanSandbox,
        evaluator_factory: Callable[[], Evaluator] = make_minif2f_rubric,
    ) -> None:
        super().__init__(
            name=name or "minif2f",
            description=description or "MiniF2F formal math proof benchmark (Lean 4, v2c)",
            metadata=metadata,
        )
        self.data_dir = Path(data_dir) if data_dir else None
        self.limit = limit
        self._worker_factory = worker_factory
        self._sandbox_factory = sandbox_factory
        self._evaluator_factory = evaluator_factory

    # ------------------------------------------------------------------

    def build_instances(self) -> Mapping[str, Sequence[Task[MiniF2FTaskPayload]]]:
        problems = self._load_problems()
        tasks: list[Task[MiniF2FTaskPayload]] = []
        for problem in problems:
            payload = MiniF2FTaskPayload(
                name=problem.name,
                informal_statement=problem.informal_statement,
                formal_statement=problem.formal_statement,
                header=problem.header,
            )
            description = (
                f"{problem.informal_statement}\n\n"
                f"Your task: prove the following theorem in Lean 4.\n\n"
                f"{problem.header}\n"
                f"{problem.formal_statement}"
            )
            tasks.append(
                MiniF2FTask(
                    task_slug=problem.name,
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

    # ------------------------------------------------------------------

    def _download_jsonl(self) -> Path:
        """Download the v2c jsonl from HuggingFace Hub, returning the cached path."""
        cache_dir = str(self.data_dir) if self.data_dir else None
        path = hf_hub_download(
            repo_id=HF_REPO_ID,
            filename=HF_FILENAME,
            repo_type="dataset",
            cache_dir=cache_dir,
        )
        return Path(path)

    def _load_problems(self) -> list[MiniF2FProblem]:
        jsonl_path = self._download_jsonl()
        logger.info("Loading MiniF2F-v2c problems from %s", jsonl_path)

        problems: list[MiniF2FProblem] = []
        with jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                problems.append(
                    MiniF2FProblem(
                        name=raw["name"],
                        informal_statement=raw["informal_statement"],
                        formal_statement=raw["formal_statement"],
                        header=raw["header"],
                    )
                )
                if self.limit and len(problems) >= self.limit:
                    break

        logger.info("Loaded %d MiniF2F-v2c problems", len(problems))
        return problems
