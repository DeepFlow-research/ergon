"""Smoke test benchmark for h_arcane pipeline validation.

This benchmark validates the h_arcane execution pipeline including
evaluation with real E2B sandboxes for code rule evaluation.

Usage:
    # Via CLI
    python -m h_arcane.benchmarks.smoke_test.cli list
    python -m h_arcane.benchmarks.smoke_test.cli run --workflow single

    # Via Python API
    from h_arcane.benchmarks.smoke_test import (
        SMOKE_TEST_CONFIG,
        SmokeTestToolkit,
        MockStakeholder,
        SmokeTestSandboxManager,
        create_workflow,
        load_smoke_test_to_database,
    )
"""

from h_arcane.benchmarks.smoke_test.config import SMOKE_TEST_CONFIG
from h_arcane.benchmarks.smoke_test.factories import (
    create_stakeholder,
    create_toolkit,
)
from h_arcane.benchmarks.smoke_test.loader import (
    SMOKE_TEST_TASKS,
    SmokeTestTask,
    get_smoke_test_tasks,
    load_smoke_test_to_database,
)
from h_arcane.benchmarks.smoke_test.sandbox import SmokeTestSandboxManager
from h_arcane.benchmarks.smoke_test.stakeholder import MockStakeholder
from h_arcane.benchmarks.smoke_test.stub_responses import (
    StubAnalyzeResponse,
    StubReadFileResponse,
    StubWriteFileResponse,
)
from h_arcane.benchmarks.smoke_test.toolkit import SmokeTestToolkit
from h_arcane.benchmarks.smoke_test.workflows import (
    WORKFLOW_FACTORIES,
    create_linear_chain_workflow,
    create_nested_hierarchy_workflow,
    create_parallel_workflow,
    create_single_task_workflow,
    create_workflow,
    list_workflows,
)

__all__ = [
    # Config
    "SMOKE_TEST_CONFIG",
    # Factories
    "create_stakeholder",
    "create_toolkit",
    # Loader
    "SMOKE_TEST_TASKS",
    "SmokeTestTask",
    "get_smoke_test_tasks",
    "load_smoke_test_to_database",
    # Core components
    "SmokeTestSandboxManager",
    "MockStakeholder",
    "SmokeTestToolkit",
    # Stub responses
    "StubAnalyzeResponse",
    "StubReadFileResponse",
    "StubWriteFileResponse",
    # Workflows
    "WORKFLOW_FACTORIES",
    "create_linear_chain_workflow",
    "create_nested_hierarchy_workflow",
    "create_parallel_workflow",
    "create_single_task_workflow",
    "create_workflow",
    "list_workflows",
]
