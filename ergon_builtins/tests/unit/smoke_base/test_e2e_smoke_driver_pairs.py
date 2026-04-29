from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    ("module_name", "happy_worker", "sad_worker", "criterion"),
    [
        (
            "tests.e2e.test_researchrubrics_smoke",
            "researchrubrics-smoke-worker",
            "researchrubrics-sadpath-smoke-worker",
            "researchrubrics-smoke-criterion",
        ),
        (
            "tests.e2e.test_minif2f_smoke",
            "minif2f-smoke-worker",
            "minif2f-sadpath-smoke-worker",
            "minif2f-smoke-criterion",
        ),
        (
            "tests.e2e.test_swebench_smoke",
            "swebench-smoke-worker",
            "swebench-sadpath-smoke-worker",
            "swebench-smoke-criterion",
        ),
    ],
)
def test_e2e_smoke_driver_builds_happy_sad_pairs(
    module_name: str,
    happy_worker: str,
    sad_worker: str,
    criterion: str,
) -> None:
    module = importlib.import_module(module_name)

    assert module._smoke_slots(2) == [
        ("happy", happy_worker, criterion),
        ("sad", sad_worker, criterion),
        ("happy", happy_worker, criterion),
        ("sad", sad_worker, criterion),
    ]


def test_build_cohort_payload_includes_explicit_runtime_choices() -> None:
    submit = importlib.import_module("tests.e2e._submit")

    payload = submit.build_cohort_payload(
        benchmark_slug="minif2f",
        slots=[("minif2f-smoke-worker", "minif2f-smoke-criterion")],
        cohort_key="ci-smoke-minif2f",
        sandbox_slug="minif2f",
        dependency_extras=("none",),
        model="openai:gpt-4o",
    )

    assert payload["benchmark_slug"] == "minif2f"
    assert payload["sandbox_slug"] == "minif2f"
    assert payload["dependency_extras"] == ["none"]
    assert payload["model"] == "openai:gpt-4o"
    assert payload["slots"] == [
        {
            "worker_slug": "minif2f-smoke-worker",
            "evaluator_slug": "minif2f-smoke-criterion",
        }
    ]
