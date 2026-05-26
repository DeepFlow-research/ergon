import pytest
from uuid import uuid4

from ergon_core.api import Sample
from ergon_core.test_support.task_factory import task_with_id


def make_task(*, key: str, dependencies: tuple[str, ...] = ()):
    return task_with_id(
        uuid4(),
        task_slug=key,
        instance_key=key,
        description=f"Task {key}",
        dependency_task_slugs=dependencies,
    )


def test_sample_requires_concrete_tasks() -> None:
    sample = Sample(
        name="mini:1",
        sample_key="1",
        environment_name="mini-validation",
        tasks=[make_task(key="solve")],
    )

    sample.validate_runnable()
    assert sample.tasks[0].task_slug == "solve"
    assert sample.task_count() == 1
    assert sample.root_tasks()[0].task_slug == "solve"
    assert sample.task_by_key("solve").task_slug == "solve"


def test_sample_rejects_duplicate_task_keys() -> None:
    with pytest.raises(ValueError, match="unique"):
        Sample.from_tasks(
            name="bad",
            sample_key="bad",
            environment_name="mini",
            tasks=[make_task(key="solve"), make_task(key="solve")],
        )


def test_sample_rejects_unknown_dependency() -> None:
    with pytest.raises(ValueError, match="Unknown dependency"):
        Sample.from_tasks(
            name="bad",
            sample_key="bad",
            environment_name="mini",
            tasks=[make_task(key="solve", dependencies=("missing",))],
        )


def test_sample_task_by_key_raises_for_unknown_task() -> None:
    sample = Sample.from_tasks(
        name="mini:1",
        sample_key="1",
        environment_name="mini-validation",
        tasks=[make_task(key="solve")],
    )

    with pytest.raises(KeyError):
        sample.task_by_key("missing")
