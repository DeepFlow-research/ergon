"""Smoke-test the new registry factory signatures."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from ergon_builtins.registry_core import WORKERS
from ergon_core.api import Worker


def test_registry_does_not_export_benchmark_profiles() -> None:
    """Benchmark slugs should not imply worker/evaluator/sandbox defaults."""
    from ergon_builtins import registry
    from ergon_builtins import registry_core

    assert not hasattr(registry_core, "BENCHMARK_PROFILES")
    assert not hasattr(registry, "BENCHMARK_PROFILES")


def test_no_bare_react_v1_entry() -> None:
    """RFC §1: `react-v1` bare entry removed — every factory binds a concrete toolkit."""
    assert "react-v1" not in WORKERS, (
        "Bare `react-v1` entry must not exist post-RFC. Use `minif2f-react` or "
        "`swebench-react` instead."
    )


def test_shared_authoring_import_surfaces_exist() -> None:
    """Generic built-in primitives should be available from ergon_builtins.shared."""
    from ergon_builtins.shared.criteria.code_check import CodeCheckCriterion
    from ergon_builtins.shared.criteria.llm_judge import LLMJudgeCriterion
    from ergon_builtins.shared.criteria.sandbox_file_check import SandboxFileCheckCriterion
    from ergon_builtins.shared.models.resolution import resolve_model_target
    from ergon_builtins.shared.workers.react_worker import ReActWorker
    from ergon_builtins.shared.workers.training_stub_worker import TrainingStubWorker

    assert ReActWorker.type_slug == "react-v1"
    assert TrainingStubWorker.type_slug == "training-stub"
    assert CodeCheckCriterion.type_slug == "code-check"
    assert LLMJudgeCriterion.type_slug == "llm-judge"
    assert SandboxFileCheckCriterion.type_slug == "sandbox-file-check"
    assert callable(resolve_model_target)


def test_training_stub_factory_accepts_new_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-benchmark factories must accept `task_id` / `sandbox_id` kwargs (option a)."""
    factory = WORKERS["training-stub"]
    worker = factory(
        name="training-stub-under-test",
        model=None,
        task_id=uuid4(),
        sandbox_id="sbx-abc",
    )
    assert isinstance(worker, Worker)
    assert worker.name == "training-stub-under-test"


def test_benchmark_react_factories_live_with_benchmarks() -> None:
    """Benchmark-specific ReAct wiring should not live in the global registry module."""
    from ergon_builtins import registry_core
    from ergon_builtins.benchmarks.minif2f.worker_factory import minif2f_react
    from ergon_builtins.benchmarks.swebench_verified.worker_factory import swebench_react
    from ergon_builtins.benchmarks.swebench_verified.rubric import SWEBenchRubric
    from ergon_builtins.evaluators.rubrics.swebench_rubric import (
        SWEBenchRubric as LegacySWEBenchRubric,
    )

    assert registry_core.WORKERS["minif2f-react"] is minif2f_react
    assert registry_core.WORKERS["swebench-react"] is swebench_react
    assert registry_core.EVALUATORS["swebench-rubric"] is SWEBenchRubric
    assert LegacySWEBenchRubric is SWEBenchRubric


def test_gdpeval_react_factory_lives_with_benchmark(monkeypatch: pytest.MonkeyPatch) -> None:
    """GDPEval should expose a benchmark-owned ReAct factory through registry_data."""
    pytest.importorskip("datasets", reason="ergon-builtins[data] not installed")
    from ergon_builtins.benchmarks.gdpeval import worker_factory
    from ergon_builtins.registry_data import WORKERS as DATA_WORKERS

    assert DATA_WORKERS["gdpeval-react"] is worker_factory.gdpeval_react

    fake_toolkit = MagicMock()
    fake_toolkit.get_tools.return_value = ["read_pdf", "run_python"]
    monkeypatch.setattr(worker_factory, "GDPEvalToolkit", lambda **kwargs: fake_toolkit)
    monkeypatch.setattr(worker_factory, "GDPEvalSandboxManager", lambda: MagicMock())

    task_id = uuid4()
    worker = DATA_WORKERS["gdpeval-react"](
        name="gdpeval-test",
        model="openai:gpt-4o",
        task_id=task_id,
        sandbox_id="sbx-gdp",
    )

    assert isinstance(worker, Worker)
    assert worker.tools == ["read_pdf", "run_python"]
    assert worker.max_iterations == 40
    fake_toolkit.get_tools.assert_called_once_with()


def test_researchrubrics_workers_are_reexported_from_benchmark_factory() -> None:
    """ResearchRubrics worker registry entries should come from the benchmark package."""
    pytest.importorskip("datasets", reason="ergon-builtins[data] not installed")
    from ergon_builtins.benchmarks.researchrubrics.worker_factory import (
        ResearchRubricsResearcherWorker,
        ResearchRubricsWorkflowCliReActWorker,
    )
    from ergon_builtins.registry_data import WORKERS as DATA_WORKERS

    assert DATA_WORKERS["researchrubrics-researcher"] is ResearchRubricsResearcherWorker
    assert (
        DATA_WORKERS["researchrubrics-workflow-cli-react"]
        is ResearchRubricsWorkflowCliReActWorker
    )


def test_minif2f_factory_builds_toolkit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The minif2f factory must construct a live toolkit bound to the sandbox."""
    # reason: imports deferred to avoid pulling registry_core + sandbox_manager
    # eagerly into test collection. Every test pulls its own patch target.
    # reason: only needed for MagicMock spec= below; eager import would pull
    # the benchmark sandbox module into all registry tests.
    from ergon_builtins.benchmarks.minif2f import sandbox_manager as sm_mod

    from ergon_builtins.benchmarks.minif2f import worker_factory

    fake_sandbox = MagicMock(name="fake-sandbox")
    fake_manager = MagicMock(spec=sm_mod.MiniF2FSandboxManager)
    fake_manager.get_sandbox.return_value = fake_sandbox
    # Patch on the call-site module so the test does not depend on lazy
    # imports inside the factory.
    monkeypatch.setattr(worker_factory, "MiniF2FSandboxManager", lambda: fake_manager)

    factory = WORKERS["minif2f-react"]
    task_id = uuid4()
    worker = factory(
        name="minif2f-test",
        model=None,
        task_id=task_id,
        sandbox_id="sbx-minif2f",
    )
    assert isinstance(worker, Worker)
    # Factory should have asked the manager for the sandbox
    fake_manager.get_sandbox.assert_called_once_with(task_id)
    # MiniF2FToolkit without ask_stakeholder_fn publishes exactly 4 tools:
    # write_lean_file, check_lean_file, verify_lean_proof, search_lemmas
    assert len(worker.tools) == 4
    # `max_iterations` must be explicit — 30 is the MiniF2F budget from the old adapter
    assert worker.max_iterations == 30
