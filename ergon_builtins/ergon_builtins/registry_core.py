"""Components with no dependencies beyond ergon-core.

All imports are eager and fully typed.  This module is always safe to import
regardless of which optional extras are installed.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from ergon_core.api import Benchmark, Evaluator, Worker
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

from ergon_builtins.benchmarks.gdpeval.rubric import StagedRubric
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit
from ergon_builtins.benchmarks.swebench_verified.benchmark import SweBenchVerifiedBenchmark
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
from ergon_builtins.evaluators.rubrics.swebench_rubric import SWEBenchRubric
from ergon_builtins.workers.baselines.react_prompts import (
    MINIF2F_SYSTEM_PROMPT,
    SWEBENCH_SYSTEM_PROMPT,
)
from ergon_builtins.workers.baselines.react_worker import ReActWorker
from ergon_builtins.workers.baselines.training_stub_worker import TrainingStubWorker


# reason: Worker factory signature — every registry entry accepts the same
# four keyword-only args. Plain ``Worker`` subclasses get them via
# ``super().__init__``; benchmark factories read ``task_id`` to resolve a
# live sandbox. RFC 2026-04-22 §1 + Open Question 1 resolution.
WorkerFactory = Callable[..., Worker]


def _minif2f_run_skill(sandbox: Any) -> Any:  # slopcop: ignore[no-typing-any]
    """Return the ``write_lean_file`` run_skill callback bound to ``sandbox``.

    Extracted from the old ``MiniF2FAdapter`` verbatim. The MiniF2F toolkit
    only routes ``write_lean_file`` through this callback; the other tools
    drive ``sandbox.commands.run`` directly.
    """

    async def run_skill(
        _run_id: UUID,
        skill_name: str,
        response_model: type,
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> Any:  # slopcop: ignore[no-typing-any]
        if skill_name != "write_lean_file":
            raise ValueError(f"MiniF2F factory does not support skill {skill_name!r}")
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


def _minif2f_react(
    *,
    name: str,
    model: str | None,
    task_id: UUID,
    sandbox_id: str,
) -> ReActWorker:
    """Registry factory: ReActWorker wired with a live MiniF2F toolkit."""
    sandbox = MiniF2FSandboxManager().get_sandbox(task_id)
    if sandbox is None:
        raise RuntimeError(
            f"MiniF2F factory requires a live sandbox for task_id={task_id}; "
            "SandboxSetupRequest must have completed before worker-execute runs."
        )
    toolkit = MiniF2FToolkit(
        sandbox=sandbox,
        sandbox_run_skill=_minif2f_run_skill(sandbox),
        run_id=task_id,
    )
    # reason: RFC 2026-04-22 §1 — forward task_id / sandbox_id so the base
    # ``Worker.__init__`` invariant is satisfied; ReActWorker passes them
    # through to super().
    return ReActWorker(
        name=name,
        model=model,
        task_id=task_id,
        sandbox_id=sandbox_id,
        tools=list(toolkit.get_tools()),
        system_prompt=MINIF2F_SYSTEM_PROMPT,
        max_iterations=30,
    )


def _swebench_react(
    *,
    name: str,
    model: str | None,
    task_id: UUID,
    sandbox_id: str,
) -> ReActWorker:
    """Registry factory: ReActWorker wired with a live SWE-Bench toolkit."""
    sandbox = SWEBenchSandboxManager().get_sandbox(task_id)
    if sandbox is None:
        raise RuntimeError(
            f"SWE-Bench factory requires a live sandbox for task_id={task_id}; "
            "SandboxSetupRequest must have completed (including "
            "_install_dependencies) before worker-execute runs."
        )
    toolkit = SWEBenchToolkit(sandbox=sandbox, workdir="/workspace/repo")
    # reason: RFC 2026-04-22 §1 — forward task_id / sandbox_id so the base
    # ``Worker.__init__`` invariant is satisfied.
    return ReActWorker(
        name=name,
        model=model,
        task_id=task_id,
        sandbox_id=sandbox_id,
        tools=list(toolkit.get_tools()),
        system_prompt=SWEBENCH_SYSTEM_PROMPT,
        max_iterations=50,
    )


# Registry maps worker slug → a factory callable accepting
# ``(name=..., model=..., task_id=..., sandbox_id=...)`` that returns a
# ready-to-run Worker. Plain subclasses are referenced directly now that
# base ``Worker.__init__`` requires ``task_id`` and ``sandbox_id``; benchmark
# factories (``_minif2f_react``, ``_swebench_react``) close over their
# sandbox manager and pre-bind a concrete toolkit + system prompt +
# iteration budget. RFC 2026-04-22 §1 + Open Question 1 resolution (c)
# (make IDs required on base Worker, drop ``_plain`` shim).
WORKERS: dict[str, WorkerFactory] = {
    "training-stub": TrainingStubWorker,
    # NOTE: bare `"react-v1": ReActWorker` entry removed (RFC 2026-04-22 §1).
    # Every real use binds a concrete toolkit via a factory closure below.
    "minif2f-react": _minif2f_react,
    "swebench-react": _swebench_react,
    # Test-only smoke workers register via tests/e2e/_fixtures/__init__.py;
    # they do NOT appear here (production CLI paths don't import tests).
}

BENCHMARKS: dict[str, type[Benchmark]] = {
    "minif2f": MiniF2FBenchmark,
    "swebench-verified": SweBenchVerifiedBenchmark,
    # ``researchrubrics-smoke`` / ``smoke-test`` benchmarks retired alongside
    # the canonical-smoke refactor (see
    # docs/architecture/07_testing.md §canonical-smoke).  Smoke uses each
    # benchmark's real sandbox image via the test-fixture registrations.
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "staged-rubric": StagedRubric,
    "minif2f-rubric": MiniF2FRubric,
    "swebench-rubric": SWEBenchRubric,
    # Stub rubrics + smoke rubrics retired.  Test-only smoke criteria
    # register via tests/e2e/_fixtures/__init__.py.
}

SANDBOX_MANAGERS: dict[str, type[BaseSandboxManager]] = {
    "gdpeval": GDPEvalSandboxManager,
    "minif2f": MiniF2FSandboxManager,
    "swebench-verified": SWEBenchSandboxManager,
}

SANDBOX_TEMPLATES: dict[str, Path] = {
    "minif2f": Path(__file__).parent / "benchmarks/minif2f/sandbox",
    "swebench-verified": Path(__file__).parent / "benchmarks/swebench_verified/sandbox",
}
