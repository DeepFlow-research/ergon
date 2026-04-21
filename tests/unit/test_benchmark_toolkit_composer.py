"""benchmark_toolkit_composer: per-benchmark DI factory for generic ReAct."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from ergon_builtins.tools.benchmark_toolkit_composer import compose_benchmark_toolkit


def _make_ctx() -> SimpleNamespace:
    return SimpleNamespace(
        run_id=uuid4(),
        node_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sb-test",
        task_id=uuid4(),
        definition_id=None,
        metadata={},
    )


def test_compose_researchrubrics_unions_lifecycle_rr_and_graph() -> None:
    tools = compose_benchmark_toolkit(
        benchmark_slug="researchrubrics",
        ctx=_make_ctx(),
        sandbox=MagicMock(),
        run_skill=MagicMock(),
        publisher_sync=MagicMock(),
    )
    # Minimum union size: 8 (lifecycle) + 6 (rr) + 6 (graph) = 20
    assert len(tools) >= 20


def test_compose_minif2f_unions_lifecycle_and_minif2f() -> None:
    tools = compose_benchmark_toolkit(
        benchmark_slug="minif2f",
        ctx=_make_ctx(),
        sandbox=MagicMock(),
        run_skill=MagicMock(),
    )
    # Minimum: 8 (lifecycle) + Lean toolkit (>=4, no ask_stakeholder_fn) = 12
    assert len(tools) >= 12


def test_compose_swebench_unions_lifecycle_and_swebench() -> None:
    tools = compose_benchmark_toolkit(
        benchmark_slug="swebench-verified",
        ctx=_make_ctx(),
        sandbox=MagicMock(),
    )
    # Minimum: 8 (lifecycle) + bash + str-replace = 10
    assert len(tools) >= 10


def test_compose_unknown_slug_raises() -> None:
    with pytest.raises(ValueError, match="no toolkit composer for"):
        compose_benchmark_toolkit(
            benchmark_slug="unknown",
            ctx=_make_ctx(),
            sandbox=MagicMock(),
        )
