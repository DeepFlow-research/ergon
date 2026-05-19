"""Smoke-test the new registry factory signatures."""

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


def test_training_stub_factory_accepts_authoring_configuration() -> None:
    """Non-benchmark worker classes only need authoring configuration."""
    factory = WORKERS["training-stub"]
    worker = factory(
        name="training-stub-under-test",
        model=None,
    )
    assert isinstance(worker, Worker)
    assert worker.name == "training-stub-under-test"


def test_benchmark_react_workers_live_with_benchmarks() -> None:
    """Benchmark-specific ReAct workers should not live in the global registry module."""
    from ergon_builtins import registry_core
    from ergon_builtins.benchmarks.minif2f._legacy_workers import MiniF2FReactWorker
    from ergon_builtins.benchmarks.swebench_verified.worker_factory import SWEBenchReactWorker
    from ergon_builtins.benchmarks.swebench_verified.rubric import SWEBenchRubric
    from ergon_builtins.evaluators.rubrics.swebench_rubric import (
        SWEBenchRubric as LegacySWEBenchRubric,
    )

    assert registry_core.WORKERS["minif2f-react"] is MiniF2FReactWorker
    assert registry_core.WORKERS["swebench-react"] is SWEBenchReactWorker
    assert registry_core.EVALUATORS["swebench-rubric"] is SWEBenchRubric
    assert LegacySWEBenchRubric is SWEBenchRubric


def test_gdpeval_react_worker_lives_with_benchmark() -> None:
    """GDPEval should expose a benchmark-owned ReAct worker through registry_data."""
    pytest.importorskip("datasets", reason="ergon-builtins[data] not installed")
    from ergon_builtins.benchmarks.gdpeval import worker_factory
    from ergon_builtins.registry_data import WORKERS as DATA_WORKERS

    assert DATA_WORKERS["gdpeval-react"] is worker_factory.GDPEvalReactWorker

    worker = DATA_WORKERS["gdpeval-react"](name="gdpeval-test", model="openai:gpt-4o")
    assert worker.max_iterations == 40


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
        DATA_WORKERS["researchrubrics-workflow-cli-react"] is ResearchRubricsWorkflowCliReActWorker
    )


def test_minif2f_worker_defers_toolkit_until_execute() -> None:
    """The minif2f worker class is importable and builds tools at runtime."""
    worker_cls = WORKERS["minif2f-react"]
    worker = worker_cls(name="minif2f-test", model=None)

    assert isinstance(worker, Worker)
    assert worker._tools == []
    assert worker.max_iterations == 30
