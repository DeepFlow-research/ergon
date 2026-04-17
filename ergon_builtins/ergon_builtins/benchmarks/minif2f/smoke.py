"""Deterministic single-task MiniF2F benchmark for the manager+prover demo.

Ships one canned trivial theorem so the demo command is fast, offline
(no HuggingFace download), and guaranteed provable by ``openai:gpt-4o``.
The task payload uses the same :class:`MiniF2FTaskPayload` shape as the
full benchmark so ``MiniF2FReActWorker`` / ``MiniF2FProverWorker`` can
consume it unchanged.
"""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.task_types import BenchmarkTask

from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FTaskPayload

_SMOKE_HEADER = "import Mathlib\n"
_SMOKE_FORMAL_STATEMENT = "theorem smoke_add : 1 + 1 = 2 := by decide"
_SMOKE_INFORMAL = "Prove that one plus one equals two."


class MiniF2FSmokeBenchmark(Benchmark):
    """One trivial Lean 4 theorem, used only by the manager+prover smoke demo."""

    type_slug: ClassVar[str] = "minif2f-smoke"

    def __init__(
        self,
        *,
        limit: int | None = None,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            name=name or "minif2f-smoke",
            description=description or "Single trivial Lean 4 theorem for CI smoke demos",
            metadata=metadata,
        )
        # ``limit`` is accepted to match the shared ``_construct_benchmark`` probe
        # in the CLI composition; this benchmark only ever produces one task.
        self._limit = limit

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask]]:
        payload = MiniF2FTaskPayload(
            name="smoke_add",
            informal_statement=_SMOKE_INFORMAL,
            formal_statement=_SMOKE_FORMAL_STATEMENT,
            header=_SMOKE_HEADER,
        )
        description = (
            f"{_SMOKE_INFORMAL}\n\n"
            f"Your task: prove the following theorem in Lean 4.\n\n"
            f"{_SMOKE_HEADER}"
            f"{_SMOKE_FORMAL_STATEMENT}"
        )
        task = BenchmarkTask(
            task_key="smoke_add",
            instance_key="default",
            description=description,
            evaluator_binding_keys=("default",),
            task_payload=payload.model_dump(),
        )
        return {"default": [task]}

    def evaluator_requirements(self) -> Sequence[str]:
        return ("default",)
