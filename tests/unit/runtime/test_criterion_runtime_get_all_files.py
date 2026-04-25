"""Unit tests for ``DefaultCriterionRuntime.get_all_files_for_task``.

The helper materializes every ``run_resources`` row scoped to
``(run_id, task_id)`` into ``{name: bytes}``.  On duplicate names the
newest ``created_at`` wins.

These tests use a mocked ``get_session`` (matching the existing
``test_criterion_runtime_di.py`` style) so they stay under ``tests/unit/``
without requiring a real database fixture.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ergon_core.core.runtime.evaluation.criterion_runtime import (
    CriterionRuntimeOptions,
    DefaultCriterionRuntime,
)
from ergon_core.core.runtime.evaluation.evaluation_schemas import CriterionContext


def _row(*, name: str, file_path: str, created_at: datetime) -> MagicMock:
    """Build a MagicMock that looks like a ``RunResource`` ORM row."""
    row = MagicMock()
    row.name = name
    row.file_path = file_path
    row.created_at = created_at
    return row


def _make_runtime(
    *,
    run_id=None,
    task_id=None,
) -> DefaultCriterionRuntime:
    context = CriterionContext(
        run_id=run_id or uuid4(),
        task_input="test task",
        agent_reasoning="test output",
    )
    return DefaultCriterionRuntime(
        context=context,
        sandbox_manager=MagicMock(),
        options=CriterionRuntimeOptions(run_id=run_id, task_id=task_id),
    )


def _patch_session_with_rows(rows: list[MagicMock]):
    """Return a context manager patching ``get_session`` to yield ``rows``."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.exec.return_value.all.return_value = rows
    return patch(
        "ergon_core.core.runtime.evaluation.criterion_runtime.get_session",
        return_value=mock_session,
    )


@pytest.mark.asyncio
async def test_returns_materialized_bytes(tmp_path: Path) -> None:
    """Every row's file_path is read and returned in ``{name: bytes}``."""
    a_path = tmp_path / "a.bin"
    a_path.write_bytes(b"hello")
    b_path = tmp_path / "b.bin"
    b_path.write_bytes(b"\x00\x01\x02")

    now = datetime.now(UTC)
    rows = [
        _row(name="a.txt", file_path=str(a_path), created_at=now),
        _row(name="b.bin", file_path=str(b_path), created_at=now - timedelta(seconds=1)),
    ]

    runtime = _make_runtime(run_id=uuid4(), task_id=uuid4())
    with _patch_session_with_rows(rows):
        result = await runtime.get_all_files_for_task()

    assert result == {"a.txt": b"hello", "b.bin": b"\x00\x01\x02"}


@pytest.mark.asyncio
async def test_dedups_keeping_newest(tmp_path: Path) -> None:
    """When a name appears twice, the newest ``created_at`` wins."""
    old_path = tmp_path / "old.lean"
    old_path.write_bytes(b"old")
    new_path = tmp_path / "new.lean"
    new_path.write_bytes(b"NEW")

    now = datetime.now(UTC)
    # ORDER BY created_at DESC -> newest first
    rows = [
        _row(name="proof.lean", file_path=str(new_path), created_at=now),
        _row(
            name="proof.lean",
            file_path=str(old_path),
            created_at=now - timedelta(seconds=5),
        ),
    ]

    runtime = _make_runtime(run_id=uuid4(), task_id=uuid4())
    with _patch_session_with_rows(rows):
        result = await runtime.get_all_files_for_task()

    assert result == {"proof.lean": b"NEW"}


@pytest.mark.asyncio
async def test_returns_empty_when_task_id_is_none() -> None:
    """Without a task_id, the helper returns ``{}`` and doesn't hit the DB."""
    runtime = _make_runtime(run_id=uuid4(), task_id=None)

    with patch("ergon_core.core.runtime.evaluation.criterion_runtime.get_session") as mock_get:
        result = await runtime.get_all_files_for_task()

    assert result == {}
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_returns_empty_when_no_rows() -> None:
    """Zero rows → empty dict."""
    runtime = _make_runtime(run_id=uuid4(), task_id=uuid4())
    with _patch_session_with_rows([]):
        result = await runtime.get_all_files_for_task()
    assert result == {}
