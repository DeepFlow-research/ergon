"""Tests for RunRecordMissingError and the runtime identity helper."""

from uuid import uuid4

import pytest
from ergon_core.core.application.runtime.run_identity import definition_id_for_run
from ergon_core.core.application.runtime.task_errors import RunRecordMissingError


def test_error_message_contains_run_id():
    """RunRecordMissingError message includes the run_id for debugging."""
    run_id = uuid4()
    err = RunRecordMissingError(run_id)
    assert str(run_id) in str(err)


def test_error_is_exception_subclass():
    """RunRecordMissingError must be an Exception subclass so it propagates as an error."""
    run_id = uuid4()
    err = RunRecordMissingError(run_id)
    assert isinstance(err, Exception)


def test_service_raises_when_run_record_missing():
    """definition_id_for_run raises RunRecordMissingError when session returns None."""
    from unittest.mock import MagicMock

    session = MagicMock()
    # exec().first() returns None → no RunRecord found
    session.exec.return_value.first.return_value = None

    run_id = uuid4()

    with pytest.raises(RunRecordMissingError, match=str(run_id)):
        definition_id_for_run(session, run_id)
