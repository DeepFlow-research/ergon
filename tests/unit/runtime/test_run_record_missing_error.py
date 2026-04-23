"""Tests for RunRecordMissingError and the service method that raises it."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from ergon_core.core.runtime.errors.delegation_errors import RunRecordMissingError
from ergon_core.core.runtime.services.task_management_service import TaskManagementService


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
    """_resolve_definition_id raises RunRecordMissingError when session returns None."""
    session = MagicMock()
    # exec().first() returns None → no RunRecord found
    session.exec.return_value.first.return_value = None

    svc = TaskManagementService()
    run_id = uuid4()

    with pytest.raises(RunRecordMissingError, match=str(run_id)):
        svc._resolve_definition_id(session, run_id)
