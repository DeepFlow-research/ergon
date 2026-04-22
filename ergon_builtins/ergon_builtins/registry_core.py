"""Components with no dependencies beyond ergon-core.

All imports are eager and fully typed.  This module is always safe to import
regardless of which optional extras are installed.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from ergon_core.api import Benchmark, Evaluator, Worker
from ergon_core.core.providers.generation.model_resolution import ResolvedModel
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

from ergon_builtins.benchmarks.gdpeval.rubric import StagedRubric
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.benchmarks.minif2f.smoke_rubric import MiniF2FSmokeRubric
from ergon_builtins.benchmarks.researchrubrics.smoke import (
    ResearchRubricsSmokeTestBenchmark,
)
from ergon_builtins.benchmarks.researchrubrics.smoke_rubric import (
    ResearchRubricsSmokeRubric,
)
from ergon_builtins.benchmarks.smoke_test.benchmark import SmokeTestBenchmark
from ergon_builtins.benchmarks.swebench_verified.benchmark import SweBenchVerifiedBenchmark
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.benchmarks.swebench_verified.smoke_rubric import SweBenchSmokeRubric
from ergon_builtins.evaluators.rubrics.stub_rubric import StubRubric
from ergon_builtins.evaluators.rubrics.swebench_rubric import SWEBenchRubric
from ergon_builtins.evaluators.rubrics.varied_stub_rubric import VariedStubRubric
from ergon_builtins.models.cloud_passthrough import resolve_cloud
from ergon_builtins.models.vllm_backend import resolve_vllm
from ergon_builtins.workers.baselines.manager_researcher_worker import ManagerResearcherWorker
from ergon_builtins.workers.baselines.react_prompts import (
    MINIF2F_SYSTEM_PROMPT,
    SWEBENCH_SYSTEM_PROMPT,
)
from ergon_builtins.workers.baselines.react_worker import ReActWorker
from ergon_builtins.workers.baselines.stub_worker import StubWorker
from ergon_builtins.workers.baselines.training_stub_worker import TrainingStubWorker
from ergon_builtins.workers.research_rubrics.stub_worker import (
    StubResearchRubricsWorker,
)
from ergon_builtins.workers.stubs.canonical_smoke_worker import CanonicalSmokeWorker


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
    # reason: lazy import so tests can monkeypatch `MiniF2FSandboxManager` on
    # its defining module and have the replacement picked up here.
    from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager

    # reason: paired lazy import with the sandbox_manager above — defer toolkit
    # import too so a bare `import registry_core` doesn't pull the toolkit.
    from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit

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
    # reason: lazy import to mirror the MiniF2F factory — keeps sandbox-manager
    # instantiation deferred until a sandbox is actually requested and lets
    # tests monkeypatch the manager on its defining module.
    from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
        SWEBenchSandboxManager as _Manager,
    )

    # reason: paired lazy import with the sandbox_manager above.
    from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit

    sandbox = _Manager().get_sandbox(task_id)
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
    "stub-worker": StubWorker,
    "training-stub": TrainingStubWorker,
    # NOTE: bare `"react-v1": ReActWorker` entry removed (RFC 2026-04-22 §1).
    # Every real use binds a concrete toolkit via a factory closure below.
    "minif2f-react": _minif2f_react,
    "swebench-react": _swebench_react,
    "manager-researcher": ManagerResearcherWorker,
    "researcher": StubWorker,
    "researchrubrics-stub": StubResearchRubricsWorker,
    "canonical-smoke": CanonicalSmokeWorker,
}

BENCHMARKS: dict[str, type[Benchmark]] = {
    "smoke-test": SmokeTestBenchmark,
    "minif2f": MiniF2FBenchmark,
    "researchrubrics-smoke": ResearchRubricsSmokeTestBenchmark,
    "swebench-verified": SweBenchVerifiedBenchmark,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "stub-rubric": StubRubric,
    "varied-stub-rubric": VariedStubRubric,
    "staged-rubric": StagedRubric,
    "minif2f-rubric": MiniF2FRubric,
    "swebench-rubric": SWEBenchRubric,
    "researchrubrics-smoke-rubric": ResearchRubricsSmokeRubric,
    "minif2f-smoke-rubric": MiniF2FSmokeRubric,
    "swebench-smoke-rubric": SweBenchSmokeRubric,
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

MODEL_BACKENDS: dict[str, Callable[..., ResolvedModel]] = {
    "vllm": resolve_vllm,
    "openai": resolve_cloud,
    "anthropic": resolve_cloud,
    "google": resolve_cloud,
}
