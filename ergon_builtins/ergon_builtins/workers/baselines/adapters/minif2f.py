"""MiniF2F Lean adapter for :class:`ReActWorker`.

Fetches the live E2B sandbox from :class:`MiniF2FSandboxManager`, builds
a :class:`MiniF2FToolkit`, and after the run scrapes the proof the agent
wrote to ``/workspace/final_output/final_solution.lean``. The proof is
routed through both ``WorkerOutput.output`` and ``artifacts`` — the
runtime's evaluator dispatch drops ``artifacts`` in some paths, so
shipping the proof as the output text is the critical path for
``ProofVerificationCriterion``.
"""

import logging
from typing import Any
from uuid import UUID

from ergon_core.api import BenchmarkTask, WorkerContext, WorkerOutput

from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit
from ergon_builtins.workers.baselines.adapters.base import BenchmarkAdapter

logger = logging.getLogger(__name__)

_FINAL_SOLUTION_PATH = "/workspace/final_output/final_solution.lean"
_FINAL_SOLUTION_ARTIFACT_KEY = "final_solution.lean"

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert Lean 4 theorem prover. Your task is to produce a "
    "complete, verified proof of the given theorem using Mathlib4.\n\n"
    "Workflow:\n"
    "1. Call write_lean_file to save a candidate proof to "
    "/workspace/scratchpad/draft.lean. Use 'sorry' as a placeholder while "
    "exploring.\n"
    "2. Call check_lean_file to see compilation errors and remaining goals.\n"
    "3. Iterate until the proof has no 'sorry' and no errors.\n"
    "4. Write the final proof to /workspace/final_output/final_solution.lean "
    "and call verify_lean_proof to confirm the Lean kernel accepts it.\n\n"
    "Always import Mathlib at the top. Keep proofs short and use high-level "
    "tactics (ring, linarith, nlinarith, simp, omega) when possible."
)


def _make_run_skill(sandbox: Any) -> Any:  # slopcop: ignore[no-typing-any]
    """Return a minimal ``sandbox_run_skill`` callable bound to ``sandbox``.

    The MiniF2F toolkit only routes ``write_lean_file`` through this
    callback; the other tools drive ``sandbox.commands.run`` directly.
    """

    async def run_skill(
        _run_id: UUID,
        skill_name: str,
        response_model: type,
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> Any:  # slopcop: ignore[no-typing-any]
        if skill_name != "write_lean_file":
            raise ValueError(f"MiniF2F adapter does not support skill {skill_name!r}")
        file_path = kwargs["file_path"]
        content = kwargs["content"]
        payload = content.encode("utf-8") if isinstance(content, str) else content
        await sandbox.files.write(file_path, payload)
        return response_model(
            success=True,
            filename=file_path,
            bytes_written=len(payload),
        )

    return run_skill


async def _read_final_proof(sandbox: Any) -> str | None:  # slopcop: ignore[no-typing-any]
    """Return the contents of the agent's final proof file, or ``None``."""
    try:
        result = await sandbox.commands.run(
            f"cat {_FINAL_SOLUTION_PATH} 2>/dev/null",
            timeout=15,
        )
    except Exception as exc:  # slopcop: ignore[no-broad-except]
        logger.warning("Failed to read final proof from sandbox: %s", exc)
        return None
    if result.exit_code != 0 or not (result.stdout or "").strip():
        logger.info(
            "No final proof at %s (exit=%d); scoring will see empty artifacts.",
            _FINAL_SOLUTION_PATH,
            result.exit_code,
        )
        return None
    return result.stdout


class MiniF2FAdapter(BenchmarkAdapter):
    """ReAct adapter for the MiniF2F Lean benchmark."""

    system_prompt = DEFAULT_SYSTEM_PROMPT
    max_iterations = 30

    def __init__(self) -> None:
        self._sandbox: Any = None  # slopcop: ignore[no-typing-any]
        self._final_proof: str | None = None

    async def build_tools(
        self,
        task: BenchmarkTask,
        context: WorkerContext,
    ) -> list[Any]:  # slopcop: ignore[no-typing-any]
        manager = MiniF2FSandboxManager()
        sandbox = manager.get_sandbox(context.task_id)
        if sandbox is None:
            raise RuntimeError(
                f"MiniF2F adapter requires a live sandbox for task_id={context.task_id}; "
                "none is registered on the MiniF2FSandboxManager singleton."
            )
        self._sandbox = sandbox
        toolkit = MiniF2FToolkit(
            sandbox=sandbox,
            sandbox_run_skill=_make_run_skill(sandbox),
            run_id=context.run_id,
        )
        return toolkit.get_tools()

    async def on_run_end(
        self,
        task: BenchmarkTask,
        context: WorkerContext,
    ) -> None:
        # Pull the final proof off the sandbox even if the ReAct loop raised
        # or was closed early — without this, evaluation would have no
        # artifact to score against. The sandbox is still alive here;
        # teardown happens in task_execution_service.finalize_success after
        # get_output() runs.
        if self._sandbox is None:
            return None
        self._final_proof = await _read_final_proof(self._sandbox)
        logger.info(
            "MiniF2F adapter captured final proof: %s bytes",
            len(self._final_proof) if self._final_proof else 0,
        )

    def transform_output(
        self,
        context: WorkerContext,
        base: WorkerOutput,
    ) -> WorkerOutput:
        """Ship the captured proof through both ``output`` and ``artifacts``.

        The runtime's evaluator dispatch only carries ``execution.output_text``
        forward into ``agent_reasoning`` — the worker's ``artifacts`` dict is
        dropped by the time the criterion runs. So we ship the final proof
        code as the *output text* itself; :class:`ProofVerificationCriterion`
        picks it up out of ``context.worker_result.output``.
        """
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
