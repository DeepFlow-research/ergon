"""Training stub worker behavior."""

from ergon_builtins.workers.training_stub_worker import _build_synthetic_chunks


def test_training_stub_chunks_are_deterministic_for_same_seed_and_task() -> None:
    first = _build_synthetic_chunks("task-a", seed=123)
    second = _build_synthetic_chunks("task-a", seed=123)

    assert first == second


def test_training_stub_chunks_change_by_task_slug() -> None:
    first = _build_synthetic_chunks("task-a", seed=123)
    second = _build_synthetic_chunks("task-b", seed=123)

    assert first != second
