"""Tests for SWE-Bench task schemas."""

import pytest

from ergon_builtins.benchmarks.swebench_verified.task_schemas import (
    SWEBenchInstance,
    SWEBenchTaskPayload,
    _parse_test_list,  # noqa: PLC2701
)


RAW_ROW = {
    "instance_id": "django__django-11999",
    "repo": "django/django",
    "base_commit": "deadbeef",
    "patch": "--- gold patch, worker must not see ---",
    "test_patch": "--- test patch, evaluator only ---",
    "problem_statement": "Fix the thing.",
    "hints_text": "maybe look at foo.py",
    "version": "3.0",
    "FAIL_TO_PASS": '["tests.test_foo.TestFoo.test_fix"]',
    "PASS_TO_PASS": '["tests.test_foo.TestFoo.test_existing"]',
    "environment_setup_commit": "cafebabe",
}


def test_instance_parses_json_encoded_test_lists() -> None:
    instance = SWEBenchInstance.from_raw(RAW_ROW)
    assert instance.fail_to_pass == ["tests.test_foo.TestFoo.test_fix"]
    assert instance.pass_to_pass == ["tests.test_foo.TestFoo.test_existing"]


def test_payload_from_instance_strips_gold_patch() -> None:
    instance = SWEBenchInstance.from_raw(RAW_ROW)
    payload = SWEBenchTaskPayload.from_instance(instance)
    dumped = payload.model_dump()
    assert "patch" not in dumped
    assert dumped["test_patch"] == RAW_ROW["test_patch"]
    assert dumped["problem_statement"] == RAW_ROW["problem_statement"]


def test_worker_description_excludes_test_patch() -> None:
    instance = SWEBenchInstance.from_raw(RAW_ROW)
    payload = SWEBenchTaskPayload.from_instance(instance)
    description = payload.build_worker_description()
    assert RAW_ROW["problem_statement"] in description
    assert "test patch" not in description
    assert "gold patch" not in description


def test_parse_test_list_accepts_list() -> None:
    assert _parse_test_list(["a", "b"]) == ["a", "b"]


def test_parse_test_list_accepts_json_string() -> None:
    assert _parse_test_list('["a", "b"]') == ["a", "b"]


def test_parse_test_list_rejects_json_non_list() -> None:
    with pytest.raises(TypeError):
        _parse_test_list('"just a string"')


def test_parse_test_list_rejects_unknown_type() -> None:
    with pytest.raises(TypeError):
        _parse_test_list(42)
