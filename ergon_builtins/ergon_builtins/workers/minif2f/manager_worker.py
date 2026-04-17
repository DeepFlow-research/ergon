"""MiniF2F manager worker for the manager+prover smoke demo.

Composes three toolkits at execute time:

* :class:`MiniF2FToolkit` — write_lean_file / check_lean_file /
  verify_lean_proof against the manager's own sandbox, so the manager
  can produce and verify the final ``final_solution.lean``.
* :func:`build_subtask_lifecycle_tools` — add_subtask / list_subtasks /
  get_subtask / bash, so the manager can dispatch a ``minif2f-prover``
  sub-agent to work on the theorem.
* :class:`ResearchGraphToolkit` — list_child_resources / read_resource,
  so the manager can observe what the prover produced.

The manager's own sandbox is the one that ships ``final_solution.lean``
into artifacts, so the unchanged ``ProofVerificationCriterion`` picks
it up directly.
"""

import logging
from collections.abc import AsyncGenerator
from typing import ClassVar

from ergon_core.api import WorkerOutput
from ergon_core.api.generation import GenerationTurn
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext

from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit
from ergon_builtins.tools.graph_toolkit import ResearchGraphToolkit
from ergon_builtins.tools.subtask_lifecycle_toolkit import (
    build_subtask_lifecycle_tools,
)
from ergon_builtins.workers.baselines.minif2f_react_worker import (
    _make_run_skill,
    _read_final_proof,
)

_FINAL_SOLUTION_ARTIFACT_KEY = "final_solution.lean"
from ergon_builtins.workers.baselines.react_worker import ReActWorker

logger = logging.getLogger(__name__)

_MANAGER_SYSTEM_PROMPT = (
    "You are a Lean 4 proof manager agent. Your job is to prove a theorem "
    "by delegating to a prover sub-agent, observing its draft, and then "
    "producing the verified final proof yourself.\n\n"
    "You have access to:\n"
    "- add_subtask(description, worker_binding_key, depends_on): Spawn a "
    "prover sub-agent. Use worker_binding_key='minif2f-prover'.\n"
    "- list_subtasks(): Status and output of every direct subtask.\n"
    "- get_subtask(node_id): Full details for one subtask.\n"
    "- cancel_task / refine_task / restart_task: control flow tools.\n"
    "- bash(command): Run a shell command in your own sandbox.\n"
    "- write_lean_file / check_lean_file / verify_lean_proof: Lean 4 tools "
    "bound to your own sandbox.\n"
    "- Resource-discovery tools to observe the prover's outputs.\n\n"
    "Workflow:\n"
    "1. Spawn exactly one minif2f-prover sub-agent via add_subtask with a "
    "clear restatement of the theorem.\n"
    "2. Poll list_subtasks until the prover completes, then read its output "
    "via get_subtask.\n"
    "3. Take the prover's proof (or write your own if the prover failed) "
    "and save it with write_lean_file to "
    "/workspace/final_output/final_solution.lean.\n"
    "4. Call verify_lean_proof on that path before you finish. Do not stop "
    "until verify_lean_proof reports success.\n\n"
    "For trivial goals 'by decide', 'by rfl', or 'by norm_num' usually suffice."
)


class MiniF2FManagerWorker(ReActWorker):
    """Manager for the MiniF2F smoke demo.

    Spawns a :class:`MiniF2FProverWorker` via ``add_subtask``; writes and
    verifies the final proof in its own sandbox so the unchanged
    ``minif2f-rubric`` / ``proof-verification`` criterion compiles it.
    """

    type_slug: ClassVar[str] = "minif2f-manager"

    def __init__(
        self,
        *,
        name: str = "minif2f-manager",
        model: str | None = None,
        max_iterations: int = 30,
    ) -> None:
        super().__init__(
            name=name,
            model=model,
            tools=[],
            system_prompt=_MANAGER_SYSTEM_PROMPT,
            max_iterations=max_iterations,
        )
        # Captured at end-of-execute by reading /workspace/final_output/
        # final_solution.lean from the manager's sandbox; surfaced via
        # get_output().
        self._final_proof: str | None = None

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        if context.node_id is None:
            raise RuntimeError("MiniF2FManagerWorker requires WorkerContext.node_id")

        sandbox_manager = MiniF2FSandboxManager()
        sandbox = sandbox_manager.get_sandbox(context.task_id)
        if sandbox is None:
            raise RuntimeError(
                f"MiniF2FManagerWorker requires a live sandbox for task_id={context.task_id}; "
                "none is registered on the MiniF2FSandboxManager singleton."
            )

        minif2f_toolkit = MiniF2FToolkit(
            sandbox=sandbox,
            sandbox_run_skill=_make_run_skill(sandbox),
            run_id=context.run_id,
        )

        lifecycle_tools = build_subtask_lifecycle_tools(
            run_id=context.run_id,
            parent_node_id=context.node_id,
            sandbox_id=context.sandbox_id,
        )

        graph_tools = ResearchGraphToolkit(
            run_id=context.run_id,
            task_execution_id=context.execution_id,
        ).build_tools()

        self.tools = [*minif2f_toolkit.get_tools(), *lifecycle_tools, *graph_tools]

        try:
            async for turn in super().execute(task, context=context):
                yield turn
        finally:
            # Pull the final proof off the manager's own sandbox even if
            # the base generator raised — same pattern as MiniF2FReActWorker.
            self._final_proof = await _read_final_proof(sandbox)
            logger.info(
                "MiniF2FManagerWorker captured final proof: %s bytes",
                len(self._final_proof) if self._final_proof else 0,
            )

    def get_output(self, context: WorkerContext) -> WorkerOutput:
        """Route the final proof through ``output`` + ``artifacts``.

        ``evaluator_dispatch_service`` only carries ``execution.output_text``
        forward into ``agent_reasoning``; the worker's ``artifacts`` dict is
        what ``ProofVerificationCriterion._extract_proof`` reads, but it
        also falls back to ``worker_result.output`` if the artifact is
        missing. We populate both, mirroring :class:`MiniF2FReActWorker`.
        """
        base = super().get_output(context)
        if self._final_proof is None:
            return base
        artifacts = dict(base.artifacts) if base.artifacts else {}
        artifacts[_FINAL_SOLUTION_ARTIFACT_KEY] = self._final_proof
        return base.model_copy(
            update={
                "output": self._final_proof,
                "success": True,
                "artifacts": artifacts,
            }
        )
