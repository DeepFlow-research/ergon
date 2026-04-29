"""Documented built-in benchmark pairings are explicit and registered."""

import pytest

from ergon_core.api.registry import ComponentRegistry


CORE_PAIRINGS = [
    {
        "benchmark": "minif2f",
        "worker": "minif2f-react",
        "evaluator": "minif2f-rubric",
        "sandbox": "minif2f",
        "extras": ("none",),
    },
    {
        "benchmark": "swebench-verified",
        "worker": "swebench-react",
        "evaluator": "swebench-rubric",
        "sandbox": "swebench-verified",
        "extras": ("ergon-builtins[data]",),
    },
]

DATA_PAIRINGS = [
    {
        "benchmark": "gdpeval",
        "worker": "gdpeval-react",
        "evaluator": "gdpeval-staged-rubric",
        "sandbox": "gdpeval",
        "extras": ("ergon-builtins[data]",),
    },
    {
        "benchmark": "researchrubrics",
        "worker": "researchrubrics-researcher",
        "evaluator": "researchrubrics-rubric",
        "sandbox": "researchrubrics",
        "extras": ("ergon-builtins[data]",),
    },
    {
        "benchmark": "researchrubrics-vanilla",
        "worker": "researchrubrics-researcher",
        "evaluator": "researchrubrics-rubric",
        "sandbox": "researchrubrics-vanilla",
        "extras": ("ergon-builtins[data]",),
    },
]


@pytest.mark.parametrize("pairing", CORE_PAIRINGS)
def test_core_pairings_reference_registered_slugs(pairing: dict[str, object]) -> None:
    from ergon_builtins.registry_core import register_core_builtins

    registry = ComponentRegistry()
    register_core_builtins(registry)

    _assert_pairing(pairing, registry)


@pytest.mark.parametrize("pairing", DATA_PAIRINGS)
def test_data_pairings_reference_registered_slugs(pairing: dict[str, object]) -> None:
    pytest.importorskip("datasets", reason="ergon-builtins[data] not installed")
    from ergon_builtins.registry import register_builtins

    registry = ComponentRegistry()
    register_builtins(registry)

    _assert_pairing(pairing, registry)


def _assert_pairing(
    pairing: dict[str, object],
    registry: ComponentRegistry,
) -> None:
    benchmark = pairing["benchmark"]
    worker = pairing["worker"]
    evaluator = pairing["evaluator"]
    sandbox = pairing["sandbox"]
    extras = pairing["extras"]

    assert benchmark in registry.benchmarks
    assert worker in registry.workers
    assert evaluator in registry.evaluators
    assert sandbox in registry.sandbox_managers
    assert isinstance(extras, tuple)
    assert extras
