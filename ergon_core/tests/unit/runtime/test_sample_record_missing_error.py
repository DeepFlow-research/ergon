"""Tests for SampleRecordMissingError."""

from uuid import uuid4

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
