"""Ensure the public ``Tool`` alias is exported from ``ergon_core.api``."""


def test_tool_is_reexported_from_api_root() -> None:
    from ergon_core.api import Tool  # noqa: F401 — import is the assertion

    # Defining a function with list[Tool] must type-check (Tool is callable as a type hint).
    def _takes_tools(tools: list[Tool]) -> int:
        return len(tools)

    assert _takes_tools([]) == 0
    assert _takes_tools([object(), object()]) == 2


def test_tool_module_is_importable() -> None:
    from ergon_core.api import types as api_types

    assert hasattr(api_types, "Tool")
