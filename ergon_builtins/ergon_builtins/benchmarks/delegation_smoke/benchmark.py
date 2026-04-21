"""Minimal benchmark for testing dynamic delegation.

Produces a single task assigned to the manager-researcher worker,
which delegates to researcher sub-agents at runtime.
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.benchmark_deps import BenchmarkDeps
from ergon_core.api.task_types import BenchmarkTask


class DelegationSmokeBenchmark(Benchmark):
    type_slug: ClassVar[str] = "delegation-smoke"
    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps()

    def __init__(self, *, limit: int | None = None) -> None:
        super().__init__(
            name="delegation-smoke",
            description="Dynamic delegation smoke test",
        )

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask]]:
        tasks = [
            BenchmarkTask(
                task_slug="manager-task",
                instance_key="default",
                description=(
                    "You are a manager agent. Your job is to delegate research "
                    "sub-tasks to researcher agents and synthesize their results.\n\n"
                    "Use the add_subtask tool to spawn exactly 2 researcher sub-tasks:\n"
                    "1. 'Research the history of reinforcement learning'\n"
                    "2. 'Research recent advances in multi-agent systems'\n\n"
                    "After spawning both, wait briefly, then provide a synthesis "
                    "of the results."
                ),
                evaluator_binding_keys=("default",),
            ),
        ]
        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ["default"]
