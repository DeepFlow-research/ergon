"""Contract tests for the post-RFC `ReActWorker.__init__` signature."""

import inspect

import pytest

from ergon_builtins.workers.baselines.react_worker import ReActWorker


def test_no_adapter_kwarg() -> None:
    sig = inspect.signature(ReActWorker.__init__)
    assert "adapter" not in sig.parameters, (
        "BenchmarkAdapter ABC is being deleted — ReActWorker must not accept an adapter kwarg."
    )


@pytest.mark.parametrize(
    "kwarg",
    ["name", "model", "tools", "system_prompt", "max_iterations"],
)
def test_all_kwargs_required_and_keyword_only(kwarg: str) -> None:
    sig = inspect.signature(ReActWorker.__init__)
    param = sig.parameters[kwarg]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        f"`{kwarg}` must be keyword-only; got {param.kind}"
    )
    assert param.default is inspect.Parameter.empty, (
        f"`{kwarg}` must have no default (RFC 2026-04-22 forbids nullable-with-default); "
        f"got {param.default!r}"
    )


def test_construct_with_minimal_explicit_kwargs() -> None:
    """A ReActWorker can be built with explicit [] tools and None prompt."""
    worker = ReActWorker(
        name="unit",
        model=None,
        tools=[],
        system_prompt=None,
        max_iterations=1,
    )
    assert worker.name == "unit"
    assert worker.model is None
    assert worker.tools == []
    assert worker.system_prompt is None
    assert worker.max_iterations == 1
