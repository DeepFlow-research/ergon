from __future__ import annotations

import json
from itertools import islice

import pytest

from ergon_builtins.benchmarks.swebench_verified.benchmark import SweBenchTask
from ergon_builtins.benchmarks.swebench_verified.task_schemas import (
    SWEBenchInstance,
    SWEBenchTaskPayload,
)
from ergon_core.api import Sample


class FakeSweBenchRow(SWEBenchInstance):
    needs_ui: bool = False


def test_swebench_environment_returns_samples(swebench_environment_factory) -> None:
    env = swebench_environment_factory(limit=1)

    sample = next(iter(env.iter_samples()))

    assert isinstance(sample, Sample)
    assert sample.sample_key == "swe-1"
    assert sample.environment_name == env.name
    assert sample.tasks
    assert sample.tasks[0].worker is not None
    assert sample.tasks[0].sandbox is not None
    assert sample.tasks[0].evaluators
    assert isinstance(sample.tasks[0], SweBenchTask)
    assert isinstance(sample.tasks[0].task_payload, SWEBenchTaskPayload)


def test_swebench_streaming_environment_yields_samples_without_all_samples(
    worker,
    evaluator,
    sandbox,
    swebench_environment_factory,
) -> None:
    env = swebench_environment_factory(
        limit=2,
        streaming=True,
        worker=worker,
        evaluators=[evaluator],
        sandbox=sandbox,
    )

    samples = list(islice(env.iter_samples(), 2))

    assert len(samples) == 2
    with pytest.raises(NotImplementedError):
        env.all_samples()


def test_swebench_environment_resolves_row_dependent_components(
    robot_worker,
    researcher_worker,
    ui_eval,
    patch_eval,
    browser_sandbox,
    repo_sandbox,
    swebench_environment_factory,
) -> None:
    rows = [
        FakeSweBenchRow(
            instance_id="ui",
            repo="org/repo",
            base_commit="abcdef123456",
            problem_statement="Fix the UI.",
            version="1.0",
            fail_to_pass=["tests/test_ui.py::test_fix"],
            pass_to_pass=[],
            environment_setup_commit="abcdef123456",
            test_patch="diff --git a/tests/test_ui.py b/tests/test_ui.py\n",
            needs_ui=True,
        ),
        FakeSweBenchRow(
            instance_id="patch",
            repo="org/repo",
            base_commit="abcdef123456",
            problem_statement="Fix the patch.",
            version="1.0",
            fail_to_pass=["tests/test_patch.py::test_fix"],
            pass_to_pass=[],
            environment_setup_commit="abcdef123456",
            test_patch="diff --git a/tests/test_patch.py b/tests/test_patch.py\n",
            needs_ui=False,
        ),
    ]
    env = swebench_environment_factory(
        rows=rows,
        worker=lambda row: robot_worker if row.needs_ui else researcher_worker,
        evaluators=lambda row: [ui_eval] if row.needs_ui else [patch_eval],
        sandbox=lambda row: browser_sandbox if row.needs_ui else repo_sandbox,
    )

    samples = list(env.iter_samples())

    assert samples[0].tasks[0].worker is robot_worker
    assert samples[0].tasks[0].evaluators == (ui_eval,)
    assert samples[0].tasks[0].sandbox is browser_sandbox
    assert samples[1].tasks[0].worker is researcher_worker
    assert samples[1].tasks[0].evaluators == (patch_eval,)
    assert samples[1].tasks[0].sandbox is repo_sandbox


def test_swebench_sample_provenance_is_json_safe(swebench_environment_factory) -> None:
    sample = next(iter(swebench_environment_factory(limit=1).iter_samples()))

    json.dumps(sample.sample_ref)
    json.dumps(sample.source_metadata)
