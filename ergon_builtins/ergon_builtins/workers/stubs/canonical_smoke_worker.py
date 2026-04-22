"""Canonical smoke parent worker.

Always plans the same 9-subtask graph regardless of env:

    Diamond (4):           Line (3):           Singletons (2):
          d_root           l_1 -> l_2 -> l_3         s_a    s_b
          /     \\
      d_left   d_right
          \\     /
          d_join

Determinism is the point: a graph regression either surfaces identically in
every env's smoke, or doesn't exist. The leaf work is env-specific via the
composition binding `smoke-leaf`. The worker calls plan_subtasks directly
(no LLM) so the topology is fixed by code, not model behaviour.
"""

from collections.abc import AsyncGenerator

from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn, TextPart
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.types import (
    AssignedWorkerSlug,
    NodeId,
    RunId,
    TaskSlug,
)
from ergon_core.core.runtime.services.task_management_dto import (
    PlanSubtasksCommand,
    SubtaskSpec,
)
from ergon_core.core.runtime.services.task_management_service import (
    TaskManagementService,
)

EXPECTED_SUBTASK_SLUGS: tuple[str, ...] = (
    "d_root",
    "d_left",
    "d_right",
    "d_join",
    "l_1",
    "l_2",
    "l_3",
    "s_a",
    "s_b",
)


def _build_specs() -> list[SubtaskSpec]:
    leaf = AssignedWorkerSlug("smoke-leaf")

    def spec(slug: str, description: str, deps: list[str]) -> SubtaskSpec:
        return SubtaskSpec(
            task_slug=TaskSlug(slug),
            description=description,
            assigned_worker_slug=leaf,
            depends_on=[TaskSlug(d) for d in deps],
        )

    return [
        spec("d_root", "Diamond root", []),
        spec("d_left", "Diamond left arm", ["d_root"]),
        spec("d_right", "Diamond right arm", ["d_root"]),
        spec("d_join", "Diamond join", ["d_left", "d_right"]),
        spec("l_1", "Line node 1", []),
        spec("l_2", "Line node 2", ["l_1"]),
        spec("l_3", "Line node 3", ["l_2"]),
        spec("s_a", "Singleton A", []),
        spec("s_b", "Singleton B", []),
    ]


class CanonicalSmokeWorker(Worker):
    """Shared parent for every env's canonical smoke."""

    type_slug = "canonical-smoke"

    def __init__(self, *, name: str = "canonical-smoke", model: str | None) -> None:
        super().__init__(name=name, model=model)

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        if context.node_id is None:
            raise ValueError("CanonicalSmokeWorker requires context.node_id")
        service = TaskManagementService()
        command = PlanSubtasksCommand(
            run_id=RunId(context.run_id),
            parent_node_id=NodeId(context.node_id),
            subtasks=_build_specs(),
        )
        with get_session() as session:
            result = await service.plan_subtasks(session, command)

        summary = "\n".join(
            f"{slug}: planned (node_id={result.nodes[TaskSlug(slug)]})"
            for slug in EXPECTED_SUBTASK_SLUGS
        )
        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        "canonical-smoke planned 9 subtasks "
                        f"(roots={sorted(result.roots)}):\n{summary}"
                    ),
                ),
            ],
        )
