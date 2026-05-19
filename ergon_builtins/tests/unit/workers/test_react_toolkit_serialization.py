"""ReAct toolkit serialization stays owned by builtins, not core Worker."""

from typing import Any

import pytest

from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit
from ergon_builtins.benchmarks.minif2f.workers import make_minif2f_worker
from ergon_builtins.workers.baselines.toolkit import Toolkit


def test_react_worker_serializes_concrete_toolkit_fields() -> None:
    worker = make_minif2f_worker()
    worker.toolkit = MiniF2FToolkit(max_tool_calls=16)

    serialized = worker.model_dump(mode="json")

    assert serialized["toolkit"]["_type"].endswith(":MiniF2FToolkit")
    assert serialized["toolkit"]["max_tool_calls"] == 16


def test_react_worker_rehydrates_concrete_toolkit() -> None:
    worker = make_minif2f_worker()
    worker.toolkit = MiniF2FToolkit(max_tool_calls=16)

    rebuilt = type(worker).model_validate(worker.model_dump(mode="json"))

    assert type(rebuilt.toolkit) is MiniF2FToolkit
    assert rebuilt.toolkit.max_tool_calls == 16


def test_toolkit_from_definition_requires_type_discriminator() -> None:
    with pytest.raises(ValueError, match="Toolkit snapshot.*`_type`"):
        Toolkit.from_definition({"label": "missing"})


def test_toolkit_from_definition_rejects_non_toolkit_type() -> None:
    with pytest.raises(TypeError, match="Toolkit _type.*Toolkit subclass"):
        Toolkit.from_definition({"_type": "ergon_core.api.benchmark.task:Task", "label": "wrong"})


class _NoopToolkit(Toolkit):
    label: str = "fake"

    def tools(self, sandbox: Any, task: Any) -> list:
        return []


def test_toolkit_from_definition_rehydrates_builtin_subclass() -> None:
    original = _NoopToolkit(label="roundtrip")

    rebuilt = Toolkit.from_definition(original.model_dump(mode="json"))

    assert type(rebuilt) is _NoopToolkit
    assert rebuilt.label == "roundtrip"
