"""Smoke tests for SpawnedTaskHandle."""

import uuid

import pytest

from ergon_core.api import SpawnedTaskHandle as SpawnedTaskHandleFromApi
from ergon_core.api.worker import SpawnedTaskHandle as SpawnedTaskHandleFromWorker


def test_importable_from_both_paths() -> None:
    assert SpawnedTaskHandleFromApi is SpawnedTaskHandleFromWorker


def test_instantiates_with_uuid() -> None:
    task_id = uuid.uuid4()
    handle = SpawnedTaskHandleFromApi(task_id=task_id)
    assert handle.task_id == task_id


@pytest.mark.asyncio
async def test_wait_raises_not_implemented() -> None:
    handle = SpawnedTaskHandleFromApi(task_id=uuid.uuid4())
    with pytest.raises(NotImplementedError, match="await_completion is deferred in v2"):
        await handle.wait()
