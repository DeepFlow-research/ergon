"""Tests for SWEBenchRubric."""

from ergon_builtins.benchmarks.swebench_verified.rubric import SWEBenchRubric


def test_rubric_contains_single_test_resolution_criterion() -> None:
    rubric = SWEBenchRubric(name="swebench-rubric")
    names = [c.slug for c in rubric.criteria]
    assert names == ["test-resolution"]
    assert rubric.criteria[0].weight == 1.0
