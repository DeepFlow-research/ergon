"""Unit tests for the DI-extended ``DefaultCriterionRuntime``.

Covers the four new methods added in the criterion-runtime-di-container RFC:
``read_resource``, ``list_resources``, ``db_read_session``, ``event_sink``.
Also covers ``run_id`` / ``task_id`` resolution.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlmodel import Session

from ergon_core.api.criterion_runtime import CriterionRuntime
from ergon_core.api.run_resource import RunResourceView
from ergon_core.core.providers.sandbox.event_sink import (
    DashboardEmitterSandboxEventSink,
    NoopSandboxEventSink,
)
from ergon_core.core.runtime.evaluation.criterion_runtime import (
    CriterionRuntimeOptions,
    DefaultCriterionRuntime,
    ResourceNotFoundError,
)
from ergon_core.core.runtime.evaluation.evaluation_schemas import CriterionContext


def _criterion_context(run_id=None) -> CriterionContext:
    return CriterionContext(
        run_id=run_id or uuid4(),
        task_input="test task",
        agent_reasoning="test output",
    )


def _make_runtime(
    *,
    run_id=None,
    task_id=None,
    event_sink=None,
) -> DefaultCriterionRuntime:
    context = _criterion_context()
    sandbox_manager = MagicMock()
    return DefaultCriterionRuntime(
        context=context,
        sandbox_manager=sandbox_manager,
        options=CriterionRuntimeOptions(
            run_id=run_id,
            task_id=task_id,
            event_sink=event_sink,
        ),
    )


class TestReadResource:
    @pytest.mark.asyncio
    async def test_found_reads_blob(self, tmp_path: Path) -> None:
        """read_resource returns bytes from file_path on disk."""
        blob = tmp_path / "abc"
        blob.write_bytes(b"hello-world")

        run_id = uuid4()
        row = MagicMock()
        row.file_path = str(blob)
        row.run_id = run_id
        row.name = "patch"

        runtime = _make_runtime(run_id=run_id)

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.exec.return_value.first.return_value = row

        with patch(
            "ergon_core.core.runtime.evaluation.criterion_runtime.get_session",
            return_value=mock_session,
        ):
            result = await runtime.read_resource("patch")

        assert result == b"hello-world"

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        """read_resource raises ResourceNotFoundError when no row matches."""
        runtime = _make_runtime()

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.exec.return_value.first.return_value = None

        with patch(
            "ergon_core.core.runtime.evaluation.criterion_runtime.get_session",
            return_value=mock_session,
        ):
            with pytest.raises(ResourceNotFoundError, match="no_such_resource"):
                await runtime.read_resource("no_such_resource")


class TestListResources:
    @pytest.mark.asyncio
    async def test_returns_dtos_newest_first(self) -> None:
        """list_resources maps ORM rows to RunResourceView DTOs."""
        runtime = _make_runtime()
        mock_row = MagicMock()

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.exec.return_value.all.return_value = [mock_row]

        with (
            patch(
                "ergon_core.core.runtime.evaluation.criterion_runtime.get_session",
                return_value=mock_session,
            ),
            patch.object(RunResourceView, "from_row", return_value=MagicMock()) as mock_from_row,
        ):
            result = await runtime.list_resources()

        assert len(result) == 1
        mock_from_row.assert_called_once_with(mock_row)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_resources(self) -> None:
        """list_resources returns [] when there are no run_resources rows."""
        runtime = _make_runtime()

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.exec.return_value.all.return_value = []

        with patch(
            "ergon_core.core.runtime.evaluation.criterion_runtime.get_session",
            return_value=mock_session,
        ):
            result = await runtime.list_resources()

        assert result == []


class TestDbReadSession:
    def test_returns_session(self) -> None:
        """db_read_session returns the session from get_session()."""
        runtime = _make_runtime()
        with patch("ergon_core.core.runtime.evaluation.criterion_runtime.get_session") as mock_get:
            mock_get.return_value = MagicMock(spec=Session)
            sess = runtime.db_read_session()
        assert sess is mock_get.return_value


class TestEventSink:
    def test_returns_noop_by_default(self) -> None:
        """event_sink() returns a NoopSandboxEventSink when none was injected."""
        runtime = _make_runtime()
        assert isinstance(runtime.event_sink(), NoopSandboxEventSink)

    def test_returns_injected_sink(self) -> None:
        """event_sink() returns the sink passed at construction time."""
        emitter = MagicMock()
        sink = DashboardEmitterSandboxEventSink(emitter)
        runtime = _make_runtime(event_sink=sink)
        assert runtime.event_sink() is sink


class TestRunIdResolution:
    def test_explicit_run_id_overrides_context(self) -> None:
        """When run_id is given explicitly it takes precedence over context.run_id."""
        context = _criterion_context()
        explicit_id = uuid4()
        runtime = DefaultCriterionRuntime(
            context=context,
            sandbox_manager=MagicMock(),
            options=CriterionRuntimeOptions(run_id=explicit_id),
        )
        assert runtime._run_id == explicit_id

    def test_default_falls_back_to_context(self) -> None:
        """When run_id is omitted, _run_id equals context.run_id."""
        context = _criterion_context()
        runtime = DefaultCriterionRuntime(
            context=context,
            sandbox_manager=MagicMock(),
        )
        assert runtime._run_id == context.run_id

    def test_task_id_stored(self) -> None:
        """task_id is stored on _task_id when provided."""
        context = _criterion_context()
        tid = uuid4()
        runtime = DefaultCriterionRuntime(
            context=context,
            sandbox_manager=MagicMock(),
            options=CriterionRuntimeOptions(task_id=tid),
        )
        assert runtime._task_id == tid

    def test_task_id_defaults_to_none(self) -> None:
        """_task_id is None when task_id is not provided."""
        runtime = _make_runtime()
        assert runtime._task_id is None


class TestCriterionRuntimeProtocolCompliance:
    def test_protocol_has_all_twelve_methods(self) -> None:
        """CriterionRuntime Protocol exposes all 12 expected method names."""
        expected = {
            "ensure_sandbox",
            "upload_files",
            "write_file",
            "run_command",
            "execute_code",
            "call_llm_judge",
            "cleanup",
            "read_resource",
            "list_resources",
            "get_all_files_for_task",
            "db_read_session",
            "event_sink",
        }
        actual = {name for name in dir(CriterionRuntime) if not name.startswith("_")}
        missing = expected - actual
        assert not missing, f"CriterionRuntime missing methods: {missing}"
