"""Contract tests for the base `Worker.__init__` signature."""

import inspect

from ergon_core.api import Worker


def test_model_kwarg_has_no_default() -> None:
    """`model` must be keyword-only AND have no default value.

    Defaults on worker `__init__` are an anti-pattern (RFC 2026-04-22):
    they hide sizing decisions. Factories must pass `model=` explicitly.
    """
    sig = inspect.signature(Worker.__init__)
    model_param = sig.parameters["model"]
    assert model_param.kind == inspect.Parameter.KEYWORD_ONLY, (
        f"`model` must be keyword-only, got {model_param.kind}"
    )
    assert model_param.default is inspect.Parameter.empty, (
        f"`model` must have no default; got {model_param.default!r}"
    )


def test_name_kwarg_has_no_default() -> None:
    sig = inspect.signature(Worker.__init__)
    name_param = sig.parameters["name"]
    assert name_param.kind == inspect.Parameter.KEYWORD_ONLY
    assert name_param.default is inspect.Parameter.empty
