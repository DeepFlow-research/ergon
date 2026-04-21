"""Per-benchmark DI factory — unions `SubtaskLifecycleToolkit` with the
env-specific toolkit so a single generic ReAct worker can exercise any
of the three target benchmarks."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class _HasContextFields(Protocol):
    run_id: Any  # slopcop: ignore[no-typing-any]
    node_id: Any  # slopcop: ignore[no-typing-any]
    execution_id: Any  # slopcop: ignore[no-typing-any]
    sandbox_id: str


def compose_benchmark_toolkit(
    *,
    benchmark_slug: str,
    ctx: _HasContextFields,
    sandbox: Any,  # slopcop: ignore[no-typing-any]
    run_skill: Callable[..., Awaitable[Any]] | None = None,  # slopcop: ignore[no-typing-any]
    publisher_sync: Callable[[], Awaitable[list[Any]]]  # slopcop: ignore[no-typing-any]
    | None = None,
) -> list[Any]:  # slopcop: ignore[no-typing-any]
    """Return the union of Tools a generic ReAct worker needs for benchmark_slug."""
    # reason: lazy import avoids circular deps at module load time
    from ergon_builtins.tools.subtask_lifecycle_toolkit import SubtaskLifecycleToolkit

    lifecycle = SubtaskLifecycleToolkit(
        run_id=ctx.run_id,
        parent_node_id=ctx.node_id,
        sandbox_id=ctx.sandbox_id,
    ).get_tools()

    match benchmark_slug:
        case "researchrubrics":
            # reason: benchmark-specific import kept local to avoid mandatory top-level deps
            from ergon_builtins.tools.graph_toolkit import ResearchGraphToolkit

            # reason: benchmark-specific import kept local to avoid mandatory top-level deps
            from ergon_builtins.tools.research_rubrics_toolkit import (
                ResearchRubricsToolkit,
            )

            if run_skill is None or publisher_sync is None:
                raise ValueError("researchrubrics composer requires run_skill + publisher_sync")
            rr = ResearchRubricsToolkit(
                run_skill=run_skill,
                publisher_sync=publisher_sync,
            ).build_tools()
            graph = ResearchGraphToolkit(
                run_id=ctx.run_id,
                task_execution_id=ctx.execution_id,
            ).build_tools()
            return [*lifecycle, *rr, *graph]
        case "minif2f":
            # reason: benchmark-specific import kept local to avoid mandatory top-level deps
            from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit

            if run_skill is None:
                raise ValueError("minif2f composer requires run_skill")
            return [
                *lifecycle,
                *MiniF2FToolkit(
                    sandbox=sandbox,
                    sandbox_run_skill=run_skill,
                    run_id=ctx.run_id,
                ).get_tools(),
            ]
        case "swebench-verified":
            # reason: benchmark-specific import kept local to avoid mandatory top-level deps
            from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit

            return [*lifecycle, *SWEBenchToolkit(sandbox=sandbox).get_tools()]
        case _:
            raise ValueError(f"no toolkit composer for {benchmark_slug!r}")
