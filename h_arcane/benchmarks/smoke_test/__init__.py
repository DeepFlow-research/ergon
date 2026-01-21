"""Smoke test benchmark for h_arcane pipeline validation.

This benchmark provides a lightweight way to validate the h_arcane execution
pipeline without requiring real E2B sandboxes. It uses stub tools that return
mock data instantly.

Usage:
    # Via CLI
    python -m h_arcane.benchmarks.smoke_test.cli list
    python -m h_arcane.benchmarks.smoke_test.cli run --workflow single

    # Via Python API
    from h_arcane.benchmarks.smoke_test import (
        SMOKE_TEST_CONFIG,
        SmokeTestToolkit,
        MockStakeholder,
        DummySandboxManager,
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
from h_arcane.benchmarks.smoke_test.sandbox import DummySandboxManager
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
    "DummySandboxManager",
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
