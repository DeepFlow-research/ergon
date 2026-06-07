"""Tests for SampleRecordMissingError and the runtime identity helper."""

from uuid import uuid4

import pytest
from ergon_core.core.application.runtime.sample_identity import definition_id_for_run
from ergon_core.core.application.runtime.task_errors import SampleRecordMissingError


def test_error_message_contains_run_id():
    """SampleRecordMissingError message includes the sample_id for debugging."""
    sample_id = uuid4()
    err = SampleRecordMissingError(sample_id)
    assert str(sample_id) in str(err)


def test_error_is_exception_subclass():
    """SampleRecordMissingError must be an Exception subclass so it propagates as an error."""
    sample_id = uuid4()
    err = SampleRecordMissingError(sample_id)
    assert isinstance(err, Exception)


def test_service_raises_when_run_record_missing():
    """definition_id_for_run raises SampleRecordMissingError when session returns None."""
    from unittest.mock import MagicMock

    session = MagicMock()
    # exec().first() returns None → no SampleRecord found
    session.exec.return_value.first.return_value = None

    sample_id = uuid4()

    with pytest.raises(SampleRecordMissingError, match=str(sample_id)):
        definition_id_for_run(session, sample_id)
