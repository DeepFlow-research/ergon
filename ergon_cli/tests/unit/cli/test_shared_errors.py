import pytest

from ergon_cli.shared import exit_codes
from ergon_cli.shared.errors import CliDependencyError, CliNotFoundError, CliUsageError
from ergon_cli.shared.parsing import parse_uuid


def test_error_subclasses_carry_exit_codes() -> None:
    assert CliUsageError("bad").exit_code == exit_codes.USAGE
    assert CliNotFoundError("missing").exit_code == exit_codes.NOT_FOUND
    assert CliDependencyError("docker").exit_code == exit_codes.RUNTIME_ERROR


def test_parse_uuid_returns_uuid_or_usage_error() -> None:
    assert str(parse_uuid("00000000-0000-0000-0000-000000000000")) == (
        "00000000-0000-0000-0000-000000000000"
    )
    with pytest.raises(CliUsageError):
        parse_uuid("not-a-uuid", field_name="sample_id")
